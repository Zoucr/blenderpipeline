"""Disposable linear EXR for the Outputs browser's real Blender check."""
import bpy
import sys
from pathlib import Path

output = Path(sys.argv[sys.argv.index('--') + 1])
image = bpy.data.images.new('Output preview test', width=2048, height=64, float_buffer=True)
image.pixels = [value for y in range(64) for x in range(2048)
                for value in (x / 2048, y / 64, .25, 1)]
scene = bpy.context.scene
scene.render.image_settings.file_format = 'OPEN_EXR'
scene.render.image_settings.color_mode = 'RGBA'
image.save_render(str(output), scene=scene)
