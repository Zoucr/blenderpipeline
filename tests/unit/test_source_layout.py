"""The source checkout runs independently of the old output folder or user data."""
import ast
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile

from blender_pipeline.adapters.addon_package import build_addon
from blender_pipeline.bootstrap import create_application
from blender_pipeline.http.server import create_server
from blender_pipeline.paths import SOURCE_ROOT


class SourceLayoutTests(unittest.TestCase):
    def test_entry_point_works_from_another_directory_without_writing_data(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / 'settings'
            environment = dict(os.environ, PIPELINE_DATA_DIR=str(data))
            result = subprocess.run([sys.executable, '-B', str(SOURCE_ROOT / 'run.py'), '--help'],
                                    cwd=directory, env=environment, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('--data-dir', result.stdout)
            self.assertFalse(data.exists())

    def test_importing_http_does_not_construct_an_application_or_write_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / 'settings'
            environment = dict(os.environ, PYTHONPATH=str(SOURCE_ROOT / 'src'), PIPELINE_DATA_DIR=str(data))
            result = subprocess.run([sys.executable, '-B', '-c',
                                     'from blender_pipeline.http import server; assert not hasattr(server, "model")'],
                                    cwd=directory, env=environment, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(data.exists())

    def test_bootstrap_settings_and_download_are_isolated(self):
        with tempfile.TemporaryDirectory() as directory:
            first = create_application(Path(directory) / 'first')
            second = create_application(Path(directory) / 'second')
            try:
                self.assertNotEqual(first.model.registry, second.model.registry)
                self.assertEqual(first.model.global_template_config.parent, first.settings_directory)
                self.assertEqual(first.model.resolver.directory, first.settings_directory)
                self.assertTrue(first.addon_archive.is_relative_to(first.settings_directory))
                self.assertFalse(first.model.registry.exists())
            finally:
                first.tasks.pool.shutdown()
                second.tasks.pool.shutdown()

    def test_generated_companion_contains_only_sources_and_no_machine_specific_path(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = build_addon(Path(directory) / 'Companion.zip')
            with zipfile.ZipFile(archive) as package:
                self.assertEqual(set(package.namelist()), {'pipeline_companion/__init__.py', 'pipeline_companion/material_assistant.py', 'pipeline_companion/blender_linking.py'})
                source = package.read('pipeline_companion/__init__.py').decode()
                self.assertNotIn('__PIPELINE_CONNECTION__', source)
                self.assertNotIn(str(SOURCE_ROOT), source)
                self.assertIn('default_connection()', source)
            self.assertFalse(archive.with_suffix('.zip.tmp').exists())

    def test_all_python_source_and_blender_fixtures_parse(self):
        for directory in ('src', 'addon', 'scripts', 'tests'):
            for file in (SOURCE_ROOT / directory).rglob('*.py'):
                with self.subTest(file=file.relative_to(SOURCE_ROOT)):
                    ast.parse(file.read_text(encoding='utf-8'), filename=str(file))

    def test_static_source_and_private_resources_cannot_be_served(self):
        with tempfile.TemporaryDirectory() as directory:
            app = create_application(Path(directory) / 'settings')
            http = create_server(app, 'test-token')
            thread = threading.Thread(target=http.serve_forever, daemon=True)
            thread.start()
            url = f'http://127.0.0.1:{http.server_port}'
            try:
                for route in ('/js/ui_runtime.js', '/css/base.css', '/icons/file_blend.svg', '/Pipeline_Companion.zip'):
                    with urllib.request.urlopen(url + route) as response:
                        self.assertEqual(response.status, 200)
                for route in ('/js/../../README.md', '/icons/COPYING', '/src/blender_pipeline/paths.py'):
                    with self.assertRaises(urllib.error.HTTPError) as blocked:
                        urllib.request.urlopen(url + route)
                    self.assertEqual(blocked.exception.code, 404)
            finally:
                http.shutdown()
                http.server_close()
                thread.join(5)
                app.tasks.pool.shutdown()
