"""Build a Blender-installable archive from source, without installing anything."""
from pathlib import Path
import zipfile

from blender_pipeline.paths import ADDON_SOURCE, BLENDER_SCRIPTS_DIR


def build_addon(destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix('.zip.tmp')
    try:
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.write(ADDON_SOURCE, 'pipeline_companion/__init__.py')
            archive.write(ADDON_SOURCE.parent / 'material_assistant.py', 'pipeline_companion/material_assistant.py')
            archive.write(BLENDER_SCRIPTS_DIR / 'blender_linking.py', 'pipeline_companion/blender_linking.py')
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination
