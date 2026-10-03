"""Local application entry point; intentionally binds only to loopback."""
import argparse
import json
from pathlib import Path
import secrets
import webbrowser

from blender_pipeline import __version__
from blender_pipeline.bootstrap import create_application
from blender_pipeline.http.server import create_server
from blender_pipeline.paths import DATA_DIR


def main():
    parser = argparse.ArgumentParser(description='Local Blender Pipeline')
    parser.add_argument('--data-dir', type=Path, default=DATA_DIR, help='Machine settings and generated downloads')
    parser.add_argument('--blender', help='Blender executable; otherwise use saved setting or automatic discovery')
    parser.add_argument('--port', type=int, default=0, help='Local port (0 selects an available port)')
    parser.add_argument('--no-browser', action='store_true', help='Print the address without opening a browser')
    args = parser.parse_args()
    app = create_application(args.data_dir.expanduser().resolve(), args.blender)
    token = secrets.token_urlsafe(32)
    http = create_server(app, token, address=('127.0.0.1', args.port))
    connection = app.bridge.publish(http.server_port, token)
    url = f'http://127.0.0.1:{http.server_port}/'
    print(f'Blender Pipeline {__version__}: {url}\nData: {app.settings_directory}\nKeep this console open. Ctrl+C stops the local application.', flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        http.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        http.server_close()
        app.tasks.pool.shutdown(wait=True)
        try:
            if json.loads(connection.read_text())['token'] == token:
                connection.unlink()
        except (OSError, ValueError, KeyError):
            pass


if __name__ == '__main__':
    main()
