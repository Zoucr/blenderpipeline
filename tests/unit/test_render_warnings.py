"""Per-submission image consent, atomic batches and retained required-input guards."""
import copy
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from blender_pipeline.application.tasks import Tasks
from blender_pipeline.project.workspace import Pipeline
from blender_pipeline.project.model import digest
from blender_pipeline.rendering.inputs import RenderImageWarnings
from blender_pipeline.blender.render_resources import restore_warning_images, restore_image_inputs
from blender_pipeline.rendering.images import image_identity, freeze_images
from blender_pipeline.blender.image_usage import classify_images


class RenderWarningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        (self.base / 'settings').mkdir()
        self.p = Pipeline(data_directory=self.base / 'settings')
        self.p.create(self.base, 'Warnings')
        self.p.folder('Outputs')
        self.folder = self.p.data['nodes'][-1]
        self.p.queue_worker = object()
        self.refresh = patch.object(self.p, 'refresh')
        self.refresh.start()

    def tearDown(self):
        self.refresh.stop(); self.temp.cleanup()

    def source(self, identity='Shot', refs=None):
        p = self.p; path = p.root / (identity + '.blend'); path.write_bytes(identity.encode())
        node = {'id': identity, 'type': 'blend', 'name': identity, 'path': path.name, 'x': 0, 'y': 0, 'snapshots': [],
                'scan': {'hash': digest(path), 'signature': [path.stat().st_mtime_ns, path.stat().st_size], 'refs': refs or [],
                         'scenes': [{'name': 'Scene', 'camera': 'Camera', 'cameras': ['Camera'], 'start': 1, 'end': 1,
                                     'width': 16, 'height': 16, 'engine': 'CYCLES', 'samples': 1, 'current_frame': 1}]}}
        p.data['nodes'].append(node)
        p.render_config(identity, self.folder['id'], 'Scene')
        return node

    def image(self, title='unused_ALPHA.png', kind='Image', relative=True, external=False):
        path = (self.base if external else self.p.root) / title
        return {'kind': kind, 'path': str(path), 'name': title, 'raw': ('//' if relative else '') + title,
                'exists': path.is_file(), 'pattern': False, 'inside': not external, 'relative': relative}

    def test_warnings_require_consent_without_partial_jobs_or_node_error(self):
        p = self.p; node = self.source(refs=[self.image()])
        before = copy.deepcopy(node['render_config'])
        with self.assertRaises(RenderImageWarnings) as caught: p.queue_render(node['id'])
        warning = caught.exception.dependency_warnings[0]
        self.assertIn('unused_ALPHA.png', warning['path']); self.assertIn('missing', warning['reason'])
        self.assertFalse(p.data.get('render_queue')); self.assertFalse(p.data.get('renders')); self.assertNotIn('last_error', node)
        p.queue_render(node['id'], allow_image_warnings=True, accepted_image_warnings=[warning])
        queued = p.data['render_queue'][-1]
        self.assertEqual(queued['dependency_warnings'], [warning]); self.assertTrue(queued['allow_image_warnings'])
        self.assertEqual(queued['expected_inputs'], {node['path']: digest(p.path(node))})
        self.assertEqual(node['render_config'], before); self.assertFalse(list(p.path(self.folder).iterdir()))
        p.data['render_queue'] = []
        with self.assertRaises(RenderImageWarnings): p.queue_render(node['id'])
        # Export/portable capture keeps its strict existing contract.
        with self.assertRaises(ValueError) as strict: p.capture_render_inputs(node)
        self.assertNotIsInstance(strict.exception, RenderImageWarnings)

    def test_confirmed_render_node_and_direct_preparation_keep_the_warning_manifest(self):
        p = self.p; node = self.source(refs=[self.image(relative=False, external=True)])
        p.render_node(source_ids=[node['id']]); operation = p.data['nodes'][-1]
        p.render_node_config(operation['id'], {**operation['render_plan'], 'folder_id': self.folder['id']})
        with self.assertRaises(RenderImageWarnings): p.queue_render_node(operation['id'])
        p.queue_render_node(operation['id'], allow_image_warnings=True)
        queued = p.data['render_queue'][-1]
        with patch.object(p, 'monitor_render'), patch('blender_pipeline.project.workspace.subprocess.Popen') as start, patch('blender_pipeline.project.workspace.threading.Thread'):
            start.return_value.pid = 123
            start.return_value.poll.return_value = 0
            p.render_start(node['id'], settings=queued['effective_settings'], expected_inputs=queued['expected_inputs'],
                           allow_image_warnings=True, expected_image_warnings=queued['dependency_warnings'])
        run = p.data['renders'][-1]
        self.assertEqual(run['dependency_warnings'], queued['dependency_warnings'])
        import json
        job = json.loads((p.root / run['output'] / 'render-job.json').read_text(encoding='utf-8'))
        self.assertEqual(job['image_warnings'], run['dependency_warnings'])
        self.assertEqual(job['project_root'], str(p.root))

    def test_missing_libraries_and_other_resources_are_still_blocked_for_entire_batch(self):
        p = self.p; a = self.source('A', refs=[self.image()]); b = self.source('B', refs=[self.image('Missing.blend', kind='Library')])
        with self.assertRaisesRegex(ValueError, 'Missing.blend'): p.queue_batch(node_ids=[a['id'], b['id']], allow_image_warnings=True)
        self.assertFalse(p.data.get('render_queue'))
        b['scan']['refs'] = [self.image('Missing.ttf', kind='Font')]
        with self.assertRaisesRegex(ValueError, 'Missing.ttf'): p.queue_render(b['id'], allow_image_warnings=True)
        p.companion = SimpleNamespace(opened=lambda path: [{'dirty': True}])
        with self.assertRaisesRegex(ValueError, 'Save this render input'): p.queue_render(a['id'], allow_image_warnings=True)

    def test_new_warnings_need_new_consent_and_changed_queued_manifest_stops(self):
        p = self.p; node = self.source(refs=[self.image()]); warnings = []
        p.capture_render_inputs(node, allow_image_warnings=True, warnings=warnings)
        node['scan']['refs'].append(self.image('another_missing.png'))
        with self.assertRaises(RenderImageWarnings): p.queue_render(node['id'], allow_image_warnings=True, accepted_image_warnings=warnings)
        self.assertFalse(p.data.get('render_queue'))
        with self.assertRaisesRegex(ValueError, 'warnings changed'): p.render_start(node['id'], allow_image_warnings=True, expected_image_warnings=warnings)
        self.assertFalse(p.data.get('renders')); self.assertFalse(list(p.path(self.folder).iterdir()))
        with self.assertRaisesRegex(ValueError, 'consent'): p.queue_render(node['id'], allow_image_warnings='yes')

    def test_valid_absolute_and_external_images_are_collected_without_warning(self):
        p = self.p; (p.root / 'valid.png').write_bytes(b'image')
        valid = self.image('valid.png'); node = self.source(refs=[valid, self.image('valid.png', relative=False)])
        (self.base / 'external.png').write_bytes(b'external image')
        node['scan']['refs'].append(self.image('external.png', relative=False, external=True))
        warnings = []; images = []; manifest = p.capture_render_inputs(node, allow_image_warnings=True, warnings=warnings, images=images)
        self.assertEqual(manifest['valid.png'], digest(p.root / 'valid.png'))
        self.assertFalse(warnings); self.assertEqual(len({i['source_path'] for i in images}), 2)
        self.assertTrue(any(i['managed'] and i['target']=='valid.png' for i in images))
        self.assertEqual({Path(i['source_path']).name for i in images}, {'valid.png', 'external.png'})
        with self.assertRaises(ValueError): p.capture_render_inputs(node)

    def test_unused_missing_image_is_a_notice_and_unknown_use_still_needs_consent(self):
        p=self.p; ref=self.image();ref['image_usage']='unused';node=self.source(refs=[ref])
        p.queue_render(node['id'])
        queued=p.data['render_queue'][-1]
        self.assertFalse(queued['dependency_warnings']);self.assertEqual(queued['image_notices'][0]['severity'],'notice')
        self.assertFalse(queued['allow_image_warnings'])
        p.data['render_queue']=[];ref['image_usage']='unknown'
        with self.assertRaises(RenderImageWarnings):p.queue_render(node['id'])
        ref['image_usage']='used'
        with self.assertRaises(RenderImageWarnings):p.queue_render(node['id'])

    def test_same_filename_images_have_distinct_frozen_paths_and_changes_block_launch(self):
        p=self.p; (self.base/'a').mkdir();(self.base/'b').mkdir()
        refs=[]
        for folder,content in [('a',b'green'),('b',b'blue')]:
            path=self.base/folder/'color.png';path.write_bytes(content)
            refs.append(dict(self.image('color.png',external=True),path=str(path),raw=str(path),relative=False))
        node=self.source(refs=refs);p.queue_render(node['id']);queued=p.data['render_queue'][-1]
        images=queued['image_inputs'];self.assertEqual(len({i['target'] for i in images}),2)
        inputs=p.root/'test-inputs';inputs.mkdir();freeze_images(p,images,inputs)
        self.assertEqual({(inputs/i['target']).read_bytes() for i in images},{b'green',b'blue'})
        Path(images[0]['source_path']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'images changed'):
            p.render_start(node['id'],expected_inputs=queued['expected_inputs'],expected_images=images)
        self.assertFalse(p.data.get('renders'))

    def test_located_replacement_is_portable_and_does_not_rewrite_working_files(self):
        p=self.p;node=self.source(refs=[self.image()]);before=digest(p.path(node))
        replacement=self.base/'replacement.png';replacement.write_bytes(b'replacement')
        p.locate_render_image(node['id'],node['scan']['refs'][0]['path'],str(replacement))
        replacement.unlink();images=[]
        p.capture_render_inputs(node,allow_image_warnings=False,images=images)
        self.assertTrue(images[0]['replacement']);self.assertTrue(images[0]['source_relative'].startswith('.pipeline/render-assets/'))
        self.assertEqual(digest(p.path(node)),before)
        with self.assertRaisesRegex(ValueError,'current scan'):p.locate_render_image(node['id'],str(self.base/'unrelated.png'),str(p.path(node)))
        with patch.object(p,'save',side_effect=ValueError('conflict')):
            other=self.base/'other.png';other.write_bytes(b'other')
            with self.assertRaisesRegex(ValueError,'conflict'):p.locate_render_image(node['id'],node['scan']['refs'][0]['path'],str(other))
        self.assertEqual(len(p.data['image_replacements']),1)

    def test_udim_members_are_frozen_and_an_unresolved_tile_is_reviewed(self):
        p=self.p
        files=[self.base/'color.1001.png',self.base/'color.1002.png']
        for path in files:path.write_bytes(path.name.encode())
        ref=dict(self.image('color.<UDIM>.png',external=True),pattern=True,image_source='TILED',image_files=[str(path) for path in files])
        node=self.source(refs=[ref]);images=[]
        p.capture_render_inputs(node,allow_image_warnings=False,images=images)
        self.assertEqual(len(images),2);self.assertEqual(images[0]['pattern_name'],'color.<UDIM>.png')
        files[1].unlink()
        with self.assertRaises(RenderImageWarnings):p.queue_render(node['id'])

    def test_collected_linked_image_uses_snapshot_after_original_disappears(self):
        p=self.p;frozen=p.root/'.pipeline'/'render-inputs'/'run';original=self.base/'green.png'
        image=SimpleNamespace(source='FILE',packed_file=None,library=object(),name='Green',filepath='//../green.png')
        target='.pipeline/images/id/green.png'
        restored=restore_image_inputs([image],{'input_root':str(frozen),'project_root':str(p.root),
            'image_inputs':[{'original_path':str(original),'target':target}]},lambda raw,library=None:str(frozen/raw.removeprefix('//')))
        self.assertEqual(image.filepath.removeprefix('\\\\?\\'),str(frozen/target));self.assertEqual(restored[0]['original'],str(original))

    def test_usage_detection_never_guesses_unknown_or_animated_consumers(self):
        class Item:
            def __init__(self,**kwargs):self.__dict__.update(kwargs)
        image=Item(users=1,use_fake_user=False,animation_data=None)
        node=Item(image=image,bl_idname='ShaderNodeTexImage',outputs=[SimpleNamespace(is_linked=False)])
        tree=Item(nodes=[node],animation_data=None);owner=Item(animation_data=None)
        users={image:{tree}};trees=[(owner,tree)]
        self.assertEqual(classify_images([image],trees,users)[image],'unused')
        node.outputs[0].is_linked=True;self.assertEqual(classify_images([image],trees,users)[image],'used')
        node.outputs[0].is_linked=False;tree.animation_data=object()
        self.assertEqual(classify_images([image],trees,users)[image],'unknown')
        tree.animation_data=None;users[image].add(Item())
        self.assertEqual(classify_images([image],trees,users)[image],'unknown')

    def test_async_warning_has_structured_details_without_persisting_a_file_failure(self):
        p = self.p; node = self.source(refs=[self.image()]); tasks = Tasks(p)
        try:
            job = {'id': 'request', 'node_id': node['id'], 'project_id': p.data['id'], 'action': 'queue_render', 'status': 'Queued', 'args': {}}
            tasks.jobs[job['id']] = job
            tasks.execute(job, {'node_id': node['id']}, p.queue_render)
            result = tasks.state()['jobs'][-1]
            self.assertEqual(result['error_code'], 'render_image_warnings'); self.assertTrue(result['dependency_warnings'])
            self.assertNotIn('last_error', p.node(node['id']))
        finally: tasks.pool.shutdown()

    def test_linked_relative_live_images_rebase_from_frozen_to_original_root(self):
        p = self.p; frozen = p.root / '.pipeline' / 'render-inputs' / 'run'
        original = self.base / 'live.png'
        image = SimpleNamespace(source='FILE', packed_file=None, library=object(), name='Live', filepath='//../live.png')
        good = SimpleNamespace(source='FILE', packed_file=None, library=None, name='Good', filepath='//valid.png')
        packed = SimpleNamespace(source='FILE', packed_file=True, library=None, name='Packed', filepath='//../live.png')
        abspath = lambda raw, library=None: str(frozen / raw.removeprefix('//'))
        restored = restore_warning_images([image, good, packed], {'input_root': str(frozen), 'project_root': str(p.root), 'image_warnings': [{'path': str(original)}]}, abspath)
        self.assertEqual(image.filepath, str(original)); self.assertEqual(good.filepath, '//valid.png')
        self.assertEqual(packed.filepath, '//../live.png'); self.assertEqual(restored, [{'name': 'Live', 'path': str(original)}])


if __name__ == '__main__': unittest.main()
