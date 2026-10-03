"""Source resources and machine-local data have distinct, explicit locations."""
import os
from pathlib import Path
import shutil
import sys

SOURCE_ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = SOURCE_ROOT / 'web'
ADDON_SOURCE = SOURCE_ROOT / 'addon' / 'companion.py'
BLENDER_SCRIPTS_DIR = Path(__file__).resolve().parent / 'blender'


def data_directory():
    """An override is useful for portable installs and disposable test instances."""
    if override := os.environ.get('PIPELINE_DATA_DIR'):
        return Path(override).expanduser().resolve()
    if sys.platform == 'win32':
        base = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
    elif sys.platform == 'darwin':
        base = Path.home() / 'Library' / 'Application Support'
    else:
        base = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share'))
    return base / 'BlenderPipeline'


def default_blender():
    if executable := os.environ.get('BLENDER_EXECUTABLE') or shutil.which('blender'):
        return executable
    if sys.platform == 'win32':
        folder = Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Blender Foundation'
        installed = sorted(folder.glob('Blender */blender.exe'), reverse=True)
        return str(installed[0]) if installed else 'blender.exe'
    if sys.platform == 'darwin':
        return '/Applications/Blender.app/Contents/MacOS/Blender'
    return 'blender'


DATA_DIR = data_directory()
DEFAULT_BLENDER = default_blender()
