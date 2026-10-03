import bpy,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from blender_render_settings import apply as apply_advanced,read as read_advanced
from compositor_outputs import route
job=json.loads(Path(sys.argv[sys.argv.index('--')+1]).read_text(encoding='utf-8'))
bpy.ops.wm.open_mainfile(filepath=job['input'])
scene=bpy.data.scenes.get(job['scene'])
if not scene:raise ValueError('Render scene is missing.')
camera=scene.objects.get(job['camera'])
if not camera or camera.type!='CAMERA':raise ValueError('Select a camera in the render scene.')
scene.camera=camera
scene.frame_start=job['start'];scene.frame_end=job['end']
if job.get('engine'):scene.render.engine=job['engine']
for key,prop in [('width','resolution_x'),('height','resolution_y'),('percentage','resolution_percentage')]:
    if job.get(key) is not None:setattr(scene.render,prop,job[key])
if job.get('samples') is not None:
    if scene.render.engine=='CYCLES':scene.cycles.samples=job['samples']
    elif hasattr(scene,'eevee') and hasattr(scene.eevee,'taa_render_samples'):scene.eevee.taa_render_samples=job['samples']
    else:raise ValueError('Samples override is not supported by this render engine.')
if job.get('denoise') is not None:
    if scene.render.engine!='CYCLES':raise ValueError('Denoising override requires Cycles.')
    scene.cycles.use_denoising=job['denoise']
if job.get('format'):
    if hasattr(scene.render.image_settings,'media_type'):scene.render.image_settings.media_type='MULTI_LAYER_IMAGE' if job['format']=='OPEN_EXR_MULTILAYER' else 'VIDEO' if job['format']=='FFMPEG' else 'IMAGE'
    scene.render.image_settings.file_format=job['format']
scene.render.use_file_extension=True
advanced=apply_advanced(scene,job.get('advanced',{}))
print('PIPELINE_SETTINGS '+json.dumps(dict(width=scene.render.resolution_x,height=scene.render.resolution_y,percentage=scene.render.resolution_percentage,samples=scene.cycles.samples if scene.render.engine=='CYCLES' else getattr(getattr(scene,'eevee',None),'taa_render_samples',None),engine=scene.render.engine,format=scene.render.image_settings.file_format,start=scene.frame_start,end=scene.frame_end,camera=camera.name,denoise=scene.cycles.use_denoising if scene.render.engine=='CYCLES' else None,advanced=advanced,passes=[p.identifier for p in scene.view_layers[0].bl_rna.properties if p.identifier.startswith('use_pass_') and getattr(scene.view_layers[0],p.identifier,False)])),flush=True)
scene.render.filepath=str(Path(job['output'])/(job['prefix'] if job['prefix'].endswith('_') else job['prefix']+'_'))
tree=getattr(scene,'compositing_node_group',None) or getattr(scene,'node_tree',None)
print('PIPELINE_COMPOSITOR_OUTPUTS '+json.dumps(route(tree,job['output'],job['prefix'])),flush=True)
advanced_errors=[]
def prepare(current,*args):
    if current==scene and advanced:
        try:apply_advanced(current,job.get('advanced',{}))
        except Exception as exc:advanced_errors.append(str(exc))
def written(current,*args):
    print('PIPELINE_FRAME '+json.dumps({'frame':current.frame_current}),flush=True)
    if current==scene and advanced:
        actual=read_advanced(current,advanced)
        print('PIPELINE_ADVANCED_FRAME '+json.dumps(dict(frame=current.frame_current,settings=actual)),flush=True)
        if actual!=advanced:advanced_errors.append('Animation or a driver changed a requested render setting at frame '+str(current.frame_current)+'.')
bpy.app.handlers.render_pre.append(prepare)
bpy.app.handlers.render_write.append(written)
bpy.ops.render.render(animation=True,scene=scene.name)
if advanced_errors:raise ValueError('\n'.join(dict.fromkeys(advanced_errors)))
