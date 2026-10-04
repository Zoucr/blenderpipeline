"""Two local adapters must not share tokens, settings or application state."""
import json
from html.parser import HTMLParser
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

from blender_pipeline.application.commands import Application
from blender_pipeline.http.server import create_server


class PageResources(HTMLParser):
    """Check the URLs the browser will request, rather than hardcoded asset paths."""
    def __init__(self):
        super().__init__()
        self.scripts = []
        self.stylesheets = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'script' and attrs.get('src'):
            self.scripts.append(attrs['src'])
        if tag == 'link' and 'stylesheet' in attrs.get('rel', '').split():
            self.stylesheets.append(attrs['href'])


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
                    resources = PageResources()
                    resources.feed(body)
                    self.assertEqual(resources.scripts[0], '/js/ui_runtime.js')
                    self.assertEqual(resources.scripts[-1], '/js/app_bootstrap.js')
                    self.assertTrue(resources.stylesheets, 'The page must declare its stylesheets.')
                    for routes, mimes in ((resources.scripts, ('text/javascript', 'application/javascript')),
                                          (resources.stylesheets, ('text/css',))):
                        for route in routes:
                            with self.subTest(resource=route):
                                with urllib.request.urlopen(f'http://127.0.0.1:{http.server_port}{route}') as response:
                                    self.assertEqual(response.status, 200)
                                    self.assertIn(response.headers.get_content_type(), mimes)
                                    self.assertTrue(response.read(), 'Page resources must not be empty.')
            finally:
                for http in servers:
                    http.shutdown()
                    http.server_close()
                for thread in threads:
                    thread.join(timeout=5)
