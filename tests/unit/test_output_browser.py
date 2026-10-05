"""Output navigation, safe file references, lazy previews and authenticated media."""
import copy
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from blender_pipeline.bootstrap import create_application
from blender_pipeline.http.server import create_server
from blender_pipeline.rendering.output_browser import OutputBrowser


class OutputBrowserTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='pipeline-output-test-')
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / 'Project'
        self.directory = self.root / 'Outputs' / 'Scene_r002'
        self.directory.mkdir(parents=True)
        self.run = {'id': 'r2', 'number': 2, 'status': 'Cancelled',
                    'output': 'Outputs/Scene_r002', 'config': {'prefix': '261005_Scene_'}}
        self.model = SimpleNamespace(root=self.root, data={'renders': [self.run]},
                                     runtime=Mock(), blender='test-blender')
        self.browser = OutputBrowser(self.model, self.base / 'settings')

    def put(self, name, content=b'image'):
        path = self.directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def test_selected_version_lists_final_and_compositor_saved_frames_only(self):
        for frame in [-1, 1, 3, 5]:
            self.put('261005_Scene_' + (('-' + str(abs(frame)).zfill(4)) if frame < 0 else str(frame).zfill(4)) + '.png')
        self.put('compositor/261005_Scene_Mist_0003.exr')
        self.put('preview.mp4')
        self.put('job.json')
        other = self.root / 'Outputs' / 'Scene_r001'
        other.mkdir(); (other / 'old_0001.png').write_bytes(b'old')
        result = self.browser.files(self.browser.version('r2'))
        images = next(s for s in result['sequences'] if s['format'] == 'PNG')
        self.assertEqual([f['frame'] for f in images['frames']], [-1, 1, 3, 5])
        self.assertTrue(all(f['path'].startswith('261005_') for f in images['frames']))
        mist = next(s for s in result['sequences'] if s['kind'] == 'compositor')
        self.assertEqual(mist['name'], 'Mist')
        self.assertEqual(mist['frames'][0]['path'], 'compositor/261005_Scene_Mist_0003.exr')
        self.assertTrue(next(s for s in result['sequences'] if s['format'] == 'MP4')['video'])
        self.assertFalse(result['truncated']); self.assertFalse(result['missing'])
        self.model.runtime.run.assert_not_called()

    def test_snapshot_is_detached_and_missing_or_deleted_versions_are_clear(self):
        version = self.browser.version('r2')
        self.run['config']['prefix'] = 'changed'
        self.assertEqual(version.run['config']['prefix'], '261005_Scene_')
        self.directory.rmdir()
        self.assertTrue(self.browser.files(version)['missing'])
        self.run['status'] = 'Deleted'
        with self.assertRaisesRegex(ValueError, 'unavailable'): self.browser.version('r2')

    def test_file_and_version_references_cannot_escape_render_outputs(self):
        self.put('safe.png')
        version = self.browser.version('r2')
        for value in ['../other.png', '/outside.png', 'C:/outside.png', 'compositor\\file.png', 'job.json', '', None]:
            with self.subTest(value=value), self.assertRaises(ValueError): self.browser.file(version, value)
        for directory in ['.', '../Outside', '.pipeline/private', str(self.base / 'Outside')]:
            self.run['output'] = directory
            with self.subTest(directory=directory), self.assertRaises(ValueError): self.browser.version('r2')

    def test_linked_paths_are_rejected_and_not_walked(self):
        self.put('safe.png')
        # Works on Windows without depending on symlink creation privileges.
        actual = Path.is_symlink
        with patch.object(Path, 'is_symlink', lambda p: p.name == 'linked' or actual(p)):
            (self.directory / 'linked').mkdir()
            (self.directory / 'linked' / 'hidden.png').write_bytes(b'outside')
            version = self.browser.version('r2')
            self.assertEqual(len(self.browser.files(version)['sequences']), 1)
            with self.assertRaisesRegex(ValueError, 'Linked'): self.browser.file(version, 'linked/hidden.png')

    def test_scan_is_bounded_even_for_empty_directory_trees(self):
        for i in range(8): (self.directory / str(i)).mkdir()
        with patch('blender_pipeline.rendering.output_browser.MAX_FILES', 3):
            self.assertTrue(self.browser.files(self.browser.version('r2'))['truncated'])

    def test_native_images_are_served_without_conversion_or_project_writes(self):
        source = self.put('final.png', b'png bytes')
        version = self.browser.version('r2')
        result = self.browser.preview(version, 'final.png')
        self.assertEqual(result.path, source); self.assertEqual(result.content_type, 'image/png')
        self.model.runtime.run.assert_not_called(); self.assertFalse(self.browser.cache.exists())
        with patch('blender_pipeline.rendering.output_browser.MAX_MEDIA_BYTES', 3):
            with self.assertRaisesRegex(ValueError, 'too large'): self.browser.preview(version, 'final.png')

    def test_exr_is_cached_outside_project_and_refreshed_when_source_changes(self):
        source = self.put('compositor/Mist_0001.exr', b'original exr')
        self.run['actual_settings'] = {'advanced': None, 'color_management': {'["color","exposure"]': 1.5}}
        def convert(blender, script, args):
            self.assertEqual(script, 'preview_image.py')
            job = json.loads(Path(args[0]).read_text())
            self.assertEqual(job['source'], str(source))
            self.assertEqual(job['color']['["color","exposure"]'], 1.5)
            Path(job['output']).write_bytes(b'display png')
        self.model.runtime.run.side_effect = convert
        before = copy.deepcopy(self.model.data)
        first = self.browser.preview(self.browser.version('r2'), 'compositor/Mist_0001.exr')
        second = self.browser.preview(self.browser.version('r2'), 'compositor/Mist_0001.exr')
        self.assertEqual(first.path, second.path); self.assertEqual(self.model.runtime.run.call_count, 1)
        self.assertFalse(first.path.is_relative_to(self.root))
        self.assertEqual(source.read_bytes(), b'original exr'); self.assertEqual(self.model.data, before)
        source.write_bytes(b'updated exr pixels')
        third = self.browser.preview(self.browser.version('r2'), 'compositor/Mist_0001.exr')
        self.assertNotEqual(first.path, third.path); self.assertEqual(self.model.runtime.run.call_count, 2)
        self.assertEqual(len(list(self.directory.rglob('*'))), 2)

    def test_preview_cache_is_bounded(self):
        self.browser.cache.mkdir(parents=True)
        for i in range(70): (self.browser.cache / (str(i) + '.png')).write_bytes(b'image')
        keep = self.browser.cache / '69.png'
        self.browser._trim_cache(keep)
        self.assertLessEqual(len(list(self.browser.cache.glob('*.png'))), 64)
        self.assertTrue(keep.exists())


class OutputHttpTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='pipeline-media-http-')
        self.addCleanup(self.temporary.cleanup)
        base = Path(self.temporary.name)
        self.app = create_application(base / 'settings', package_addon=False)
        self.addCleanup(self.app.tasks.pool.shutdown)
        p = self.app.model
        p.create(base, 'Project')
        directory = p.root / 'Outputs' / 'r001'; directory.mkdir(parents=True)
        (directory / 'image.png').write_bytes(b'\x89PNG\r\n\x1a\nactual saved bytes')
        p.data['renders'] = [{'id': 'run', 'status': 'Complete', 'number': 1, 'output': 'Outputs/r001', 'config': {}}]
        p.save()
        self.http = create_server(self.app, 'test-token')
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True); self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.http.shutdown(); self.http.server_close(); self.thread.join(5)

    def call(self, action, args, token='test-token'):
        request = urllib.request.Request('http://127.0.0.1:' + str(self.http.server_port) + '/' + action,
                                         data=json.dumps(args).encode(),
                                         headers={'Content-Type': 'application/json', 'X-Pipeline-Token': token})
        return urllib.request.urlopen(request, timeout=10)

    def test_context_checked_read_and_binary_response_do_not_change_revision(self):
        p = self.app.model; before = p.data['revision']
        args = {'project_id': p.data['id'], 'run_id': 'run'}
        with self.call('output_files', args) as response:
            self.assertEqual(len(json.load(response)['sequences']), 1)
        with self.call('output_image', {**args, 'path': 'image.png'}) as response:
            self.assertEqual(response.headers['Content-Type'], 'image/png')
            self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
            data = response.read(); self.assertEqual(len(data), int(response.headers['Content-Length']))
            self.assertTrue(data.startswith(b'\x89PNG'))
        self.assertEqual(p.data['revision'], before)
        for values, token in [({**args, 'project_id': 'other'}, 'test-token'), ({**args, 'path': '../private.png'}, 'test-token'), ({**args, 'path': 'image.png'}, 'wrong')]:
            with self.assertRaises(urllib.error.HTTPError): self.call('output_image', values, token)
        with self.assertRaises(urllib.error.HTTPError): urllib.request.urlopen('http://127.0.0.1:' + str(self.http.server_port) + '/output_image?path=image.png')

    def test_frame_abort_does_not_send_second_http_response(self):
        from blender_pipeline.http.server import Handler
        from blender_pipeline.rendering.output_browser import OutputMedia
        path = self.app.model.root / 'Outputs/r001/image.png'
        handler = Handler.__new__(Handler)
        handler.server = SimpleNamespace(token='test-token', application=SimpleNamespace(dispatch=lambda *args: OutputMedia(path, 'image/png')))
        handler.path = '/output_image'; handler.headers = {'X-Pipeline-Token': 'test-token', 'Content-Length': '2'}
        import io
        handler.rfile = io.BytesIO(b'{}'); handler.wfile = Mock()
        handler.wfile.write.side_effect = ConnectionResetError('cancelled')
        handler.send_response = Mock(); handler.send_header = Mock(); handler.end_headers = Mock()
        handler.dispatch_post()
        handler.send_response.assert_called_once_with(200)


if __name__ == '__main__': unittest.main()
