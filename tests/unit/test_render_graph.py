"""Scene operations and dependency observations without launching Blender."""
import copy
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from blender_pipeline.project.workspace import Pipeline
from blender_pipeline.project.model import Pipeline as BasePipeline, digest
from blender_pipeline.project.dependencies import dependency_health, file_signature


class RenderGraphTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        (self.base / 'settings').mkdir()
        self.pipeline = Pipeline(data_directory=self.base / 'settings')
        self.pipeline.create(self.base, 'Tests')
        self.pipeline.queue_worker = object()  # Inspect atomic submissions before execution.

    def tearDown(self):
        self.temp.cleanup()

    def source(self, identity, refs=None):
        p = self.pipeline
        path = p.root / (identity + '.blend')
        path.write_bytes(identity.encode())
        scene = {'name': 'Scene', 'camera': 'Camera', 'cameras': ['Camera'], 'start': 1, 'end': 2,
                 'width': 32, 'height': 24, 'engine': 'CYCLES', 'samples': 5, 'current_frame': 2,
                 'active_view_layer': 'Beauty', 'view_layers': [{'name': 'Beauty', 'enabled': True}, {'name': 'Mask', 'enabled': True}],
                 'use_compositing': False, 'compositor_dependencies': []}
        node = {'id': identity, 'type': 'blend', 'name': identity, 'path': path.name, 'x': 0, 'y': 0,
                'scan': {'hash': digest(path), 'signature': file_signature(path), 'refs': refs or [],
                         'scenes': [scene, {**scene, 'name': 'Detail', 'start': 4, 'end': 4}],
                         'datablocks': [{'kind': 'collections', 'name': 'Models'}]}, 'snapshots': []}
        p.data['nodes'].append(node)
        return node

    def library(self, source):
        return {'kind': 'Library', 'path': str(self.pipeline.path(source)), 'exists': True,
                'relative': True, 'inside': True, 'raw': '//' + source['path']}

    def operation(self, sources):
        p = self.pipeline
        p.folder('Outputs')
        folder = p.data['nodes'][-1]
        p.render_node(source_ids=[s['id'] for s in sources])
        operation = p.data['nodes'][-1]
        p.render_node_config(operation['id'], {**operation['render_plan'], 'folder_id': folder['id']})
        return operation, folder

    def test_multiple_scenes_capture_actual_file_refs_and_override_precedence(self):
        p = self.pipeline
        a, b = self.source('A'), self.source('B')
        operation, folder = self.operation([a, b])
        plan = copy.deepcopy(operation['render_plan'])
        plan['targets'][0]['overrides'] = {'width': 16, 'samples': 10}
        plan['targets'][1]['overrides'] = {'width': 48}
        plan['targets'].append({**plan['targets'][0], 'id': 'detail', 'scene': 'Detail', 'overrides': {}})
        plan['overrides'] = {'samples': 2}
        p.render_node_config(operation['id'], plan)
        with patch.object(p, 'refresh'):
            p.queue_render_node(operation['id'])
        jobs = p.data['render_queue']
        self.assertEqual(len(jobs), 3)
        self.assertEqual(len({q['target_key'] for q in jobs}), 3)
        self.assertEqual([q['node_id'] for q in jobs], ['A', 'B', 'A'])
        self.assertEqual([q['effective_settings'].get('width') for q in jobs], [16, 48, None])
        self.assertTrue(all(q['effective_settings']['samples'] == 2 for q in jobs))
        self.assertEqual(jobs[-1]['effective_settings']['start'], 4)
        self.assertEqual(jobs[0]['file_ref']['file_id'], 'A')
        self.assertEqual(jobs[0]['settings']['output_subfolder'], 'A/Scene/Beauty')
        self.assertEqual(len(p.render_targets(folder['id'])), 3)
        self.assertNotIn('path', operation)
        with self.assertRaisesRegex(ValueError, 'no file'):
            p.path(operation)
        with patch.object(p, 'refresh'), self.assertRaisesRegex(ValueError, 'already queued'):
            p.queue_render('A', settings=jobs[0]['settings'])
        self.assertEqual(len(jobs), 3)
        plan['overrides']['samples'] = 90
        self.assertEqual(jobs[0]['effective_settings']['samples'], 2)

    def test_invalid_target_rejects_entire_batch_and_explicit_conversion_preserves_settings(self):
        p = self.pipeline
        a, b = self.source('A'), self.source('B')
        operation, folder = self.operation([a, b])
        plan = copy.deepcopy(operation['render_plan'])
        plan['targets'][-1]['camera'] = 'Missing'
        p.render_node_config(operation['id'], plan)
        with patch.object(p, 'refresh'), self.assertRaisesRegex(ValueError, 'camera'):
            p.queue_render_node(operation['id'])
        self.assertFalse(p.data.get('render_queue'))
        original = {'folder_id': folder['id'], 'scene': 'Detail', 'camera': 'Camera', 'samples': 12, 'auto_prefix': False, 'prefix': 'keep_'}
        a['render_config'] = copy.deepcopy(original)
        p.render_node(source_ids=['A'])
        self.assertEqual(a['render_config'], original)
        p.render_node(source_ids=['A'], adopt_existing=True)
        converted = p.data['nodes'][-1]
        self.assertNotIn('render_config', a)
        self.assertEqual(converted['render_plan']['folder_id'], folder['id'])
        self.assertEqual(converted['render_plan']['targets'][0]['overrides'], {'samples': 12})
        self.assertEqual(converted['render_plan']['targets'][0]['scene'], 'Detail')
        self.assertEqual(converted['render_plan']['targets'][0]['prefix'], 'keep_')
        with self.assertRaisesRegex(ValueError, 'one existing'):
            p.render_node(source_ids=['A', 'B'], adopt_existing=True)

    def test_four_layer_setups_individual_disabled_render_and_stable_readable_directories(self):
        p = self.pipeline
        a = self.source('A')
        operation, _ = self.operation([a])
        plan = copy.deepcopy(operation['render_plan'])
        original = plan['targets'][0]
        self.assertEqual(original['view_layer'], 'Beauty')
        for identity, scene, layer in [('mask', 'Scene', 'Mask'), ('detail', 'Detail', 'Beauty'), ('detail-mask', 'Detail', 'Mask')]:
            plan['targets'].append({**original, 'id': identity, 'scene': scene, 'view_layer': layer})
        plan['targets'][1]['enabled'] = False
        plan['targets'][2].update(mode='STILL', frame=None)
        p.render_node_config(operation['id'], plan)
        self.assertEqual(len({t['output_subfolder'] for t in operation['render_plan']['targets']}), 4)
        self.assertEqual(operation['render_plan']['targets'][1]['output_subfolder'], 'A/Scene/Mask')
        with patch.object(p, 'refresh'):
            p.queue_render_node(operation['id'], target_ids=['mask'])
            p.queue_render_node(operation['id'])
        jobs = p.data['render_queue']
        self.assertEqual(len(jobs), 4)
        self.assertEqual(jobs[0]['effective_settings']['view_layers'], ['Mask'])
        still = next(q for q in jobs if q['target_id'] == 'detail')
        self.assertEqual(still['effective_settings']['start'], 2)
        self.assertEqual(still['effective_settings']['end'], 2)
        saved = copy.deepcopy(operation['render_plan'])
        old_path = saved['targets'][0]['output_subfolder']
        saved['targets'][0]['label'] = 'Final beauty'
        saved['targets'].append({**saved['targets'][0], 'id': 'variant', 'label': ''})
        p.render_node_config(operation['id'], saved)
        self.assertEqual(operation['render_plan']['targets'][0]['output_subfolder'], old_path)
        self.assertEqual(operation['render_plan']['targets'][-1]['output_subfolder'], 'A/Scene/Beauty_02')
        saved = copy.deepcopy(operation['render_plan'])
        saved['targets'] = []
        p.render_node_config(operation['id'], saved)
        self.assertEqual(operation['render_plan']['source_ids'], ['A'])
        self.assertEqual(len(p.data['render_queue']), 4)  # Submitted jobs keep their setup.

    def test_compositor_conflicts_and_missing_layers_reject_the_whole_batch(self):
        p = self.pipeline
        a = self.source('A')
        scene = a['scan']['scenes'][0]
        scene.update(use_compositing=True, compositor_dependencies=[{'scene': 'Scene', 'view_layer': 'Mask'}])
        operation, _ = self.operation([a])
        with patch.object(p, 'refresh'), self.assertRaisesRegex(ValueError, 'Compositor needs Scene / Mask'):
            p.queue_render_node(operation['id'])
        self.assertFalse(p.data.get('render_queue'))
        plan = copy.deepcopy(operation['render_plan'])
        plan['targets'][0]['view_layer'] = 'Missing'
        p.render_node_config(operation['id'], plan)
        self.assertTrue(any(r['kind']=='missing_layer' for r in p.state()['health']['nodes'][operation['id']]['reasons']))
        with patch.object(p, 'refresh'), self.assertRaisesRegex(ValueError, 'View layer missing'):
            p.queue_render_node(operation['id'])
        self.assertFalse(p.data.get('render_queue'))
        plan['targets'][0].update(view_layer='Beauty', compositor='OFF')
        p.render_node_config(operation['id'], plan)
        with patch.object(p, 'refresh'):p.queue_render_node(operation['id'])
        self.assertFalse(p.data['render_queue'][-1]['effective_settings']['use_compositing'])
        p.data['render_queue'] = []
        plan['targets'][0].update(view_layer='', compositor='BLENDER')
        p.render_node_config(operation['id'], plan)
        with patch.object(p, 'refresh'):p.queue_render_node(operation['id'])
        self.assertEqual(p.data['render_queue'][-1]['effective_settings']['view_layers'], ['Beauty', 'Mask'])

    def test_missing_source_can_be_removed_without_deleting_other_setups(self):
        p = self.pipeline
        a, b = self.source('A'), self.source('B')
        operation, _ = self.operation([a, b])
        p.data['nodes'].remove(a)
        with patch.object(p, 'refresh'), self.assertRaisesRegex(ValueError, 'missing source file'):
            p.queue_render_node(operation['id'])
        self.assertFalse(p.data.get('render_queue'))
        plan = copy.deepcopy(operation['render_plan'])
        plan['targets'] = [t for t in plan['targets'] if t['source_id'] != 'A']
        p.render_node_config(operation['id'], plan)
        self.assertEqual(len(operation['render_plan']['targets']), 1)

    def test_folder_recovery_and_companion_do_not_replace_render_plan(self):
        p = self.pipeline
        a = self.source('A')
        operation, folder = self.operation([a])
        p.archive_folder(folder['id'], confirmed=True)
        self.assertIsNone(operation['render_plan']['folder_id'])
        p.restore_folder(p.data['archived_folders'][-1]['id'])
        self.assertEqual(operation['render_plan']['folder_id'], folder['id'])
        plan = copy.deepcopy(operation['render_plan'])
        with patch.object(p, 'refresh'):
            p.companion_render('A', 'Scene', 'Camera', 1, 1)
        self.assertEqual(operation['render_plan'], plan)
        self.assertNotIn('render_config', a)
        job = p.data['render_queue'][-1]
        self.assertEqual(job['operation_id'], operation['id'])
        self.assertEqual(job['settings']['folder_id'], folder['id'])
        with self.assertRaisesRegex(ValueError, 'jobs before removing'):
            p.remove_graph_node(operation['id'], confirmed=True)

    def test_saved_refresh_keeps_pending_library_change_until_target_is_saved(self):
        p = self.pipeline
        a = self.source('A')
        b = self.source('B', [self.library(a)])
        b['dependency_hashes'] = {'A': a['scan']['hash']}
        old_hash = a['scan']['hash']
        p.path(a).write_bytes(b'new source state')
        a['scan'].update(hash=digest(p.path(a)), signature=file_signature(p.path(a)))
        def scan(_self, node):
            node['scan'] = copy.deepcopy(node['scan'])
            node['scan']['hash'] = digest(p.path(node))
        with patch.object(BasePipeline, 'inspect', scan):
            p.inspect(b)
            self.assertEqual(b['dependency_hashes']['A'], old_hash)
            p.path(b).write_bytes(b'saved destination state')
            p.inspect(b)
            self.assertEqual(b['dependency_hashes']['A'], a['scan']['hash'])

    def test_transitive_impact_missing_assets_dirty_inputs_and_output_freshness(self):
        p = self.pipeline
        a = self.source('A')
        b = self.source('B', [self.library(a)])
        c = self.source('C', [self.library(b)])
        b['dependency_hashes'] = {'A': a['scan']['hash']}
        c['dependency_hashes'] = {'B': b['scan']['hash']}
        b['scan']['instances'] = [{'source': str(p.path(a)), 'collection': 'Models'}]
        operation, _ = self.operation([c])
        p.data['renders'] = [{'id': 'old', 'status': 'Complete', 'node_id': 'C',
                              'input_hashes': {n['path']: n['scan']['hash'] for n in [a, b, c]},
                              'input_signatures': {n['path']: file_signature(p.path(n)) for n in [a, b, c]}}]
        self.assertFalse(dependency_health(p, {})['outputs']['renders']['old']['outdated'])
        p.path(a).write_bytes(b'updated source')
        a['scan'].update(hash=digest(p.path(a)), signature=file_signature(p.path(a)), datablocks=[])
        p.companion = Mock()
        p.companion.opened.side_effect = lambda path: [{'dirty': True}] if path == p.path(a) else []
        before = copy.deepcopy(p.data)
        result = dependency_health(p, {})
        self.assertEqual(p.data, before)  # Read-only status checks.
        self.assertEqual(result['nodes']['A']['affected'], ['B', 'C'])
        self.assertTrue({'asset_missing', 'unsaved_upstream', 'source_updated'} <= {r['kind'] for r in result['nodes']['B']['reasons']})
        self.assertTrue({'unsaved_upstream', 'source_updated'} <= {r['kind'] for r in result['nodes'][operation['id']]['reasons']})
        self.assertEqual(result['outputs']['renders']['old']['changed_inputs'], ['A.blend'])
        self.assertEqual(result['outputs']['renders']['old']['unsaved_inputs'], ['A.blend'])
        a['scan']['refs'] = [self.library(c)]  # A cycle must terminate.
        self.assertEqual(dependency_health(p, {})['nodes']['A']['upstream'], ['B', 'C'])


if __name__ == '__main__':
    unittest.main()
