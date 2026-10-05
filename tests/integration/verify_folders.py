"""Real disk operations, nested frames, recovery and animation output discovery."""
import tempfile,subprocess,time,copy
from pathlib import Path
from blender_pipeline.project.workspace import Pipeline
from blender_pipeline.project.folders import dated_prefix
from blender_pipeline.project.model import digest
from support import ROOT, WORKERS, FIXTURES
with tempfile.TemporaryDirectory(prefix='folder-workflow-') as temp:
    root=Path(temp);p=Pipeline();p.registry=root/'recent.json';p.global_template_config=root/'startup.json';p.create(root,'Folder test')
    p.create_blend('Shot',template_id='',x=100,y=150);shot=p.data['nodes'][-1]
    p.create_blend('Other',template_id='',x=450,y=150);other=p.data['nodes'][-1]
    p.folder('Outputs',node_ids=[shot['id'],other['id']],x=50,y=20,width=800,height=450);outer=p.data['nodes'][-1]
    assert shot['group']==outer['id'] and other['group']==outer['id'] and p.path(shot).parent==p.root
    p.folder('Scene renders',folder_id=outer['id'],x=500,y=100,width=300,height=180);inner=p.data['nodes'][-1]
    assert inner['group']==outer['id'] and inner['path']=='Outputs/Scene renders'
    before=copy.deepcopy(p.data)
    try:p.group_nodes({outer['id']:inner['id']});raise AssertionError('cycle accepted')
    except ValueError:pass
    assert p.data==before
    try:p.folder('Invalid',folder_id=inner['id'],node_ids=[outer['id']]);raise AssertionError('creation cycle accepted')
    except ValueError:pass
    assert not (p.path(inner)/'Invalid').exists()
    p.group_nodes({other['id']:inner['id']});other=p.node(other['id']);assert other['group']==inner['id']
    script=root/'fixture.py';script.write_text('''import bpy
bpy.ops.wm.read_factory_settings(use_empty=False)
scene=bpy.context.scene;scene.name='Test Scene';scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=1
scene.render.resolution_x=16;scene.render.resolution_y=16
bpy.context.preferences.filepaths.save_version=0
bpy.ops.wm.save_as_mainfile(filepath=TARGET)
'''.replace('TARGET',repr(str(p.path(shot)))))
    subprocess.run([p.blender,'--background','--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(script)],check=True,capture_output=True)
    p.refresh(shot['id']);p.render_config(shot['id'],inner['id'],'Test Scene','Camera',1,2,100)
    assert p.node(shot['id'])['render_config']['prefix']==dated_prefix('Test Scene')
    p.render_start(shot['id']);run=p.data['renders'][-1];deadline=time.monotonic()+80
    while run['status']=='Rendering' and time.monotonic()<deadline:time.sleep(.2)
    assert run['status']=='Complete',run
    files=list((p.root/run['output']).glob('*.png'));assert len(files)==2
    assert sorted(f.name for f in files)==[dated_prefix('Test Scene')+'0001.png',dated_prefix('Test Scene')+'0002.png']
    p._folder_cache={};info=p.state()['folder_info'];assert info[inner['id']]['images']==2 and info[outer['id']]['images']==2
    render_hashes={f:digest(f) for f in files};physical=p.path(inner)
    try:p.archive_folder(inner['id']);raise AssertionError('unconfirmed deletion accepted')
    except ValueError:pass
    p.archive_folder(inner['id'],confirmed=True);record=p.data['archived_folders'][-1]
    assert physical.exists() and not record['moved'] and not p.node(shot['id']).get('render_config')
    assert p.node(other['id'])['group']==outer['id'] and all(digest(f)==h for f,h in render_hashes.items())
    p.restore_folder(record['id']);assert p.node(other['id'])['group']==inner['id'] and p.node(shot['id'])['render_config']['folder_id']==inner['id']
    p.folder();empty=p.data['nodes'][-1];empty_path=p.path(empty);p.archive_folder(empty['id'],confirmed=True);record=p.data['archived_folders'][-1]
    assert record['moved'] and not empty_path.exists();p.restore_folder(record['id']);assert empty_path.is_dir()
    p.archive_blend(other['id'],closed=True);archived=p.data['archived_files'][-1];p.restore_archived(archived['id']);assert p.path(p.node(other['id'])).exists()
print('PASS: folder grouping, physical nested creation, atomic cycle guards, confirmed recoverable deletion, retained render files, restored output settings, real two-frame CPU render, date/scene filenames and folder discovery')
