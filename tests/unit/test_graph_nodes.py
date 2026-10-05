"""Graph-only grouping and safe, versioned export contracts."""
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from blender_pipeline.project.workspace import Pipeline
from blender_pipeline.project.model import digest


class GraphNodeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        settings = self.base / 'settings'
        settings.mkdir()
        self.pipeline = Pipeline(data_directory=settings)
        self.pipeline.create(self.base, 'Test')

    def tearDown(self):
        self.temp.cleanup()

    def test_frames_never_create_paths_and_unframe_preserves_members(self):
        p = self.pipeline
        p.folder('Assets')
        folder = p.data['nodes'][-1]
        before = {f.relative_to(p.root).as_posix() for f in p.root.rglob('*')}
        p.frame('Preparation', node_ids=[folder['id']])
        frame = p.data['nodes'][-1]
        self.assertNotIn('path', frame)
        self.assertEqual(before, {f.relative_to(p.root).as_posix() for f in p.root.rglob('*')})
        self.assertEqual(p.physical_folder(frame['id']), None)
        self.assertEqual(p.node(folder['id'])['group'], frame['id'])
        with self.assertRaisesRegex(ValueError, 'Confirm'):
            p.remove_graph_node(frame['id'])
        p.remove_graph_node(frame['id'], confirmed=True)
        self.assertIsNone(p.node(folder['id'])['group'])
        self.assertTrue((p.root / 'Assets').is_dir())
        record = p.data['archived_graph_nodes'][-1]
        p.restore_graph_node(record['id'])
        self.assertEqual(p.node(folder['id'])['group'], frame['id'])
        p.load(p.root)
        self.assertEqual(p.node(frame['id'])['type'], 'frame')
        with self.assertRaisesRegex(ValueError, 'no file'):
            p.path(p.node(frame['id']))

    def test_nested_frame_resolves_disk_folder_and_rejects_cycles(self):
        p = self.pipeline
        p.folder('Assets')
        folder = p.data['nodes'][-1]
        p.frame(group=folder['id'])
        outer = p.data['nodes'][-1]
        p.frame(group=outer['id'])
        inner = p.data['nodes'][-1]
        self.assertEqual(p.physical_folder(inner['id']), folder['id'])
        with self.assertRaisesRegex(ValueError, 'itself or an ancestor'):
            p.group_nodes({folder['id']: inner['id']})
        count = len(p.data['nodes'])
        with self.assertRaises(ValueError):
            p.frame(node_ids=[outer['id']], group=inner['id'])
        self.assertEqual(len(p.data['nodes']), count)

    def test_folder_recovery_keeps_visual_parent_and_export_destination(self):
        p = self.pipeline
        p.frame('Outputs group')
        frame = p.data['nodes'][-1]
        p.folder('Exports', folder_id=frame['id'])
        folder = p.data['nodes'][-1]
        p.export_node()
        node = p.data['nodes'][-1]
        p.export_config(node['id'], {**node['export_config'], 'folder_id': folder['id']})
        p.archive_folder(folder['id'], confirmed=True)
        self.assertIsNone(node['export_config']['folder_id'])
        p.restore_folder(p.data['archived_folders'][-1]['id'])
        self.assertEqual(p.node(folder['id'])['group'], frame['id'])
        self.assertEqual(node['export_config']['folder_id'], folder['id'])

    def source(self):
        p = self.pipeline
        path = p.root / 'Model.blend'
        path.write_bytes(b'saved Blender state')
        node = {'id': 'source', 'type': 'blend', 'path': path.name, 'name': 'Model', 'x': 0, 'y': 0,
                'snapshots': [], 'scan': {'error': '', 'refs': [], 'scenes': [{'name': 'Scene', 'start': 1, 'end': 3, 'current_frame': 2, 'fps': 24}],
                'signature': [path.stat().st_mtime_ns, path.stat().st_size]}}
        p.data['nodes'].append(node)
        p.save()
        return node

    def test_export_uses_frozen_inputs_versions_and_never_changes_source(self):
        p = self.pipeline
        source = self.source()
        p.folder('Outputs')
        folder = p.data['nodes'][-1]
        p.export_node(source_id=source['id'])
        node = p.data['nodes'][-1]
        p.export_config(node['id'], {**node['export_config'], 'scene': 'Scene', 'folder_id': folder['id']})
        original = digest(p.path(source))
        calls = []
        def worker(script, args, opened):
            self.assertEqual(script, 'export_job.py')
            self.assertNotEqual(opened, p.path(source))
            self.assertEqual(digest(opened), original)
            self.assertEqual(json.loads(Path(args[0]).read_text())['scene'], 'Scene')
            Path(args[1]).write_bytes(b'exported geometry')
            calls.append(opened)
        with patch.object(p, 'inspect'), patch.object(p, 'run', side_effect=worker):
            p.export_start(node['id'])
            p.export_start(node['id'])
        self.assertEqual([r['number'] for r in p.data['exports']], [1, 2])
        self.assertTrue(all(r['status'] == 'Complete' for r in p.data['exports']))
        self.assertTrue(all(r['timing'] == {'mode': 'FRAME', 'start': 2, 'end': 2, 'frames': 1, 'fps': 24} for r in p.data['exports']))
        self.assertEqual(digest(p.path(source)), original)
        self.assertTrue(all(not f.exists() for f in calls))
        p.remove_graph_node(node['id'], confirmed=True)
        self.assertTrue(all((p.root / r['output'] / r['file']).exists() for r in p.data['exports']))

    def test_connected_export_defaults_to_active_local_scene(self):
        p = self.pipeline
        source = self.source()
        source['scan'].update(active_scene='Lighting', scenes=[{'name': 'Linked', 'linked': True}, {'name': 'Scene'}, {'name': 'Lighting'}])
        p.export_node(source_id=source['id'])
        self.assertEqual(p.data['nodes'][-1]['export_config']['scene'], 'Lighting')
        source['scan']['active_scene'] = 'Linked'
        p.export_node(source_id=source['id'])
        self.assertEqual(p.data['nodes'][-1]['export_config']['scene'], 'Scene')
        p.export_node()
        self.assertEqual(p.data['nodes'][-1]['export_config']['scene'], '')

    def test_export_rejects_visual_destination_and_records_failed_worker(self):
        p = self.pipeline
        source = self.source()
        p.frame()
        frame = p.data['nodes'][-1]
        p.export_node(source_id=source['id'])
        node = p.data['nodes'][-1]
        with self.assertRaisesRegex(ValueError, 'physical output folder'):
            p.export_config(node['id'], {**node['export_config'], 'folder_id': frame['id']})
        p.folder('Outputs')
        folder = p.data['nodes'][-1]
        p.export_config(node['id'], {**node['export_config'], 'folder_id': folder['id'], 'scene': 'Scene'})
        with patch.object(p, 'inspect'), patch.object(p, 'run', side_effect=ValueError('Export cancelled')):
            with self.assertRaisesRegex(ValueError, 'cancelled'):
                p.export_start(node['id'])
        self.assertEqual(p.data['exports'][-1]['status'], 'Failed')
        self.assertFalse(list((p.root / '.pipeline').glob('export-*')))

    def test_export_options_persist_and_partial_range_checks_scene_limits(self):
        p = self.pipeline
        source = self.source()
        p.folder('Outputs')
        folder = p.data['nodes'][-1]
        p.export_node(source_id=source['id'])
        node = p.data['nodes'][-1]
        config = {**node['export_config'], 'scene': 'Scene', 'folder_id': folder['id'],
                  'format': 'ALEMBIC', 'animation': True, 'start': 2,
                  'options': {'ALEMBIC': {'face_sets': True, 'xsamples': 2}, 'FBX': {'global_scale': 2}}}
        p.export_config(node['id'], config)
        saved_id = node['id']
        p.load(p.root)
        node = p.node(saved_id)
        self.assertEqual(node['export_config']['options'], config['options'])
        def worker(script, args, opened):
            payload = json.loads(Path(args[0]).read_text())
            self.assertEqual(payload['options']['ALEMBIC']['xsamples'], 2)
            self.assertIsNone(payload['end'])
            Path(args[1]).write_bytes(b'animation cache')
        with patch.object(p, 'inspect'), patch.object(p, 'run', side_effect=worker):
            p.export_start(saved_id)
        run = p.data['exports'][-1]
        self.assertEqual(run['timing']['start'], 2)
        self.assertEqual(run['timing']['end'], 3)
        self.assertTrue(run['format_options']['face_sets'])
        self.assertTrue(run['format_options']['normals'])
        self.assertIsNone(node['export_config']['end'])
        p.export_config(saved_id, {**config, 'start': 4})
        with patch.object(p, 'inspect'), self.assertRaisesRegex(ValueError, 'saved scene limits'):
            p.export_start(saved_id)
        self.assertEqual(len(p.data['exports']), 1)


if __name__ == '__main__':
    unittest.main()
