"""Real Blender settings, default selection, independent copies and portable recovery."""
import json,tempfile,zipfile
from pathlib import Path
from blender_pipeline.project.workspace import Pipeline
from blender_pipeline.project.model import digest
from support import ROOT, WORKERS, FIXTURES

with tempfile.TemporaryDirectory() as temp:
    root=Path(temp);p=Pipeline();p.registry=root/'recent.json';p.global_template_config=root/'app-startup.json';p.create(root,'Template Test')
    p.create_blend();node=p.data['nodes'][-1];source=p.path(node)
    script=root/'settings.py'
    script.write_text("import bpy,sys\nbpy.context.scene.render.resolution_x=713\nbpy.context.scene.render.fps=30\nbpy.context.scene.render.engine='CYCLES'\nbpy.context.scene.cycles.samples=19\nbpy.context.preferences.filepaths.save_version=0\nbpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)\n")
    # Use the same disabled-autoexec, background invocation as production.
    import subprocess
    subprocess.run([p.blender,'--background','--disable-autoexec',str(source),'--python',str(script)],check=True,capture_output=True)
    before=digest(source);p.save_template('My defaults',node_id=node['id'],make_default=True)
    assert digest(source)==before
    template=p.data['templates'][0];p.create_blend();new=p.data['nodes'][-1]
    assert new['startup_template']==template['id'] and new['scan']['scenes'][0]['width']==713
    assert digest(p.path(new))!=digest(p.root/template['path']) or p.path(new)!=p.root/template['path']
    assert digest(source)==before
    p.create_blend(template_id='');assert p.data['nodes'][-1]['scan']['scenes'][0]['width']!=713
    p.template_default('');p.create_blend();assert not p.data['nodes'][-1].get('startup_template')
    p.template_default(template['id']);archive=root/'project.zip';p.backup(str(archive));extracted=root/'restored';extracted.mkdir()
    with zipfile.ZipFile(archive) as z:z.extractall(extracted)
    q=Pipeline();q.registry=root/'restore-recent.json';q.global_template_config=root/'app-startup.json';q.load(str(extracted));q.create_blend();assert q.data['nodes'][-1]['scan']['scenes'][0]['width']==713
    path=q.root/template['path'];path.write_bytes(path.read_bytes()+b'changed')
    count=len(q.data['nodes'])
    try:q.create_blend();raise AssertionError('Changed template accepted')
    except ValueError as exc:assert 'changed' in str(exc)
    assert len(q.data['nodes'])==count
print('PASS: saved settings, automatic default, factory override, independent copies, portable backup and template integrity guard')
