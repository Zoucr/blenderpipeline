"""Real Blender batches: selective overrides, version isolation and safe cleanup."""
import copy,json,subprocess,tempfile,time,threading
from pathlib import Path
from unittest.mock import patch
from blender_pipeline.project.workspace import Pipeline
from blender_pipeline.project.model import digest
from support import ROOT, WORKERS, FIXTURES
def setting(scope,prop):return json.dumps([scope,prop],separators=(',',':'))

with tempfile.TemporaryDirectory(prefix='render-manager-') as temporary:
    base=Path(temporary);p=Pipeline();p.registry=base/'recent.json';p.global_template_config=base/'unused.json';p.create(base,'Render tests')
    p.folder('Outputs');outer=p.data['nodes'][-1]
    p.folder('Shot one',folder_id=outer['id']);aout=p.data['nodes'][-1]
    p.folder('Shot two');bout=p.data['nodes'][-1];p.group_nodes({bout['id']:outer['id']})
    p.folder('Working files');organizer=p.data['nodes'][-1]
    fixture=base/'fixture.py';targets=[('Shot A',16,1,2,75),('Shot B',24,4,4,100)]
    for title,width,start,end,percentage in targets:
        p.create_blend(title,template_id='');n=p.data['nodes'][-1]
        fixture.write_text('''import bpy
bpy.ops.wm.read_factory_settings(use_empty=False)
s=bpy.context.scene;s.name='Scene '+TITLE;s.render.engine='CYCLES';s.cycles.device='CPU';s.cycles.samples=1;s.cycles.use_denoising=False
s.render.resolution_x=WIDTH;s.render.resolution_y=16;s.render.resolution_percentage=PERCENT;s.frame_start=FIRST;s.frame_end=LAST
s.view_layers[0].use_pass_z=True
s.view_settings.exposure=-1;s.view_settings.keyframe_insert('exposure',frame=FIRST);s.view_settings.exposure=1;s.view_settings.keyframe_insert('exposure',frame=LAST)
t=bpy.data.node_groups.new('Shot compositor','CompositorNodeTree');s.compositing_node_group=t;s.use_nodes=True
t.interface.new_socket(name='Image',in_out='OUTPUT',socket_type='NodeSocketColor')
rl=t.nodes.new('CompositorNodeRLayers');output=t.nodes.new('NodeGroupOutput');t.links.new(rl.outputs['Image'],output.inputs['Image'])
file=t.nodes.new('CompositorNodeOutputFile');file.directory=OLD_OUTPUT;file.file_name='beauty_';file.format.media_type='IMAGE';file.format.file_format='PNG';file.file_output_items.new('RGBA','Beauty');t.links.new(rl.outputs['Image'],file.inputs['Beauty'])
for index in range(2):
    mist=t.nodes.new('CompositorNodeOutputFile');mist.name='Mist '+str(index);mist.directory=OLD_OUTPUT;mist.file_name='old_';mist.format.media_type='IMAGE';mist.format.file_format='OPEN_EXR';mist.file_output_items.new('FLOAT','Mist');t.links.new(rl.outputs['Depth'],mist.inputs['Mist'])
bundle=t.nodes.new('CompositorNodeOutputFile');bundle.label='Combined passes';bundle.directory=OLD_OUTPUT;bundle.format.media_type='MULTI_LAYER_IMAGE';bundle.file_output_items.new('RGBA','Beauty');bundle.file_output_items.new('FLOAT','Depth');t.links.new(rl.outputs['Image'],bundle.inputs['Beauty']);t.links.new(rl.outputs['Depth'],bundle.inputs['Depth'])
bpy.context.preferences.filepaths.save_version=0
bpy.ops.wm.save_as_mainfile(filepath=TARGET)
'''.replace('TITLE',repr(title)).replace('WIDTH',str(width)).replace('PERCENT',str(percentage)).replace('FIRST',str(start)).replace('LAST',str(end)).replace('TARGET',repr(str(p.path(n)))).replace('OLD_OUTPUT',repr(str(base/'legacy-output'))),encoding='utf-8')
        process=subprocess.run([p.blender,'--background','--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(fixture)],capture_output=True)
        assert process.returncode==0,process.stdout.decode(errors='replace')+process.stderr.decode(errors='replace')
        p.refresh(n['id']);p.render_config(n['id'],aout['id'] if title=='Shot A' else bout['id'],'Scene '+title)
    a,b=[n for n in p.data['nodes'] if n['type']=='blend'];p.group_nodes({a['id']:organizer['id']})
    a,b=p.node(a['id']),p.node(b['id'])
    assert len(p.render_targets(outer['id']))==2 and p.render_targets(organizer['id'])==[]
    assert p.node(a['id'])['render_config']['start'] is None
    assert p.node(a['id'])['render_config']['camera']==''
    catalog=a['scan']['scenes'][0]['advanced_settings'];assert len(catalog)>100 and any(e['key']==setting('color','exposure') and e['editable'] for e in catalog)
    assert any(e['key']==setting('color','view_transform') and any(o['value']=='Standard' for o in e['options']) for e in catalog)
    p.render_config(a['id'],aout['id'],'Scene Shot A',advanced={setting('color','exposure'):1.25,setting('cycles','max_bounces'):4})
    original={n['id']:digest(p.path(n)) for n in [a,b]};original_configs={n['id']:copy.deepcopy(n['render_config']) for n in [a,b]}
    p.queue_worker=object() # Prevent worker start until the atomic submission checks finish.
    try:p.queue_batch(outer['id'],overrides={'samples':0});raise AssertionError('invalid override accepted')
    except ValueError:pass
    assert not p.data.get('render_queue')
    for bad in [{setting('render','filepath'):'../../escape'},{setting('cycles','max_bounces'):-1},{setting('unknown','execute'):True}]:
        try:p.queue_batch(outer['id'],overrides={'advanced':bad});raise AssertionError('invalid advanced override accepted')
        except ValueError:pass
    assert not p.data.get('render_queue')
    b['render_config']['camera']='Missing'
    try:p.queue_batch(outer['id']);raise AssertionError('invalid target accepted')
    except ValueError:pass
    assert not p.data.get('render_queue');b['render_config']=original_configs[b['id']]
    advanced_batch={setting('cycles','use_adaptive_sampling'):False,setting('layer:ViewLayer','use_pass_normal'):True}
    p.queue_batch(outer['id'],overrides={'samples':2,'advanced':advanced_batch},label='Preview')
    jobs=p.data['render_queue'];assert len(jobs)==2 and len({q['batch_id'] for q in jobs})==1
    a['render_config']['width']=99 # Queued settings must retain the submitted configuration.
    worker=threading.Thread(target=p._queue_loop,args=(p.data['id'],),daemon=True);p.queue_worker=worker;worker.start()
    deadline=time.monotonic()+100
    while p.render_busy() and time.monotonic()<deadline:time.sleep(.2)
    assert all(q['status']=='Complete' for q in jobs),jobs
    for run in p.data['renders']:
        log=(p.root/run['log']).read_text(encoding='utf-8',errors='replace')
        settings=json.loads(next(line.split('PIPELINE_SETTINGS ',1)[1] for line in log.splitlines() if 'PIPELINE_SETTINGS ' in line))
        width=16 if run['node_id']==a['id'] else 24
        assert settings['width']==width and settings['samples']==2 and 'use_pass_z' in settings['passes'],settings
        assert run['config']['percentage'] is None and run['overrides']=={'samples':2,'advanced':advanced_batch}
        assert settings['advanced'][setting('cycles','use_adaptive_sampling')] is False and 'use_pass_normal' in settings['passes']
        if run['node_id']==a['id']:
            assert settings['advanced'][setting('color','exposure')]==1.25 and settings['advanced'][setting('cycles','max_bounces')]==4
            frame_settings=[json.loads(line.split('PIPELINE_ADVANCED_FRAME ',1)[1]) for line in log.splitlines() if line.startswith('PIPELINE_ADVANCED_FRAME ')]
            assert len(frame_settings)==2 and all(f['settings'][setting('color','exposure')]==1.25 for f in frame_settings),frame_settings
        assert len(list((p.root/run['output']).glob('*.png')))==(2 if width==16 else 1)
        assert run['size_bytes']>0 and run['input_bytes']>0
        assert list((p.root/run['output']/'compositor').rglob('*.png')) and run['actual_settings']['samples']==2
        compositor=p.root/run['output']/'compositor';assert not any(path.is_dir() for path in compositor.iterdir())
        prefix=run['config']['prefix'].rstrip('_')+'_';first=run['config']['start'];assert (compositor/(prefix+f'Mist_{first:04}.exr')).is_file() and (compositor/(prefix+f'Mist_02_{first:04}.exr')).is_file()
        assert (compositor/(prefix+f'Combined_passes_{first:04}.exr')).is_file()
        assert any(item.get('layers')==['Beauty','Depth'] for item in run['compositor_outputs'])
    assert not (base/'legacy-output').exists()
    assert all(digest(p.path(n))==original[n['id']] for n in [a,b])
    with patch('blender_pipeline.project.workspace.shutil.copy2',side_effect=OSError('Simulated frozen-input failure')):
        try:p.render_start(a['id']);raise AssertionError('freeze failure ignored')
        except OSError:pass
    failed=p.data['renders'][-1];assert failed['status']=='Failed' and failed['finished'] and (p.root/failed['output']/'render-job.json').is_file()
    p.render_delete(failed['id'],True);assert failed['status']=='Deleted' and not (p.root/failed['output']).exists()
    first=p.data['renders'][0];other=p.data['renders'][1];first_output=p.root/first['output'];other_output=p.root/other['output'];other_hashes={f:digest(f) for f in other_output.rglob('*.png')}
    try:p.render_delete(first['id']);raise AssertionError('unconfirmed deletion accepted')
    except ValueError:pass
    output_record=first['output'];first['output']='.'
    try:p.render_delete(first['id'],True);raise AssertionError('project deletion accepted')
    except ValueError:pass
    first['output']=output_record;p.render_delete(first['id'],True)
    assert not first_output.exists() and not (p.root/first['inputs']).exists() and first['status']=='Deleted'
    assert all(digest(f)==h for f,h in other_hashes.items()) and all(p.path(n).is_file() for n in [a,b])
    a['render_config']=original_configs[a['id']];p.queue_render(a['id'],overrides={'samples':1,'format':'OPEN_EXR_MULTILAYER'})
    deadline=time.monotonic()+80
    while p.render_busy() and time.monotonic()<deadline:time.sleep(.2)
    last=p.data['renders'][-1];assert last['status']=='Complete' and last['number']==3 and last['output']!=first['output'],last
    assert len(list((p.root/last['output']).glob('*.exr')))==2 and list((p.root/last['output']/'compositor').rglob('*.png'))
    assert all(digest(p.path(n))==original[n['id']] for n in [a,b])
    print('PASS: explicit output scopes, graph/physical subfolders, atomic batches, captured settings, inherited resolution/range/passes, selective samples/advanced settings, animated overrides per frame, flat compositor passes and multilayer outputs, unchanged working files, isolated versions, deletion guards and reserved revision numbers',flush=True)
