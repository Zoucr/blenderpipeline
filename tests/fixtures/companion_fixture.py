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
assert bpy.ops.pipeline.queue_render()=={'FINISHED'};pump(idle)
# The application must reject background edits while the companion reports this file open.
p._send('companion_heartbeat',p._payload(),p._received);pump(idle)
p._enqueue('relocate',{'node_id':p._node()['id'],'folder_id':None,'title':'Must Not Move','closed':True});pump(idle)
assert 'open in Blender' in p._status or 'Project changed' in p._status,p._status
assert Path(bpy.data.filepath).name=='Working.blend'
p.unregister()
print('PASS: companion package registration, project creation from untitled Blender, save/register, override + camera collection live links, material assignment, snapshots, reload, preflight, queue request and live-open protection')
