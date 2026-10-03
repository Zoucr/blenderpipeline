"""Generate and repair a zero-slot override without depending on user project files."""
import subprocess,tempfile
from pathlib import Path
from blender_pipeline.project.workspace import Pipeline
from blender_pipeline.project.model import digest
from support import ROOT, WORKERS, FIXTURES
with tempfile.TemporaryDirectory(prefix='material-slots-') as temp:
    root=Path(temp);p=Pipeline();p.registry=root/'recent.json';p.global_template_config=root/'app-default.json';p.create(root,'Material Test')
    fixture=root/'fixture.py'
    fixture.write_text("""import bpy,sys
from pathlib import Path
sys.path.insert(0,SCRIPTS)
from blender_linking import link_collection,link_datablock
root=Path(PROJECT)
def save(title):
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.wm.save_as_mainfile(filepath=str(root/title))
bpy.ops.wm.read_factory_settings(use_empty=True)
material=bpy.data.materials.new('Pink');material.use_nodes=True;material.use_fake_user=True
save('Untitled 001.blend')
bpy.ops.wm.read_factory_settings(use_empty=True)
collection=bpy.data.collections.new('Models');bpy.context.scene.collection.children.link(collection)
bpy.ops.mesh.primitive_monkey_add();obj=bpy.context.object;obj.name='Suzanne'
for old in list(obj.users_collection):old.objects.unlink(obj)
collection.objects.link(obj)
assert len(obj.material_slots)==0
save('Untitled 003.blend')
bpy.ops.wm.read_factory_settings(use_empty=True)
save('Untitled 002.blend')
link_collection(root/'Untitled 003.blend','Models','override')
link_datablock(root/'Untitled 001.blend','materials','Pink')
save('Untitled 002.blend')
""".replace('SCRIPTS',repr(str(WORKERS))).replace('PROJECT',repr(str(p.root))),encoding='utf-8')
    p.run(fixture,[])
    for file in list(p.root.glob('*.blend')):p.import_blend(file)
    combined=next(n for n in p.data['nodes'] if n['path']=='Untitled 002.blend');source=next(n for n in p.data['nodes'] if n['path']=='Untitled 003.blend');material=next(n for n in p.data['nodes'] if n['path']=='Untitled 001.blend')
    assert next(o for o in combined['scan']['objects'] if o.get('reference'))['reference_slots']==0
    p.prepare_materials(combined['id'],closed=True)
    assert len(combined['snapshots'])==1 and len(source['snapshots'])==1 and not material['snapshots']
    o=next(o for o in combined['scan']['objects'] if o.get('reference'));assert o['reference_slots']==1 and o['material_slots'][0]['link']=='OBJECT',o
    script=root/'edit.py'
    def run(file,code):
        script.write_text(code);result=subprocess.run([p.blender,'--background','--factory-startup','--disable-autoexec','--python-exit-code','1',str(file),'--python',str(script)],capture_output=True,text=True);assert result.returncode==0,result.stdout+result.stderr
    # User assigns the source material normally, without a custom loader or scripted reassignment.
    run(p.path(combined),"import bpy\no=bpy.context.scene.objects['Suzanne']\no.material_slots[0].material=next(m for m in bpy.data.materials if m.library and m.name=='Pink')\no.location.x=7\nbpy.context.preferences.filepaths.save_version=0\nbpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)\n")
    check="import bpy\no=bpy.context.scene.objects['Suzanne']\nassert o.material_slots[0].link=='OBJECT'\nassert o.material_slots[0].material.name=='Pink'\nassert o.material_slots[0].material.library\nassert o.location.x==7\n"
    run(p.path(combined),check)
    run(p.path(source),"import bpy\no=bpy.context.scene.objects['Suzanne']\no.data.vertices[0].co.z=12\nbpy.context.preferences.filepaths.save_version=0\nbpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)\n")
    run(p.path(material),"import bpy\nm=bpy.data.materials['Pink']\nm.diffuse_color=(0.17,0.29,0.53,1)\nn=next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED');n.inputs['Roughness'].default_value=0.123\nbpy.context.preferences.filepaths.save_version=0\nbpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)\n")
    run(p.path(combined),check+"assert o.data.vertices[0].co.z==12\nm=o.material_slots[0].material\nassert abs(m.diffuse_color[0]-0.17)<0.001\nassert abs(next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED').inputs['Roughness'].default_value-0.123)<0.001\n")
print('PASS: generated zero-slot fixture repair, source/destination snapshots, Object assignment survives native reopen, material shader + geometry updates preserve assignment and transforms; no user-project dependency')
