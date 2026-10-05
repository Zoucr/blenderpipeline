"""Generate a bounded display PNG from a saved EXR/TIFF; never save a Blend file."""
import bpy
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from render_resources import blender_file_path

job = json.loads(Path(sys.argv[sys.argv.index('--') + 1]).read_text(encoding='utf-8'))
image = bpy.data.images.load(blender_file_path(job['source']), check_existing=False)
width, height = image.size
if width < 1 or height < 1:
    raise ValueError('This image has no readable pixels.')
scale = min(1, 1600 / max(width, height))
if scale < 1:
    image.scale(max(1, round(width * scale)), max(1, round(height * scale)))
scene = bpy.context.scene
for key, value in job.get('color', {}).items():
    scope, property_name = json.loads(key)
    if scope == 'color' and property_name in {'view_transform', 'look', 'exposure', 'gamma'}:
        try:
            setattr(scene.view_settings, property_name, value)
        except (TypeError, ValueError):
            pass
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGBA'
scene.render.image_settings.color_depth = '8'
image.save_render(blender_file_path(job['output']), scene=scene)
