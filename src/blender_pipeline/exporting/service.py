"""Export jobs own presets and outputs, never edit working Blender files."""
import copy
import json
import shutil
import tempfile
from pathlib import Path
from blender_pipeline.project.model import META, uid, stamp, digest, name
from blender_pipeline.blender.export_settings import checked_options, option_values, export_timing
from blender_pipeline.project.dependencies import file_signature

FORMATS = {'FBX': '.fbx', 'GLB': '.glb', 'USD': '.usdc', 'ALEMBIC': '.abc'}


class ExportWorkflow:
    def export_node(self, source_id=None, group=None, x=None, y=None):
        source = self.node(source_id) if source_id else None
        if source and source['type'] != 'blend':
            raise ValueError('Choose a Blend file as the export source.')
        scan = source.get('scan', {}) if source else {}
        scenes = [s for s in scan.get('scenes', []) if not s.get('linked')]
        scene = next((s for s in scenes if s['name'] == scan.get('active_scene')), None) or next(iter(scenes), {})
        node = {'id': uid(), 'type': 'export', 'name': 'Export', 'group': group,
                'export_config': {'source_id': source_id, 'folder_id': None, 'format': 'GLB',
                                  'scene': scene.get('name', ''), 'scope': 'SCENE', 'collections': [],
                                  'animation': False, 'start': None, 'end': None, 'options': {}},
                **self.graph_position(x, y)}
        before = copy.deepcopy(self.data)
        try:
            self.data['nodes'].append(node)
            self.validate_groups(self.data['nodes'])
            self.save()
        except Exception:
            self.data = before
            raise
        return self.state()

    def checked_export(self, config, ready=False):
        if not isinstance(config, dict):
            raise ValueError('Invalid export settings.')
        if set(config) - {'source_id', 'folder_id', 'format', 'scene', 'scope', 'collections', 'animation', 'start', 'end', 'options'}:
            raise ValueError('Unknown export setting.')
        result = {'source_id': config.get('source_id') or None, 'folder_id': config.get('folder_id') or None,
                  'format': config.get('format', 'GLB'), 'scene': str(config.get('scene') or ''),
                  'scope': config.get('scope', 'SCENE'), 'collections': [],
                  'animation': config.get('animation', False), 'start': config.get('start'), 'end': config.get('end'),
                  'options': checked_options(config.get('options', {}))}
        if result['format'] not in FORMATS or result['scope'] not in {'SCENE', 'COLLECTIONS'}:
            raise ValueError('Choose a supported format and content scope.')
        if type(result['animation']) is not bool:
            raise ValueError('Animation must be enabled or disabled.')
        items = config.get('collections', [])
        if not isinstance(items, list) or any(not isinstance(v, str) or not v for v in items):
            raise ValueError('Choose collections from the saved file.')
        result['collections'] = list(dict.fromkeys(items))
        for key in ('start', 'end'):
            if result[key] is not None and (type(result[key]) is not int or not -1048574 <= result[key] <= 1048574):
                raise ValueError('Use whole frame numbers in Blender’s supported range.')
        if result['animation'] and result['start'] is not None and result['end'] is not None and result['end'] < result['start']:
            raise ValueError('Last frame must not precede first frame.')
        if result['source_id']:
            source = next((n for n in self.data['nodes'] if n['id'] == result['source_id']), None)
            if not source or source['type'] != 'blend':
                raise ValueError('The source Blend file is no longer registered. Choose another source.')
            if ready:
                scan = source.get('scan', {})
                if scan.get('error'):
                    raise ValueError(scan['error'])
                scenes = [s for s in scan.get('scenes', []) if not s.get('linked')]
                scene = next((s for s in scenes if s['name'] == result['scene']), None)
                if not scene:
                    raise ValueError('Choose an existing local scene. Refresh the source if it changed.')
                export_timing(result, scene)
                if result['scope'] == 'COLLECTIONS' and not result['collections']:
                    raise ValueError('Choose at least one collection.')
                if result['scope'] == 'COLLECTIONS' and 'collections' in scene and not set(result['collections']).issubset(scene['collections']):
                    raise ValueError('An export collection is not in the selected scene. Refresh and choose its contents again.')
        elif ready:
            raise ValueError('Connect a Blend file first.')
        if result['folder_id']:
            folder = next((n for n in self.data['nodes'] if n['id'] == result['folder_id']), None)
            if not folder:
                raise ValueError('The output folder is no longer registered. Connect another folder.')
            if folder['type'] != 'folder':
                raise ValueError('Choose a physical output folder; visual frames cannot store exports.')
        elif ready:
            raise ValueError('Connect an output folder first.')
        return result

    def export_config(self, node_id, config):
        node = self.node(node_id)
        if node['type'] != 'export':
            raise ValueError('Choose an Export node.')
        checked = self.checked_export(config)
        before = copy.deepcopy(node)
        try:
            node['export_config'] = checked
            self.save()
        except Exception:
            node.clear(); node.update(before)
            raise
        return self.state()

    def export_start(self, node_id):
        node = self.node(node_id)
        if node['type'] != 'export':
            raise ValueError('Choose an Export node.')
        config = self.checked_export(node['export_config'])
        if not config['source_id']:
            raise ValueError('Connect a Blend file first.')
        source = self.node(config['source_id'])
        self.inspect(source)
        config = self.checked_export(config, ready=True)
        scene = next(s for s in source['scan']['scenes'] if s['name'] == config['scene'] and not s.get('linked'))
        timing = export_timing(config, scene)
        inputs = self.capture_render_inputs(source)
        destination = self.path(self.node(config['folder_id']))
        if not destination.is_dir():
            raise ValueError('The output folder is missing.')
        runs = self.data.setdefault('exports', [])
        number = max((r['number'] for r in runs if r['node_id'] == node_id), default=0) + 1
        stem = name(source['path'].split('/')[-1].removesuffix('.blend'))
        label = name(node['name'])
        while True:
            directory = destination / f'{stem}_{label}_e{number:03}'
            try:
                directory.mkdir()
                break
            except FileExistsError:
                number += 1
        run = {'id': uid(), 'project_id': self.data['id'], 'node_id': node_id, 'source_id': source['id'],
               'number': number, 'created': stamp(), 'status': 'Exporting', 'error': '',
               'output': directory.relative_to(self.root).as_posix(), 'settings': copy.deepcopy(config),
               'timing': timing, 'format_options': option_values(config['format'], config['options'], animation=config['animation']),
               'inputs': inputs, 'file': stem + FORMATS[config['format']]}
        runs.append(run)
        try:
            self.save()
            # Frozen inputs preserve relative dependencies while Blender reads a disposable copy.
            with tempfile.TemporaryDirectory(prefix='export-', dir=self.root / META) as temporary:
                frozen = Path(temporary)
                for relative, expected in inputs.items():
                    original = (self.root / relative).resolve()
                    run.setdefault('input_signatures',{})[relative]=file_signature(original)
                    if not original.is_relative_to(self.root) or digest(original) != expected:
                        raise ValueError('An export input changed. Save and export again: ' + relative)
                    target = frozen / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(original, target)
                    if digest(target) != expected or digest(original) != expected:
                        raise ValueError('An export input changed during copying: ' + relative)
                settings = frozen / 'export-job.json'
                settings.write_text(json.dumps(config), encoding='utf-8')
                self.run('export_job.py', [settings, directory / run['file']], frozen / source['path'])
            output = directory / run['file']
            if not output.is_file() or not output.stat().st_size:
                raise ValueError('Blender did not produce an export file.')
            run.update(status='Complete', finished=stamp(), bytes=output.stat().st_size, hash=digest(output))
            self.save()
        except Exception as exc:
            run.update(status='Failed', finished=stamp(), error=str(exc))
            self.save()
            raise
        self._folder_cache = {}
        return self.state()

    def export_open(self, run_id):
        self.require_desktop()
        run = next((r for r in self.data.get('exports', []) if r['id'] == run_id), None)
        if not run:
            raise ValueError('Export version not found.')
        path = (self.root / run['output']).resolve()
        if not path.is_relative_to(self.root) or path.is_relative_to(self.root / META) or not path.is_dir():
            raise ValueError('Export output is missing or outside the project.')
        self.desktop.open_folder(path, self.desktop_available())
        return self.state()
