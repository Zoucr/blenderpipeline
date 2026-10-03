"""Generate a portable startup fixture; no developer's Desktop files are needed."""
import bpy
from pathlib import Path
import sys

target = Path(sys.argv[sys.argv.index('--') + 1])
bpy.ops.wm.read_factory_settings(use_empty=False)
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.render.resolution_x = 1920
original = bpy.data.collections['Collection']
original.name = 'Objekte'
for title in ('Camera', 'Light'):
    collection = bpy.data.collections.new(title)
    scene.collection.children.link(collection)
    obj = bpy.data.objects[title]
    original.objects.unlink(obj)
    collection.objects.link(obj)
bpy.data.objects['Cube'].data.materials.clear()
bpy.data.objects['Cube'].data.materials.append(None)
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=str(target))
