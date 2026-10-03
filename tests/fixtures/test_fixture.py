"""Blender-only fixture builder/checker, never used by normal application operations."""
import bpy, json, sys
from pathlib import Path
args=sys.argv[sys.argv.index('--')+1:]
path=Path(args[0]).resolve()
bpy.ops.wm.open_mainfile(filepath=str(path))
if args[1]=='populate':
    # New-file active collection should capture this object automatically.
    bpy.ops.mesh.primitive_cube_add()
    assert bpy.context.object.name in bpy.data.collections['Collection'].objects
    nested=bpy.data.collections.new('New Nested')
    bpy.data.collections['Collection'].children.link(nested)
    bpy.ops.mesh.primitive_uv_sphere_add()
    obj=bpy.context.object
    for c in list(obj.users_collection):c.objects.unlink(obj)
    nested.objects.link(obj)
    # Reproduce the user's loose-root object situation.
    bpy.ops.mesh.primitive_cube_add()
    obj=bpy.context.object;obj.name='Loose Root Cube'
    for c in list(obj.users_collection):c.objects.unlink(obj)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.wm.save_as_mainfile(filepath=str(path))
elif args[1]=='check':
    collection=args[2]
    matches=[o for o in bpy.context.scene.objects if o.instance_type=='COLLECTION' and o.instance_collection and o.instance_collection.name==collection]
    assert len(matches)==1
    assert len(matches[0].instance_collection.all_objects)==int(args[3]), [(o.name,len(o.instance_collection.all_objects)) for o in matches]
    bpy.context.view_layer.update()
    assert any(i.is_instance and i.object.type=='MESH' for i in bpy.context.evaluated_depsgraph_get().object_instances)
elif args[1]=='render':
    from mathutils import Vector
    bpy.ops.mesh.primitive_cube_add()
    camera_data=bpy.data.cameras.new('Camera');camera=bpy.data.objects.new('Camera',camera_data)
    bpy.context.scene.collection.objects.link(camera);camera.location=(4,-6,4)
    camera.rotation_euler=(Vector((0,0,0))-camera.location).to_track_quat('-Z','Y').to_euler()
    scene=bpy.context.scene;scene.camera=camera
    scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=1
    scene.render.resolution_x=64;scene.render.resolution_y=64;scene.render.resolution_percentage=100
    scene.world=bpy.data.worlds.new('Test World');scene.world.use_nodes=True
    scene.world.node_tree.nodes.get('Background').inputs['Strength'].default_value=1
    bpy.context.preferences.filepaths.save_version=0;bpy.ops.wm.save_as_mainfile(filepath=str(path))
elif args[1]=='lighting_camera':
    from mathutils import Vector
    camera=bpy.data.objects['Shot Camera'];camera.location=(6,-8,5);camera.rotation_euler=(Vector((0,0,0))-camera.location).to_track_quat('-Z','Y').to_euler()
    lamp=bpy.data.objects['Key Light'];lamp.location=(3,-4,6);lamp.rotation_euler=(Vector((0,0,0))-lamp.location).to_track_quat('-Z','Y').to_euler();lamp.data.energy=500
    bpy.context.preferences.filepaths.save_version=0;bpy.ops.wm.save_as_mainfile(filepath=str(path))
elif args[1]=='cpu_settings':
    scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=2;scene.render.resolution_x=160;scene.render.resolution_y=100;scene.frame_start=1;scene.frame_end=1
    bpy.context.preferences.filepaths.save_version=0;bpy.ops.wm.save_as_mainfile(filepath=str(path))
print('PASS: Blender fixture '+args[1])
