"""Actual startup capture, existing/new project inheritance and portable copies."""
import json,tempfile
from pathlib import Path
from blender_pipeline.project.workspace import Pipeline
from blender_pipeline.project.model import digest
from support import ROOT, WORKERS, FIXTURES
with tempfile.TemporaryDirectory(prefix='app-startup-') as temp:
    root=Path(temp);p=Pipeline();p.registry=root/'recent.json';p.global_template_config=root/'startup-default.json'
    source=root/'Startup.blend'
    p.run(str(FIXTURES/'create_startup.py'),[source]);before=digest(source)
    p.create(root,'Existing');p.save_app_startup(source);assert digest(source)==before
    p.create_blend();n=p.data['nodes'][-1]
    assert n['scan']['scenes'][0]['engine']=='CYCLES' and n['scan']['scenes'][0]['width']==1920
    assert set(n['scan']['collections'])=={'Camera','Light','Objekte'} and not n['scan']['refs']
    assert next(o for o in n['scan']['objects'] if o['name']=='Cube')['material_slots']==[{'link':'DATA','material':''}]
    entry=p.data['templates'][0];assert p.template_entry(entry['id'])[0]['hash']==before
    p.create_blend();assert len(p.data['templates'])==1
    p.create_blend(template_id='');assert p.data['nodes'][-1]['scan']['collections']==['Collection']
    p.create(root,'New');p.create_blend();assert set(p.data['nodes'][-1]['scan']['collections'])=={'Camera','Light','Objekte'}
    p.template_default('__factory__');p.create_blend();assert p.data['nodes'][-1]['scan']['collections']==['Collection']
    p.template_default('');p.create_blend();assert len(p.data['nodes'][-1]['scan']['objects'])==3
    entry=json.loads(p.global_template_config.read_text());(root/entry['path']).write_bytes(b'invalid');count=len(p.data['nodes'])
    try:p.create_blend();raise AssertionError('Changed default accepted')
    except ValueError as exc:assert 'changed' in str(exc)
    assert len(p.data['nodes'])==count
    assert digest(source)==before
print('PASS: self-contained startup capture unchanged, existing/new project defaults, portable project copies, explicit factory override and tamper guard')
