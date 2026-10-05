"""Real installed companion material operators, including save/reopen and source updates."""
import bpy,sys
from pathlib import Path
client,root=map(Path,sys.argv[sys.argv.index('--')+1:]);sys.path.insert(0,str(client))
import pipeline_companion as p
from pipeline_companion.blender_linking import link_collection,link_datablock
for cls in p._classes:bpy.utils.register_class(cls)
bpy.types.Scene.pipeline_companion=bpy.props.PointerProperty(type=p.PIPELINE_Settings)
source=root/'Models.blend';materials=root/'Materials.blend';shot=root/'Shot.blend'
def save(path):
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.wm.save_as_mainfile(filepath=str(path))
def active(name='Hero'):
    obj=next(o for o in bpy.context.scene.objects if (o.override_library.reference.name if o.override_library else o.name)==name)
    bpy.context.view_layer.objects.active=obj;obj.select_set(True);return obj

bpy.ops.wm.read_factory_settings(use_empty=True)
c=bpy.data.collections.new('Models');bpy.context.scene.collection.children.link(c)
bpy.ops.mesh.primitive_cube_add();hero=bpy.context.object;hero.name='Hero'
for old in list(hero.users_collection):old.objects.unlink(hero)
c.objects.link(hero)
red=bpy.data.materials.new('Red');blue=bpy.data.materials.new('Blue');hero.data.materials.append(red);hero.data.materials.append(blue)
hero.material_slots[1].link='OBJECT';hero.material_slots[1].material=blue
twin=bpy.data.objects.new('Twin',hero.data);c.objects.link(twin)
empty=bpy.data.objects.new('No Slots',bpy.data.meshes.new('Empty'));c.objects.link(empty)
save(source)
bpy.ops.wm.read_factory_settings(use_empty=True)
material=bpy.data.materials.new('Replacement');material.use_fake_user=True;material.diffuse_color=(.3,.4,.5,1);save(materials)
bpy.ops.wm.read_factory_settings(use_empty=True);save(shot)
link_collection(source,'Models','override');replacement=link_datablock(materials,'materials','Replacement')
hero=active();info=p.material_assistant.describe(hero)
assert info['binding']=='Inherited source assignment' and info['material'].library and not info['blocked'],info
mesh_material=hero.data.materials[0]
assert bpy.ops.pipeline.material_object_slot()=={'FINISHED'}
assert hero.material_slots[0].link=='OBJECT' and hero.active_material==mesh_material
assert hero.data.materials[0]==mesh_material
assert bpy.ops.pipeline.material_restore()=={'FINISHED'};assert hero.material_slots[0].link=='DATA'
bpy.context.scene.pipeline_companion.material_choice=replacement
assert bpy.ops.pipeline.material_assign()=={'FINISHED'}
assert hero.material_slots[0].link=='OBJECT' and hero.active_material==replacement
assert active('Twin').material_slots[0].material==mesh_material
hero=active();save(shot);bpy.ops.wm.open_mainfile(filepath=str(shot));hero=active()
assert hero.active_material.name=='Replacement' and hero.active_material.library
assert bpy.ops.pipeline.local_material()=={'FINISHED'}
copied=hero.active_material;assert not copied.library and not copied.override_library
assert p.material_assistant.describe(hero)['shader']=='Local shader'
save(shot);bpy.ops.wm.open_mainfile(filepath=str(shot));hero=active();assert not hero.active_material.library
assert bpy.ops.pipeline.material_restore()=={'FINISHED'};assert hero.material_slots[0].link=='DATA' and hero.active_material.name=='Red'
# Source OBJECT bindings must restore as OBJECT, rather than incorrectly using mesh DATA.
hero.active_material_index=1;bpy.context.scene.pipeline_companion.material_choice=bpy.data.materials['Replacement']
assert bpy.ops.pipeline.material_assign()=={'FINISHED'}
assert bpy.ops.pipeline.material_restore()=={'FINISHED'}
assert hero.material_slots[1].link=='OBJECT' and hero.active_material.name=='Blue'
assert not p.material_assistant.describe(hero)['can_restore']
empty=active('No Slots');assert 'source file' in p.material_assistant.describe(empty)['blocked']
assert not p.material_assistant.describe(empty)['can_add_slot']
try:p.material_assistant.assign(empty,bpy.data.materials['Replacement']);raise AssertionError('Linked mesh without slots accepted')
except ValueError:pass
hero=active();hero.override_library.is_system_override=True
assert 'System override' in p.material_assistant.describe(hero)['blocked'];hero.override_library.is_system_override=False
linked=hero.override_library.reference
assert 'Read-only' in p.material_assistant.describe(linked)['blocked']
try:p.material_assistant.local_copy(linked);raise AssertionError('Read-only object was mutated')
except ValueError:pass
bpy.ops.mesh.primitive_cube_add();local=bpy.context.object;local.name='Local';assert p.material_assistant.describe(local)['can_add_slot']
assert bpy.ops.pipeline.material_add_slot()=={'FINISHED'};assert len(local.material_slots)==1
hero=active();hero.active_material_index=0;save(shot)
bpy.ops.wm.open_mainfile(filepath=str(source));bpy.data.materials['Red'].diffuse_color=(.8,.2,.1,1)
bpy.data.objects['Hero'].material_slots[1].material=bpy.data.materials['Red'];save(source)
bpy.ops.wm.open_mainfile(filepath=str(shot));hero=active()
assert hero.material_slots[0].link=='DATA' and abs(hero.active_material.diffuse_color[0]-.8)<.001
assert hero.material_slots[1].link=='OBJECT' and hero.material_slots[1].material.name=='Red','Restored source OBJECT assignment stopped following the source'
for cls in (p.PIPELINE_OT_material_assign,p.PIPELINE_OT_material_object_slot,p.PIPELINE_OT_material_restore,p.PIPELINE_OT_material_add_slot,p.PIPELINE_OT_local_material):assert 'UNDO' in cls.bl_options
# Validate sidebar drawing against registered operator/property/icon names.
from types import SimpleNamespace
labels=[];operators=[]
icons={i.identifier for i in bpy.types.UILayout.bl_rna.functions['label'].parameters['icon'].enum_items}
class Layout:
    enabled=True
    def box(self):return Layout()
    def row(self):return Layout()
    def panel(self,*args,**kwargs):return Layout(),Layout()
    def label(self,text='',icon='NONE',**kwargs):assert icon in icons,icon;labels.append(text)
    def prop(self,data,name,**kwargs):getattr(data,name)
    def prop_search(self,data,name,search,search_name,**kwargs):getattr(data,name);getattr(search,search_name)
    def template_list(self,kind,id,data,name,active,index,**kwargs):getattr(data,name);getattr(active,index)
    def operator(self,id,**kwargs):
        module,op=id.split('.');getattr(getattr(bpy.ops,module),op).get_rna_type();operators.append(id);return SimpleNamespace()
p.PIPELINE_PT_panel.draw(SimpleNamespace(layout=Layout()),bpy.context)
assert 'pipeline.material_assign' in operators and 'pipeline.queue_render' in operators
assert 'Material / override assistant' in labels and 'Render through Pipeline' in labels
print('PASS: real material operators, source/shared mesh protection, linked assignment and local copy persistence, DATA/OBJECT inheritance restoration and source updates, read-only/system/missing-slot guards, local slot creation and undo registration')
