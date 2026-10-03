"""Real Blender batch regression: mixed imports, coverage, overrides and rollback."""
import json,subprocess,tempfile
from pathlib import Path
from blender_pipeline.project.workspace import Pipeline
from blender_pipeline.project.model import digest
from support import ROOT, WORKERS, FIXTURES
with tempfile.TemporaryDirectory(prefix='batch-link-') as temp:
    root=Path(temp);p=Pipeline();p.registry=root/'recent.json';p.global_template_config=root/'app-startup.json';p.create(root,'Batch Test');p.create_blend('Source');source=p.data['nodes'][-1]
    fixture=root/'fixture.py';fixture.write_text('''import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)
parent=bpy.data.collections.new('Models');bpy.context.scene.collection.children.link(parent)
child=bpy.data.collections.new('Parts');parent.children.link(child)
mesh=bpy.data.meshes.new('Hero Geometry');mesh.from_pydata([(0,0,0),(1,0,0),(0,1,0)],[],[(0,1,2)])
obj=bpy.data.objects.new('Hero',mesh);child.objects.link(obj)
light=bpy.data.collections.new('Lighting');bpy.context.scene.collection.children.link(light)
overlap=bpy.data.collections.new('Shared Hero');bpy.context.scene.collection.children.link(overlap);overlap.objects.link(bpy.data.objects['Hero'])
obj=bpy.data.objects.new('Key',bpy.data.lights.new('Key Data','AREA'));light.objects.link(obj)
obj=bpy.data.objects.new('Shot Camera',bpy.data.cameras.new('Camera Data'));bpy.context.scene.collection.objects.link(obj)
for name in ['Red','Blue','Green','Gold']:
    mat=bpy.data.materials.new(name);mat.use_fake_user=True
for name,kind in [('Scatter','GeometryNodeTree'),('Surface','ShaderNodeTree')]:
    g=bpy.data.node_groups.new(name,kind);g.use_fake_user=True
bpy.context.preferences.filepaths.save_version=0
bpy.ops.wm.save_as_mainfile(filepath=SOURCE)
'''.replace('SOURCE',repr(str(p.path(source)))))
    subprocess.run([p.blender,'--background','--disable-autoexec','--python',str(fixture)],check=True,capture_output=True)
    p.refresh(source['id']);assert any(d.get('object_type')=='MESH' and d['name']=='Hero' for d in source['scan']['datablocks'])
    selections=[{'kind':'collections','name':name} for name in ['Models','Parts','Lighting']]+[{'kind':'objects','name':name} for name in ['Hero','Shot Camera']]+[{'kind':'materials','name':name} for name in ['Red','Blue','Green','Gold']]+[{'kind':'node_groups','name':'Scatter'}]
    p.create_blend('Shot');shot=p.data['nodes'][-1];before=digest(p.path(shot))
    p.link_batch(source['id'],shot['id'],selections,closed=True,mode='override',camera='Shot Camera',prepare_source=True)
    assert len(source['snapshots'])==1 and len(shot['snapshots'])==1
    assert len(shot['scan']['overrides'])==3,shot['scan']['overrides']
    assert len(shot['scan']['data_links'])==6,shot['scan']['data_links']
    assert shot['scan']['scenes'][0]['camera']=='Shot Camera'
    assert len([o for o in shot['scan']['objects'] if o['name'].startswith('Hero')])==2 # linked reference + local override, only local placed
    checker=root/'check.py';checker.write_text('''import bpy
s=bpy.context.scene
assert len([o for o in s.objects if o.name.startswith('Hero')])==1
assert s.objects['Hero'].override_library and not s.objects['Hero'].library
assert s.camera.override_library and s.camera.type=='CAMERA'
assert len([c for c in s.collection.children if c.name=='Parts'])==0
assert bpy.data.materials['Red'].library
''')
    result=subprocess.run([p.blender,'--background','--disable-autoexec',str(p.path(shot)),'--python',str(checker)],capture_output=True,text=True);assert 'Traceback' not in result.stderr,result.stderr
    saved=digest(p.path(shot));snapshots=len(shot['snapshots'])
    try:p.link_batch(source['id'],shot['id'],selections,closed=True);raise AssertionError('Duplicate accepted')
    except ValueError as exc:assert 'already linked' in str(exc),str(exc)
    assert digest(p.path(shot))==saved and len(shot['snapshots'])==snapshots
    try:p.link_batch(source['id'],shot['id'],[{'kind':'collections','name':'Shared Hero'}],closed=True);raise AssertionError('Existing shared override accepted')
    except ValueError as exc:assert 'existing override' in str(exc),str(exc)
    assert digest(p.path(shot))==saved and len(shot['snapshots'])==snapshots
    try:p.link_batch(shot['id'],source['id'],[{'kind':'collections','name':'Models'}],closed=True);raise AssertionError('Cycle accepted')
    except ValueError as exc:assert 'cycle' in str(exc)
    # Invalid assignment fails inside Blender and must leave the working file unchanged.
    p.create_blend('Rollback');dest=p.data['nodes'][-1];original=digest(p.path(dest))
    try:p.link_batch(source['id'],dest['id'],[{'kind':'materials','name':'Red','apply':'material','object_name':'Missing'}],closed=True);raise AssertionError('Bad assignment accepted')
    except ValueError as exc:assert 'editable object' in str(exc),str(exc)
    assert digest(p.path(dest))==original and len(dest['snapshots'])==1
    sharing=[{'kind':'collections','name':name} for name in ['Models','Shared Hero']]
    try:p.link_batch(source['id'],dest['id'],sharing,closed=True);raise AssertionError('Shared roots accepted')
    except ValueError as exc:assert 'share objects' in str(exc),str(exc)
    assert digest(p.path(dest))==original and len(dest['snapshots'])==1
    p.link_batch(source['id'],dest['id'],sharing,closed=True,mode='collection')
    checker.write_text("import bpy\nassert len([o for o in bpy.context.scene.objects if o.name.startswith('Hero')])==1\n")
    result=subprocess.run([p.blender,'--background','--disable-autoexec',str(p.path(dest)),'--python',str(checker)],capture_output=True,text=True);assert 'Traceback' not in result.stderr,result.stderr
    for mode in ['collection','instance']:
        p.create_blend(mode);dest=p.data['nodes'][-1];p.link_batch(source['id'],dest['id'],selections,closed=True,mode=mode,camera='Shot Camera')
        assert len(dest['snapshots'])==1 and not dest['scan']['overrides']
        assert dest['scan']['scenes'][0]['camera']=='Shot Camera'
    # Source geometry update is inherited without resetting local override transforms.
    edit=root/'edit.py';edit.write_text("import bpy\nbpy.data.objects['Hero'].location.x=8\nbpy.context.preferences.filepaths.save_version=0\nbpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)\n")
    subprocess.run([p.blender,'--background','--disable-autoexec',str(p.path(shot)),'--python',str(edit)],check=True,capture_output=True)
    edit.write_text("import bpy\nbpy.data.meshes['Hero Geometry'].vertices[0].co.z=5\nbpy.context.preferences.filepaths.save_version=0\nbpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)\n")
    subprocess.run([p.blender,'--background','--disable-autoexec',str(p.path(source)),'--python',str(edit)],check=True,capture_output=True)
    checker.write_text("import bpy\no=bpy.context.scene.objects['Hero']\nassert o.location.x==8\nassert o.data.vertices[0].co.z==5\n")
    result=subprocess.run([p.blender,'--background','--disable-autoexec',str(p.path(shot)),'--python',str(checker)],capture_output=True,text=True);assert 'Traceback' not in result.stderr,result.stderr
print('PASS: mixed 10-item link, object camera override, hierarchy coverage, single snapshot, duplicate/cycle guards, atomic rollback, direct/instance placement and preserved edits on source update')
