"""Nested, hidden collection with parenting, a material and animation."""
import sys
import bpy

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
scene = bpy.context.scene
product = bpy.data.collections.new('Product')
scene.collection.children.link(product)
parts = bpy.data.collections.new('Parts')
product.children.link(parts)
empty = bpy.data.objects.new('Product Root', None)
product.objects.link(empty)
material = bpy.data.materials.new('Product Red')
material.use_nodes = True
material.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value = (0.8, 0.03, 0.02, 1)
for index in range(2):
    bpy.ops.mesh.primitive_cube_add()
    obj = bpy.context.object
    obj.name = f'Part {index+1}'
    for collection in list(obj.users_collection):
        collection.objects.unlink(obj)
    parts.objects.link(obj)
    obj.parent = empty
    obj.location.x = index * 3
    obj.data.materials.append(material)
    obj.keyframe_insert('location', frame=1)
    obj.location.z = 1
    obj.keyframe_insert('location', frame=3)
bpy.ops.mesh.primitive_uv_sphere_add()
bpy.context.object.name = 'Outside Product'
parts.hide_viewport = True
scene.frame_start = 1
scene.frame_end = 3
scene.frame_set(2)
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=sys.argv[sys.argv.index('--') + 1])
