"""Run focused checks from any working directory; all test data is disposable."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BLENDER_CHECKS = ('verify_api.py', 'verify_batch_linking.py', 'verify_material_persistence.py', 'verify_collection_materials.py',
                  'verify_folders.py', 'verify_templates.py', 'verify_external.py',
                  'verify_companion.py', 'verify_render_manager.py', 'verify_app_startup.py',
                  'verify_browser_archive.py')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--node', help='Node.js executable when not on PATH')
    parser.add_argument('--blender', action='store_true', help='Include real Blender integration checks')
    parser.add_argument('--blender-executable', help='Override Blender executable for integration checks')
    args = parser.parse_args()
    node = args.node or shutil.which('node')
    if not node:
        parser.error('Node.js is required for UI checks; use --node with its executable path.')
    commands = [[sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests/unit', '-v'],
                [node, 'tests/ui/verify_runtime.cjs'], [node, 'tests/ui/verify_graph_gestures.cjs'],
                [sys.executable, '-B', 'tests/integration/verify_launch.py'],
                [sys.executable, '-B', 'tests/integration/verify_link_selection.py']]
    if args.blender:
        commands += [[sys.executable, '-B', 'tests/integration/' + filename] for filename in BLENDER_CHECKS]
    for command in commands:
        with tempfile.TemporaryDirectory(prefix='pipeline-check-') as directory:
            environment = dict(os.environ, PYTHONPATH=str(ROOT / 'src'), PYTHONDONTWRITEBYTECODE='1',
                               PIPELINE_DATA_DIR=str(Path(directory) / 'settings'))
            if args.blender_executable:
                environment['BLENDER_EXECUTABLE'] = args.blender_executable
            subprocess.run(command, cwd=ROOT, env=environment, check=True)
    print('All requested checks passed.', flush=True)


if __name__ == '__main__':
    main()
