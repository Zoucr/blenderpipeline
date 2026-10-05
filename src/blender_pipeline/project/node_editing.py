"""Saved-file naming and independent copies of graph selections."""
import copy
from datetime import datetime
import math
from pathlib import Path
import re
import shutil

from blender_pipeline.project.model import digest, name, uid


def filename_component(value):
    return re.sub(r'[^\w-]+', '_', str(value).strip(), flags=re.UNICODE).strip('_-')[:64] or 'Blend'


class NodeEditing:
    def node_colors(self, node_ids, color):
        if color not in {'default', 'blue', 'green', 'purple', 'orange', 'red'}: raise ValueError('Choose a supported node color.')
        if not isinstance(node_ids, list) or not 1 <= len(node_ids) <= 200 or any(not isinstance(i, str) for i in node_ids): raise ValueError('Choose between 1 and 200 nodes.')
        nodes = [self.node(i) for i in dict.fromkeys(node_ids)]
        for node in nodes: node['color'] = color
        self.save()
        return self.state()

    def blend_filename(self, title, naming=None):
        naming = naming or {'date': datetime.now().strftime('%y%m%d'), 'version': 1}
        return name(f"{naming['date']}_{filename_component(self.data['name'])}_{filename_component(title)}-v{naming['version']:03}.blend")

    def new_blend_name(self, title, parent):
        if title:
            title = str(title).strip()
            if title.lower().endswith('.blend'): title = title[:-6]
            name(title)
            if len(title) > 120: raise ValueError('Use a name of at most 120 characters.')
            return title
        number = 1
        while True:
            title = f'Blend {number:02}'
            if not any(n['name'].casefold() == title.casefold() for n in self.data['nodes']) and not (parent / self.blend_filename(title)).exists():
                return title
            number += 1

    def label(self, node_id, title):
        node = self.node(node_id)
        title = str(title).strip()
        if not title or len(title) > 120: raise ValueError('Use a name between 1 and 120 characters.')
        if node['type'] != 'blend' or node.get('external'):
            return super().label(node_id, title)
        naming = node.get('file_naming') or {'date': datetime.now().strftime('%y%m%d'), 'version': 1}
        destination = self.path(node).with_name(self.blend_filename(title, naming))
        self._relocate_file(node, destination, True, node.get('group'), title)
        node['file_naming'] = naming
        self.save()
        return self.state()

    def relocate(self, node_id, folder_id, title, closed):
        node = self.node(node_id)
        parent = self.path(self.node(folder_id)) if folder_id else self.root
        if folder_id and self.node(folder_id)['type'] != 'folder': raise ValueError('Choose a folder.')
        title = name(title)
        destination = parent / (title if title.lower().endswith('.blend') else title + '.blend')
        return self._relocate_file(node, destination, closed, folder_id)

    def _relocate_file(self, node, destination, closed, group, display_name=None):
        if node['type'] != 'blend' or node.get('external'): raise ValueError('Only managed Blend files can be renamed or moved.')
        if self.render_busy(): raise ValueError('Finish or cancel the render queue before renaming files.')
        self.ensure_closed(node, closed)
        old = self.path(node)
        destination = destination.resolve()
        if not destination.is_relative_to(self.root) or destination.is_relative_to(self.root / '.pipeline'):
            raise ValueError('Choose a working location inside this project.')
        if destination == old:
            if display_name: node['name'] = display_name; self.save()
            return self.state()
        if destination.exists(): raise ValueError('A file with that name already exists.')
        self.refresh()
        if any(n.get('scan', {}).get('error') for n in self.data['nodes'] if n['type'] == 'blend'):
            raise ValueError('Resolve file scan errors before renaming so registered dependencies can be repaired.')
        dependents = [n for n in self.data['nodes'] if n['type'] == 'blend' and n['id'] != node['id'] and any(
            r['kind'] == 'Library' and Path(r['path']).resolve() == old for r in n.get('scan', {}).get('refs', []))]
        if any(n.get('external') for n in dependents): raise ValueError('An external file uses this library. Repair that reference in Blender before renaming.')
        for dependent in dependents: self.ensure_closed(dependent, closed)
        before = {k: node.get(k) for k in ('path', 'name', 'group')}
        for n in [node, *dependents]:
            for item in n['snapshots']: item.setdefault('origin_path', n['path'])
            self.snapshot(n['id'], 'Before renaming / moving ' + old.name)
        recovery = {n['id']: self.root / n['snapshots'][-1]['path'] for n in [node, *dependents]}
        recovery_metadata = copy.deepcopy(self.data)
        staged = dict(node, path=destination.relative_to(self.root).as_posix())
        repaired = {}
        created_hash = None
        try:
            self.transaction(staged, {'action': 'copy', 'source': str(old), 'source_hash': digest(old)}, new=True)
            created_hash = digest(destination)
            for dependent in dependents:
                self.transaction(dependent, {'action': 'repair_paths', 'old': str(old), 'new': str(destination)})
                repaired[dependent['id']] = digest(self.path(dependent))
            if digest(old) != node['snapshots'][-1]['hash']:
                raise ValueError('The source changed while renaming. Save and close it before retrying.')
            node.update(path=staged['path'], name=display_name or destination.stem, group=group)
            old.unlink()
            self.data.setdefault('path_aliases', {})[before['path']] = node['path']
            self.refresh()
        except Exception:
            # The original is untouched until unlink. Do not overwrite a concurrent
            # Blender save when a source/destination hash guard rejects the rename.
            if not old.exists(): shutil.copy2(recovery[node['id']], old)
            for dependent in dependents:
                if dependent['id'] in repaired and self.path(dependent).is_file() and digest(self.path(dependent)) == repaired[dependent['id']]:
                    shutil.copy2(recovery[dependent['id']], self.path(dependent))
            node.update(before)
            self.data = recovery_metadata
            if created_hash and destination.is_file() and digest(destination) == created_hash:
                destination.unlink()
            raise
        return self.state()

    def duplicate(self, node_id, x=None, y=None):
        return self.paste_nodes([node_id], x=x, y=y, clipboard_project_id=self.data['id'])

    def paste_nodes(self, node_ids, x=None, y=None, clipboard_project_id=None):
        if clipboard_project_id != self.data['id']: raise ValueError('These copied nodes belong to a different project. Copy nodes from this project first.')
        if not isinstance(node_ids, list) or not node_ids or len(node_ids) > 200 or any(not isinstance(i, str) for i in node_ids):
            raise ValueError('Copy between 1 and 200 nodes.')
        originals = [self.node(i) for i in dict.fromkeys(node_ids)]
        # Copying containers includes their graph members, without copying old renders/history.
        included = {n['id'] for n in originals}
        for node in originals:
            if node['type'] in {'folder', 'frame'}:
                originals.extend(n for n in self.data['nodes'] if n.get('group') == node['id'] and n['id'] not in included and not n.get('hidden'))
                included.update(n['id'] for n in originals)
        if len(originals) > 200: raise ValueError('The selection contains more than 200 nodes. Copy a smaller group.')
        if any(n.get('external') for n in originals): raise ValueError('Collect external libraries into the project before copying their nodes.')
        origin_x, origin_y = min(n['x'] for n in originals), min(n['y'] for n in originals)
        x, y = origin_x + 50 if x is None else float(x), origin_y + 50 if y is None else float(y)
        if not all(math.isfinite(v) for v in (x, y)): raise ValueError('Choose a finite graph position.')
        remap = {n['id']: uid() for n in originals}
        names = {n['name'].casefold() for n in self.data['nodes']}
        paths, clones, directories, files = {}, [], [], []
        before = copy.deepcopy(self.data)
        hashes = {n['id']: digest(self.path(n)) for n in originals if n['type'] == 'blend'}
        folder_sources = sorted((n for n in originals if n['type'] == 'folder'), key=lambda n: len(self.path(n).parts))

        def copy_parent(path):
            ancestors = [f for f in folder_sources if f['id'] in paths and path.is_relative_to(self.path(f))]
            if not ancestors: return path
            f = max(ancestors, key=lambda f: len(self.path(f).parts))
            return paths[f['id']] / path.relative_to(self.path(f))

        for source in [*folder_sources, *(n for n in originals if n['type'] != 'folder')]:
            base = re.sub(r' \d{2,}$', '', source['name'])[:112]
            number = 1
            while True:
                title = f'{base} {number:02}'
                target = None
                if source['type'] in {'blend', 'folder'}:
                    parent = copy_parent(self.path(source).parent)
                    target = parent / (self.blend_filename(title, source.get('file_naming')) if source['type'] == 'blend' else name(title))
                if title.casefold() not in names and (target is None or not target.exists() and target not in paths.values()): break
                number += 1
            names.add(title.casefold())
            clone = copy.deepcopy(source)
            clone.update(id=remap[source['id']], name=title, x=source['x'] + x - origin_x, y=source['y'] + y - origin_y,
                         group=remap.get(source.get('group'), source.get('group')), hidden=False)
            for field in ('last_error', 'content_changes', 'last_link_batch', 'dependency_hashes', 'scan'): clone.pop(field, None)
            if target:
                paths[source['id']] = target
                clone['path'] = target.relative_to(self.root).as_posix()
            if source['type'] == 'blend':
                clone['snapshots'] = []
                clone['file_naming'] = copy.deepcopy(source.get('file_naming') or {'date': datetime.now().strftime('%y%m%d'), 'version': 1})
                if clone.get('render_config'): clone['render_config']['folder_id'] = remap.get(clone['render_config']['folder_id'], clone['render_config']['folder_id'])
            if source['type'] == 'render':
                plan = clone['render_plan']
                plan['source_ids'] = [remap.get(i, i) for i in plan.get('source_ids', dict.fromkeys(t['source_id'] for t in plan['targets']))]
                plan['folder_id'] = remap.get(plan.get('folder_id'), plan.get('folder_id'))
                for t in plan['targets']:
                    t.update(id=uid(), source_id=remap.get(t['source_id'], t['source_id']))
                    t.pop('output_subfolder', None)
            if source['type'] == 'export':
                for key in ('source_id', 'folder_id'): clone['export_config'][key] = remap.get(clone['export_config'].get(key), clone['export_config'].get(key))
            clones.append((source, clone))
        aliases = {str(self.path(n)): str(paths[n['id']]) for n in originals if n['type'] == 'blend'}
        try:
            for source, clone in clones:
                if clone['type'] not in {'folder', 'blend'}: continue
                target = paths[source['id']]
                missing = []
                current = target if clone['type'] == 'folder' else target.parent
                while not current.exists(): missing.append(current); current = current.parent
                for directory in reversed(missing): directory.mkdir(); directories.append(directory)
                if clone['type'] == 'blend':
                    original = self.path(source)
                    # A byte copy keeps a lone file's relative links and overrides exactly intact.
                    if original.parent == target.parent and len(aliases) == 1:
                        with original.open('rb') as reader, target.open('xb') as writer:
                            files.append(target); shutil.copyfileobj(reader, writer)
                        if digest(target) != hashes[source['id']]: raise ValueError('The source changed while copying. Save it and copy again.')
                    else:
                        self.transaction(clone, {'action': 'copy', 'source': str(original), 'source_hash': hashes[source['id']], 'aliases': aliases}, new=True)
                        files.append(target)
            if any(digest(self.path(n)) != hashes[n['id']] for n in originals if n['type'] == 'blend'):
                raise ValueError('A source changed while copying. Save it and copy again.')
            self.data['nodes'].extend(c for _, c in clones)
            for _, clone in clones:
                if clone['type'] == 'render': clone['render_plan'] = self.checked_render_plan(clone['render_plan'], clone['id'])
                if clone['type'] == 'blend':
                    self.inspect(clone)
                    if clone.get('scan', {}).get('error'): raise ValueError('Could not read the copied file: ' + clone['scan']['error'])
            self.validate_groups(self.data['nodes'])
            self.save()
        except Exception:
            self.data = before
            for file in files: file.unlink(missing_ok=True)
            for directory in reversed(directories):
                if directory.exists() and not any(directory.iterdir()): directory.rmdir()
            raise
        result = self.state()
        result['pasted_ids'] = [remap[n['id']] for n in originals]
        return result
