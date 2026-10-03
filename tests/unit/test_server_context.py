"""Two local adapters must not share tokens, settings or application state."""
import json
import re
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

from blender_pipeline.application.commands import Application
from blender_pipeline.http.server import create_server


class ServerContextTests(unittest.TestCase):
    def test_two_bound_contexts_are_independent(self):
        with tempfile.TemporaryDirectory() as directory:
            servers = []
            threads = []
            try:
                for title in ('first', 'second'):
                    settings = Path(directory) / title
                    settings.mkdir()
                    tasks = SimpleNamespace(state=lambda title=title: {'project': title}, active=lambda: False)
                    app = Application(SimpleNamespace(), tasks, SimpleNamespace(), settings)
                    http = create_server(app, title + '-token')
                    thread = threading.Thread(target=http.serve_forever, daemon=True)
                    servers.append(http)
                    threads.append(thread)
                    thread.start()

                def call(index, action, args, token=None):
                    http = servers[index]
                    request = urllib.request.Request(f'http://127.0.0.1:{http.server_port}/{action}',
                        data=json.dumps(args).encode(), headers={'X-Pipeline-Token': token or http.token})
                    return json.loads(urllib.request.urlopen(request, timeout=10).read())

                self.assertEqual(call(0, 'state', {})['project'], 'first')
                self.assertEqual(call(1, 'state', {})['project'], 'second')
                prefs = {'navigator': True, 'inspector': False, 'width': 400}
                call(0, 'ui_preferences', prefs)
                self.assertEqual(call(0, 'ui_preferences', {'read': True}), prefs)
                self.assertEqual(call(1, 'ui_preferences', {'read': True}), {})
                with self.assertRaises(urllib.error.HTTPError) as rejected:
                    call(1, 'state', {}, token=servers[0].token)
                self.assertEqual(rejected.exception.code, 403)
                with self.assertRaises(urllib.error.HTTPError) as invalid:
                    call(0, 'state', [])
                self.assertEqual(invalid.exception.code, 400)
                for http in servers:
                    body = urllib.request.urlopen(f'http://127.0.0.1:{http.server_port}/').read().decode()
                    self.assertIn(http.token, body)
                    self.assertNotIn('__TOKEN__', body)
                    scripts = re.findall(r"<script src='([^']+)'", body)
                    self.assertEqual(scripts[0], '/js/ui_runtime.js')
                    self.assertEqual(scripts[-1], '/js/app_bootstrap.js')
                    for script in scripts:
                        with urllib.request.urlopen(f'http://127.0.0.1:{http.server_port}{script}') as response:
                            self.assertEqual(response.status, 200)
            finally:
                for http in servers:
                    http.shutdown()
                    http.server_close()
                for thread in threads:
                    thread.join(timeout=5)
