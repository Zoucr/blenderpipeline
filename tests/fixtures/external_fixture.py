import bpy,sys
from pathlib import Path
root=Path(sys.argv[sys.argv.index('--')+1]);root.mkdir(exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
c=bpy.data.collections.new('Base');bpy.context.scene.collection.children.link(c)
bpy.context.view_layer.active_layer_collection=bpy.context.view_layer.layer_collection.children[c.name]
bpy.ops.mesh.primitive_cube_add();bpy.context.preferences.filepaths.save_version=0
bpy.ops.wm.save_as_mainfile(filepath=str(root/'Base.blend'))
bpy.ops.wm.read_factory_settings(use_empty=True)
with bpy.data.libraries.load(str(root/'Base.blend'),link=True,relative=True) as (a,b):b.collections=['Base']
outer=bpy.data.collections.new('Outer');bpy.context.scene.collection.children.link(outer)
obj=bpy.data.objects.new('Base instance',None);obj.instance_type='COLLECTION';obj.instance_collection=b.collections[0];outer.objects.link(obj)
for i in range(80):
    child=bpy.data.collections.new('Collection '+str(i).zfill(3));outer.children.link(child)
bpy.context.preferences.filepaths.save_version=0;bpy.ops.wm.save_as_mainfile(filepath=str(root/'Outer.blend'))
