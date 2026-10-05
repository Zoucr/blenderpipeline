"""Loopback HTTP adapter. Application ownership is explicit; imports start nothing."""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import json
import os
from pathlib import Path
import threading
from urllib.parse import urlsplit

from blender_pipeline.paths import WEB_DIR
from blender_pipeline.rendering.output_browser import OutputMedia


class Handler(BaseHTTPRequestHandler):
    def handle(self):
        try:
            super().handle()
        except (ConnectionError, TimeoutError):
            self.close_connection = True  # Browser reloads/closing cancel requests.

    def setup(self):
        self.request.settimeout(15)
        super().setup()

    def do_GET(self):
        route = urlsplit(self.path).path
        root = self.server.asset_directory.resolve()
        if route == '/':
            body = (root / 'index.html').read_text(encoding='utf-8')
            body = body.replace('__TOKEN__', self.server.token).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)
            return

        if route == '/Pipeline_Companion.zip':
            path = getattr(self.server.application, 'addon_archive', None)
            if path is None or not Path(path).is_file():
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', 'application/zip')
            self.send_header('Content-Disposition', 'attachment; filename="Pipeline_Companion.zip"')
            self.end_headers()
            self.wfile.write(Path(path).read_bytes())
            return

        types = {'js': ('.js', 'text/javascript; charset=utf-8'),
                 'css': ('.css', 'text/css; charset=utf-8'),
                 'icons': ('.svg', 'image/svg+xml')}
        category = route.strip('/').split('/')[0]
        path = (root / route.lstrip('/')).resolve()
        if (category not in types or not path.is_relative_to(root / category)
                or path.suffix != types[category][0] or not path.is_file()):
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', types[category][1])
        self.send_header('Cache-Control', 'public, max-age=86400' if category == 'icons' else 'no-store')
        self.end_headers()
        self.wfile.write(path.read_bytes())

    def do_POST(self):
        lock = self.server.picker_lock if self.path == '/choose_system_path' else self.server.media_lock if self.path == '/output_image' else self.server.operation_lock
        with lock:
            self.dispatch_post()

    def dispatch_post(self):
        if self.headers.get('X-Pipeline-Token') != self.server.token:
            self.send_error(403)
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 <= size <= 1_000_000:
                raise ValueError('Request too large')
            args = json.loads(self.rfile.read(size))
            if not isinstance(args, dict):
                raise ValueError('Request arguments must be an object.')
            if tag := self.headers.get('If-Match'):
                if not tag.startswith('"') or not tag.endswith('"'):
                    raise ValueError('Use a strong quoted revision tag for If-Match.')
                revision = int(tag[1:-1])
                if 'expected_revision' in args and args['expected_revision'] != revision:
                    raise ValueError('Revision header and request disagree.')
                args['expected_revision'] = revision
            result = self.server.application.dispatch(self.path.strip('/'), args)
            if isinstance(result, OutputMedia):
                with result.path.open('rb') as stream:
                    self.send_response(200)
                    self.send_header('Content-Type', result.content_type)
                    remaining = os.fstat(stream.fileno()).st_size
                    self.send_header('Content-Length', str(remaining))
                    self.send_header('Cache-Control', 'no-store')
                    self.send_header('X-Content-Type-Options', 'nosniff')
                    self.end_headers()
                    try:
                        while remaining:
                            chunk = stream.read(min(128 * 1024, remaining))
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                            remaining -= len(chunk)
                    except OSError:
                        # A disconnect or disappearing file ends this response;
                        # headers are already sent, so never append a JSON error.
                        self.close_connection = True
                return
            body = json.dumps(result).encode()
            self.send_response(200)
            if isinstance(result, dict) and isinstance(result.get('project'), dict):
                self.send_header('ETag', '"' + str(result['project']['revision']) + '"')
        except (ConnectionError, TimeoutError):
            raise  # A disconnected socket cannot receive an error response.
        except Exception as exc:
            body = json.dumps({'error': str(exc), 'code': getattr(exc, 'code', 'invalid_request')}).encode()
            self.send_response(getattr(exc, 'status', 400))
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def create_server(app, token, asset_directory=WEB_DIR, address=('127.0.0.1', 0)):
    """A factory allows isolated local instances without module-level singletons."""
    http = ThreadingHTTPServer(address, Handler)
    http.application = app
    http.token = token
    http.asset_directory = Path(asset_directory)
    http.operation_lock = threading.RLock()
    http.picker_lock = threading.Lock()
    http.media_lock = threading.Lock()
    return http
