"""Named scene/view-layer setups share file connections and the render queue."""
import copy
import re
from blender_pipeline.project.model import uid, name
from blender_pipeline.blender.compositor_outputs import clean


class RenderGraph:
    def render_node(self, source_ids=None, group=None, x=None, y=None, adopt_existing=False):
        sources = [self.node(i) for i in dict.fromkeys(source_ids or [])]
        if any(s['type'] != 'blend' or s.get('external') for s in sources):
            raise ValueError('Connect managed Blend files to a Render node.')
        if adopt_existing and len(sources) != 1:
            raise ValueError('Move one existing output connection at a time.')
        if adopt_existing and self.render_busy():
            raise ValueError('Finish queued renders before moving an output connection.')
        plan = {'folder_id': None, 'source_ids': [s['id'] for s in sources], 'targets': [], 'overrides': {}}
        for source in sources:
            existing = source.get('render_config', {}) if adopt_existing else {}
            scenes = [s for s in source.get('scan', {}).get('scenes', []) if not s.get('linked')]
            scene = next((s for s in scenes if s['name'] == source.get('scan', {}).get('active_scene')), None)
            scene = scene or next((s for s in scenes if s.get('camera')), None) or next(iter(scenes), {})
            if existing:
                scene = next((s for s in scenes if s['name'] == existing.get('scene')), scene)
            plan['targets'].append({'id': uid(), 'source_id': source['id'], 'scene': existing.get('scene', scene.get('name', '')),
                                    'view_layer': '' if adopt_existing else scene.get('active_view_layer', ''),
                                    'compositor': 'BLENDER', 'label': '',
                                    'mode': 'ANIMATION', 'frame': None,
                                    'camera': existing.get('camera', ''), 'enabled': True,
                                    'prefix': existing.get('prefix') if existing.get('auto_prefix') is False else None,
                                    'overrides': {k: v for k, v in existing.items() if k in self.checked_overrides_keys() and v is not None}})
            if existing:
                plan['folder_id'] = existing['folder_id']
        identity = uid()
        node = {'id': identity, 'type': 'render', 'name': 'Render', 'group': group,
                'render_plan': self.checked_render_plan(plan, identity), **self.graph_position(x, y)}
        before = copy.deepcopy(self.data)
        try:
            self.data['nodes'].append(node)
            self.validate_groups(self.data['nodes'])
            if adopt_existing:
                for source in sources:
                    source.pop('render_config', None)
            self.save()
        except Exception:
            self.data = before
            raise
        return self.state()

    @staticmethod
    def checked_overrides_keys():
        return {'start', 'end', 'step', 'width', 'height', 'percentage', 'samples', 'engine', 'format', 'denoise', 'advanced'}

    def checked_render_plan(self, plan, operation_id=None):
        if not isinstance(plan, dict) or set(plan) - {'folder_id', 'source_ids', 'targets', 'overrides'}:
            raise ValueError('Invalid Render node settings.')
        folder_id = plan.get('folder_id') or None
        if folder_id and not any(n['id'] == folder_id and n['type'] == 'folder' for n in self.data['nodes']):
            raise ValueError('Connect a physical output Folder.')
        targets = plan.get('targets', [])
        if not isinstance(targets, list) or len(targets) > 500:
            raise ValueError('Choose up to 500 render setups.')
        sources = plan.get('source_ids', list(dict.fromkeys(t.get('source_id') for t in targets if isinstance(t, dict))))
        if not isinstance(sources, list) or len(sources) > 500 or any(not isinstance(i, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', i) for i in sources):
            raise ValueError('Invalid connected render files.')
        sources = list(dict.fromkeys(sources))
        for identity in sources:
            source = next((n for n in self.data['nodes'] if n['id'] == identity), None)
            if source and (source['type'] != 'blend' or source.get('external')):
                raise ValueError('Connect managed Blend files to a Render node.')
        checked, ids = [], set()
        previous = {t['id']: t for n in self.data['nodes'] if n['id'] == operation_id and n['type'] == 'render' for t in n['render_plan']['targets']}
        incoming = {t.get('id'): t for t in targets if isinstance(t, dict)}
        reserved = {t['output_subfolder'].casefold() for n in self.data['nodes'] if n['type'] == 'render' for t in n['render_plan']['targets']
                    if t.get('output_subfolder') and (n['id'] != operation_id or t['id'] in incoming and all(t.get(k, '') == incoming[t['id']].get(k, '') for k in ('source_id', 'scene', 'view_layer')))}
        reserved.update(r['config']['output_subfolder'].casefold() for r in self.data.get('renders', []) if r.get('config', {}).get('output_subfolder'))
        for target in targets:
            if not isinstance(target, dict) or set(target) - {'id', 'source_id', 'scene', 'view_layer', 'compositor', 'label', 'camera', 'enabled', 'prefix', 'overrides', 'output_subfolder', 'mode', 'frame'}:
                raise ValueError('Invalid render setup settings.')
            identity = target.get('id')
            if not isinstance(identity, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', identity) or identity in ids:
                raise ValueError('Each render setup requires a unique stable ID.')
            source = next((n for n in self.data['nodes'] if n['id'] == target.get('source_id')), None)
            if target.get('source_id') not in sources or source and (source['type'] != 'blend' or source.get('external')):
                raise ValueError('A render source is missing. Restore it or remove that target.')
            source_id = target['source_id']
            scene, camera = target.get('scene', ''), target.get('camera', '')
            layer, label = target.get('view_layer', ''), target.get('label', '')
            if any(not isinstance(v, str) or len(v) > 256 or '\x00' in v for v in (scene, camera, layer, label)):
                raise ValueError('Choose saved scene and camera names.')
            compositor = target.get('compositor', 'BLENDER')
            if compositor not in {'BLENDER', 'OFF'}:
                raise ValueError('Choose the saved compositor setting or Bypass compositor.')
            mode, frame = target.get('mode', 'ANIMATION'), target.get('frame')
            if mode not in {'ANIMATION', 'STILL'}:raise ValueError('Choose an animation range or a still frame.')
            if frame is not None:frame = self.checked_overrides({'start': frame})['start']
            enabled = target.get('enabled', True)
            if type(enabled) is not bool:
                raise ValueError('Render target enabled must be true or false.')
            prefix = target.get('prefix') or None
            if prefix is not None:
                if not isinstance(prefix, str):
                    raise ValueError('Use a filename prefix or leave it automatic.')
                prefix = name(prefix)
            ids.add(identity)
            # Allocate readable directories once. Renaming a setup keeps its output
            # location; new/duplicate setups reserve distinct paths without UUIDs.
            subfolder = previous.get(identity, {}).get('output_subfolder')
            if any(previous.get(identity, {}).get(k, '') != target.get(k, '') for k in ('source_id', 'scene', 'view_layer')):subfolder = None
            if not subfolder:
                stem = source['path'].split('/')[-1].removesuffix('.blend') if source else source_id
                base = '/'.join([clean(stem), clean(scene), clean(layer or 'All layers')])
                if label.strip():base += '/' + clean(label)
                subfolder, number = base, 2
                while subfolder.casefold() in reserved:
                    subfolder = base + f'_{number:02}';number += 1
            reserved.add(subfolder.casefold())
            checked.append({'id': identity, 'source_id': source_id, 'scene': scene, 'camera': camera,
                            'view_layer': layer, 'compositor': compositor, 'label': label.strip(),
                            'mode': mode, 'frame': frame,
                            'output_subfolder': subfolder,
                            'enabled': enabled, 'prefix': prefix, 'overrides': self.checked_overrides(target.get('overrides'))})
        return {'folder_id': folder_id, 'source_ids': sources, 'targets': checked, 'overrides': self.checked_overrides(plan.get('overrides'))}

    def render_node_config(self, node_id, plan):
        node = self.node(node_id)
        if node['type'] != 'render':
            raise ValueError('Choose a Render node.')
        checked = self.checked_render_plan(plan, node_id)
        before = copy.deepcopy(node)
        try:
            node['render_plan'] = checked
            self.save()
        except Exception:
            node.clear(); node.update(before)
            raise
        return self.state()

    def render_targets(self, folder_id=None, include_disabled=False):
        result = super().render_targets(folder_id)
        root = self.node(folder_id) if folder_id else None
        for operation in self.data['nodes']:
            if operation['type'] != 'render' or operation.get('hidden'):
                continue
            plan = operation['render_plan']
            destination = next((f for f in self.data['nodes'] if f['id'] == plan.get('folder_id') and f['type'] == 'folder'), None)
            if not destination or root and destination['id'] != root['id'] and not self.path(destination).is_relative_to(self.path(root)) and not self.in_group(destination, root['id']):
                continue
            for target in plan['targets']:
                source = next((s for s in self.data['nodes'] if s['id'] == target['source_id'] and s['type'] == 'blend'), None)
                if not source or source.get('external') or not target['enabled'] and not include_disabled:
                    continue
                layer_label = target.get('view_layer') or 'All layers'
                label = target.get('label') or target['scene'] + ' · ' + layer_label
                # Older saved plans keep their old directory until explicitly edited.
                subfolder = target.get('output_subfolder') or name(source['path'].split('/')[-1].removesuffix('.blend') + '_' + clean(target['scene']))
                config = {'folder_id': destination['id'], 'scene': target['scene'], 'camera': target['camera'],
                          'view_layer': target.get('view_layer', ''), 'compositor': target.get('compositor', 'BLENDER'), 'setup_label': label,
                          'mode': target.get('mode', 'ANIMATION'), 'frame': target.get('frame'),
                          'start': None, 'end': None, 'percentage': None, 'auto_prefix': target.get('prefix') is None,
                          'prefix': target.get('prefix'),
                          **copy.deepcopy(target['overrides']), 'operation_id': operation['id'],
                          'target_id': target['id'], 'output_subfolder': subfolder}
                merged = {**target['overrides'], **plan['overrides']}
                if target['overrides'].get('advanced') or plan['overrides'].get('advanced'):
                    merged['advanced'] = {**target['overrides'].get('advanced', {}), **plan['overrides'].get('advanced', {})}
                config.update(copy.deepcopy(merged))
                result.append({**source, 'id': operation['id'] + ':' + target['id'], 'source_id': source['id'],
                               'operation_id': operation['id'], 'target_id': target['id'],
                               'name': source['name'] + ' · ' + label, 'render_config': config})
        return result

    def in_group(self, node, group):
        seen = set()
        while node.get('group') and node['id'] not in seen:
            seen.add(node['id'])
            if node['group'] == group:
                return True
            node = next((n for n in self.data['nodes'] if n['id'] == node['group']), {})
        return False

    def queue_render_node(self, node_id, target_ids=None, overrides=None, label='', allow_image_warnings=False, accepted_image_warnings=None):
        operation = self.node(node_id)
        if operation['type'] != 'render':
            raise ValueError('Choose a Render node.')
        if not operation['render_plan'].get('folder_id'):
            raise ValueError('Connect the Render node output to a Folder first.')
        available = [n for n in self.render_targets(include_disabled=True) if n.get('operation_id') == node_id]
        ids = [t['id'] for t in operation['render_plan']['targets'] if t['enabled']] if target_ids is None else target_ids
        if not isinstance(ids, list) or any(i not in {n['target_id'] for n in available} for i in ids):
            raise ValueError('A selected render setup has a missing source file. Restore the source or remove that setup.')
        if not ids:
            raise ValueError('Enable and connect at least one render setup.')
        return self.queue_batch(node_ids=[node_id + ':' + i for i in dict.fromkeys(ids)], overrides=overrides, label=label or operation['name'], allow_image_warnings=allow_image_warnings, accepted_image_warnings=accepted_image_warnings)
