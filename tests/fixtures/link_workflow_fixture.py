"""Actual Blender collection / material / animation update regression fixture."""
import bpy,sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'/'blender_pipeline'/'blender'))
from blender_linking import link_collection,link_datablock
root=Path(sys.argv[sys.argv.index('--')+1]).resolve();root.mkdir(parents=True,exist_ok=True)
bpy.context.preferences.filepaths.save_version=0
def save(path):bpy.ops.wm.save_as_mainfile(filepath=str(path))
model=root/'Models.blend';lighting=root/'Lighting.blend';shot=root/'Shot.blend'
bpy.ops.wm.read_factory_settings(use_empty=True)
c=bpy.data.collections.new('Models');bpy.context.scene.collection.children.link(c)
bpy.ops.mesh.primitive_cube_add();obj=bpy.context.object;obj.name='Hero'
for old in list(obj.users_collection):old.objects.unlink(obj)
c.objects.link(obj)
mat=bpy.data.materials.new('Source Material');mat.diffuse_color=(.2,.3,.4,1);obj.data.materials.append(mat)
obj.location=(0,0,0);obj.keyframe_insert(data_path='location',frame=1);obj.location=(0,1,0);obj.keyframe_insert(data_path='location',frame=10)
save(model)
bpy.ops.wm.read_factory_settings(use_empty=True)
c=bpy.data.collections.new('Lighting');bpy.context.scene.collection.children.link(c)
camera=bpy.data.objects.new('Shot Camera',bpy.data.cameras.new('Camera'));c.objects.link(camera)
lamp=bpy.data.objects.new('Key Light',bpy.data.lights.new('Key Light','AREA'));lamp.data.energy=75;c.objects.link(lamp)
save(lighting)
bpy.ops.wm.read_factory_settings(use_empty=True)
local=link_collection(model,'Models','override')
link_collection(lighting,'Lighting','collection',camera='Shot Camera')
hero=next(o for o in local.all_objects if o.name.startswith('Hero'))
assert hero.override_library and not hero.library
hero.animation_data.action=bpy.data.actions.new('Shot Animation')
hero.location=(3,0,0);hero.keyframe_insert(data_path='location',frame=1)
hero.location=(5,0,0);hero.keyframe_insert(data_path='location',frame=10)
localmat=bpy.data.materials.new('Shot Material');localmat.diffuse_color=(1,.1,.1,1)
hero.material_slots[0].link='OBJECT';hero.material_slots[0].material=localmat
save(shot)
bpy.ops.wm.open_mainfile(filepath=str(model))
obj=bpy.data.objects['Hero'];obj.data.vertices[0].co.x=-3
mat=bpy.data.materials['Source Material'];mat.diffuse_color=(.1,.9,.1,1)
new=bpy.data.objects.new('Added Source Object',bpy.data.meshes.new('Added Mesh'));bpy.data.collections['Models'].objects.link(new)
save(model)
bpy.ops.wm.open_mainfile(filepath=str(lighting));bpy.data.lights['Key Light'].energy=150;save(lighting)
bpy.ops.wm.open_mainfile(filepath=str(shot))
hero=next(o for o in bpy.context.scene.objects if o.override_library and o.override_library.reference.name=='Hero')
assert hero.data.vertices[0].co.x==-3,'Source mesh update lost'
assert abs(hero.data.materials[0].diffuse_color[1]-.9)<.001,'Source linked material update lost'
assert hero.material_slots[0].material.name=='Shot Material','Local material assignment lost'
assert hero.animation_data.action.name=='Shot Animation','Local animation action lost'
bpy.context.scene.frame_set(10);assert abs(hero.location.x-5)<.001,'Local animation values lost'
assert bpy.context.scene.camera.name=='Shot Camera'
assert bpy.context.scene.camera.library and bpy.data.lights['Key Light'].energy==150
assert any(o.name.startswith('Added Source Object') for o in bpy.context.scene.objects),'Added source object failed to resync'
save(shot)
# Explicit reload must preserve both local material assignment and animation.
for library in list(bpy.data.libraries):
    if not library.parent:library.reload()
save(shot)
bpy.ops.wm.open_mainfile(filepath=str(shot))
hero=next(o for o in bpy.context.scene.objects if o.override_library and o.override_library.reference.name=='Hero')
assert hero.material_slots[0].material.name=='Shot Material'
assert hero.animation_data.action.name=='Shot Animation'
print('PASS: multi-source camera/lighting + model hierarchy, source geometry/material/light changes, added-object resync, preserved local material assignment and shot animation, reload + reopen')
# Reusable datablocks survive save even when imported without an immediate usage.
assets=root/'Reusable.blend'
bpy.ops.wm.read_factory_settings(use_empty=True)
mat=bpy.data.materials.new('Reusable Material');mat.diffuse_color=(.2,.2,.8,1);mat.use_fake_user=True
world=bpy.data.worlds.new('Reusable World');world.color=(.1,.2,.3);world.use_fake_user=True
shader=bpy.data.node_groups.new('Reusable Shader','ShaderNodeTree');shader.use_fake_user=True
shader.interface.new_socket(name='Shader',in_out='OUTPUT',socket_type='NodeSocketShader')
bsdf=shader.nodes.new('ShaderNodeBsdfDiffuse');output=shader.nodes.new('NodeGroupOutput');shader.links.new(bsdf.outputs[0],output.inputs[0])
geometry=bpy.data.node_groups.new('Reusable Geometry','GeometryNodeTree');geometry.use_fake_user=True
geometry.interface.new_socket(name='Geometry',in_out='INPUT',socket_type='NodeSocketGeometry');geometry.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')
inp=geometry.nodes.new('NodeGroupInput');out=geometry.nodes.new('NodeGroupOutput');geometry.links.new(inp.outputs[0],out.inputs[0])
save(assets)
bpy.ops.wm.open_mainfile(filepath=str(shot))
bpy.ops.mesh.primitive_cube_add();target=bpy.context.object;target.name='Datablock Target'
link_datablock(assets,'materials','Reusable Material','material',target.name)
link_datablock(assets,'node_groups','Reusable Geometry','modifier',target.name)
link_datablock(assets,'node_groups','Reusable Shader')
link_datablock(assets,'worlds','Reusable World','world')
save(shot)
bpy.ops.wm.open_mainfile(filepath=str(assets));bpy.data.materials['Reusable Material'].diffuse_color=(.8,.1,.2,1);bpy.data.node_groups['Reusable Shader'].nodes.get('Diffuse BSDF').inputs['Roughness'].default_value=.65;save(assets)
bpy.ops.wm.open_mainfile(filepath=str(shot));target=bpy.data.objects['Datablock Target']
assert target.material_slots[0].material.library and abs(target.material_slots[0].material.diffuse_color[0]-.8)<.001
assert target.modifiers[0].node_group.name=='Reusable Geometry'
assert bpy.context.scene.world.name=='Reusable World'
assert abs(bpy.data.node_groups['Reusable Shader'].nodes.get('Diffuse BSDF').inputs['Roughness'].default_value-.65)<.001
assert len([o for o in bpy.data.objects if o.get('pipeline_datablock')])==4
print('PASS: material assignment, Geometry Nodes modifier, unassigned shader group retention, scene world, linked updates after reopen')
