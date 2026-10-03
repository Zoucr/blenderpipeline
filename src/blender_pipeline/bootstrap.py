"""Composition root: construct dependencies here, not inside HTTP module imports."""
from pathlib import Path

from blender_pipeline.adapters.addon_package import build_addon
from blender_pipeline.adapters.companion_bridge import Bridge
from blender_pipeline.application.commands import Application
from blender_pipeline.application.tasks import Tasks
from blender_pipeline.paths import DATA_DIR
from blender_pipeline.project.workspace import Pipeline


def create_application(data_directory=None, blender=None, package_addon=True):
    directory = Path(data_directory) if data_directory is not None else DATA_DIR
    directory.mkdir(parents=True, exist_ok=True)
    model = Pipeline(data_directory=directory)
    if blender is not None:
        model.blender = str(blender)
    tasks = Tasks(model)
    bridge = Bridge(model)
    bridge.tasks = tasks
    app = Application(model, tasks, bridge, directory)
    if package_addon:
        app.addon_archive = build_addon(directory / 'downloads' / 'Pipeline_Companion.zip')
    return app
