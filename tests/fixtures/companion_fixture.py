"""Headless Blender integration of actual installed-package operators + HTTP bridge."""
import bpy,sys,time,json
from pathlib import Path
args=sys.argv[sys.argv.index('--')+1:];client,connection,project,fixtures=map(Path,args)
sys.path.insert(0,str(client));import pipeline_companion as p
p.DEFAULT_CONNECTION=str(connection);p.register()
def pump(condition,seconds=90):
    until=time.monotonic()+seconds
    while time.monotonic()<until:
        p._tick()
        if condition():return
        time.sleep(.05)
    raise AssertionError('Timeout: '+p._status+'; jobs='+str(p._jobs))
def idle():return not p._pending and not p._jobs and not p._requests
def source(name):return next(n for n in p._catalog['files'] if n['name']==name)
bpy.ops.wm.read_factory_settings(use_empty=True)
settings=bpy.context.scene.pipeline_companion;settings.project_folder=str(project);settings.filename='Working';settings.create=True
assert bpy.ops.pipeline.enroll()=={'FINISHED'}
pump(lambda:Path(bpy.data.filepath).name=='Working.blend' and p._node() is not None and idle())
for filename in ['Models.blend','Lighting.blend','Reusable.blend']:
    p._enqueue('import',{'source':str(fixtures/filename)})
    pump(lambda name=Path(filename).stem:any(n['name']==name for n in p._catalog['files']) and idle())
settings.source=source('Models')['id'];settings.kind='collections';settings.collection='Models';settings.mode='override'
assert bpy.ops.pipeline.link_here()=={'FINISHED'}
pump(lambda:any(o.override_library for o in bpy.context.scene.objects) and idle())
settings.source=source('Lighting')['id'];settings.collection='Lighting';settings.mode='collection';settings.camera='Shot Camera'
assert bpy.ops.pipeline.link_here()=={'FINISHED'}
pump(lambda:bpy.context.scene.camera is not None and idle())
settings.source=source('Reusable')['id'];settings.kind='materials';settings.item='Reusable Material';settings.apply='material';settings.target_object='Hero'
assert bpy.ops.pipeline.link_here()=={'FINISHED'}
pump(lambda:bpy.data.objects['Hero'].material_slots[0].material.name=='Reusable Material' and idle())
assert bpy.ops.pipeline.save_snapshot()=={'FINISHED'};pump(idle)
assert bpy.ops.pipeline.reload_links()=={'FINISHED'};pump(idle)
assert bpy.ops.pipeline.preflight()=={'FINISHED'};pump(idle)
assert p._report
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=1
scene.render.resolution_x=64;scene.render.resolution_y=64;scene.frame_start=1;scene.frame_end=1
scene.frame_set(7)
# Configure different graph overrides: the companion submission must use Blender settings.
p._enqueue('folder',{'title':'Connected Outputs'});pump(idle)
folder=next(f for f in p._catalog['folders'] if f['name']=='Connected Outputs')
p._enqueue('render_config',{'node_id':p._node()['id'],'folder_id':folder['id'],'scene':scene.name,'camera':scene.camera.name,'width':120,'samples':32,'auto_prefix':True});pump(idle)
settings.render_mode='FRAME';settings.render_output='CONNECTED'
assert bpy.ops.pipeline.queue_render()=={'FINISHED'};pump(idle)
pump(lambda:p._catalog.get('render_queue') and p._catalog['render_queue'][-1]['status']=='Complete')
first=p._catalog['render_queue'][-1]
assert first['start']==7 and first['end']==7 and first['run_id'],first
assert p._node()['render_config']['width']==120 and p._node()['render_config']['samples']==32
scene.frame_start=1;scene.frame_end=2;settings.render_mode='ANIMATION'
assert bpy.ops.pipeline.queue_render()=={'FINISHED'};pump(idle)
pump(lambda:len(p._catalog.get('render_queue',[]))==2 and p._catalog['render_queue'][-1]['status']=='Complete')
second=p._catalog['render_queue'][-1];assert second['start']==1 and second['end']==2,second
assert len(p._catalog['folders'])==1,'Companion silently created a second output folder'
assert p._node()['render_config']['width']==120 and p._node()['render_config']['samples']==32
# The application must reject background edits while the companion reports this file open.
p._send('companion_heartbeat',p._payload(),p._received);pump(idle)
p._enqueue('relocate',{'node_id':p._node()['id'],'folder_id':None,'title':'Must Not Move','closed':True});pump(idle)
assert 'open in Blender' in p._status or 'Project changed' in p._status,p._status
assert Path(bpy.data.filepath).name=='Working.blend'
p.unregister()
print('PASS: companion package registration, enrollment, live links, snapshots, current-frame/animation rendering, existing output reuse, queue status, preserved graph overrides and live-open protection')
