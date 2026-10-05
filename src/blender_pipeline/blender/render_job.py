import bpy,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from blender_render_settings import apply as apply_advanced,read as read_advanced
from compositor_outputs import route
from render_layers import compositor_tree, compositor_dependencies, layer_metadata, selection
from render_resources import restore_warning_images, restore_image_inputs, blender_file_path
from render_devices import configure as configure_device
def stage(phase, **details):
    print('PIPELINE_STAGE '+json.dumps(dict(phase=phase,**details)),flush=True)
def execute(job):
    started=time.monotonic()
    stage('Loading saved inputs')
    bpy.ops.wm.open_mainfile(filepath=job['input'])
    print('PIPELINE_IMAGE_INPUTS '+json.dumps(restore_image_inputs(bpy.data.images,job,bpy.path.abspath)),flush=True)
    print('PIPELINE_IMAGE_WARNINGS '+json.dumps(restore_warning_images(bpy.data.images,job,bpy.path.abspath)),flush=True)
    scene=bpy.data.scenes.get(job['scene'])
    if not scene:raise ValueError('Render scene is missing.')
    camera=scene.objects.get(job['camera'])
    if not camera or camera.type!='CAMERA':raise ValueError('Select a camera in the render scene.')
    scene.camera=camera
    scene.frame_start=job['start'];scene.frame_end=job['end']
    scene.frame_step=job.get('step',1)
    if job.get('mode')=='STILL':scene.frame_set(job['start'])
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
    advanced=apply_advanced(scene,job['advanced']) if job.get('advanced') else {}
    stage('Initializing render device')
    device=configure_device(scene,bpy.context.preferences.addons['cycles'].preferences)
    print('PIPELINE_DEVICE '+json.dumps(device),flush=True)
    scenes=[dict(name=s.name,view_layers=layer_metadata(s),use_compositing=s.render.use_compositing,
                 compositor_dependencies=compositor_dependencies(compositor_tree(s),s)) for s in bpy.data.scenes]
    chosen=selection(next(s for s in scenes if s['name']==scene.name),scenes,job.get('view_layer',''),job.get('compositor','BLENDER'),job.get('advanced'))
    layer_sample_overrides={scope[6:] for scope,prop in map(json.loads,advanced) if scope.startswith('layer:') and prop=='samples'}
    def apply_selection():
        # The render operator's layer argument does not isolate animation renders.
        for layer in scene.view_layers:
            layer.use=layer.name in chosen['view_layers']
            # A common Samples override also supersedes saved per-layer sample counts.
            # Explicit advanced layer overrides still take precedence, as in Blender.
            if layer.use and job.get('samples') is not None and layer.name not in layer_sample_overrides:
                layer.samples=0
        scene.render.use_compositing=chosen['use_compositing']
        if bpy.context.window:
            bpy.context.window.scene=scene
            bpy.context.window.view_layer=scene.view_layers[chosen['view_layers'][0]]
    apply_selection()
    passes={l['name']:l['passes'] for l in layer_metadata(scene) if l['name'] in chosen['view_layers']}
    layer_samples={}
    if scene.render.engine=='CYCLES':
        policy=getattr(scene.cycles,'use_layer_samples','USE')
        for layer in scene.view_layers:
            if layer.name in chosen['view_layers']:
                samples=layer.samples or scene.cycles.samples
                layer_samples[layer.name]=scene.cycles.samples if policy=='IGNORE' else min(samples,scene.cycles.samples) if policy=='BOUNDED' else samples
    color = {json.dumps(['color', key], separators=(',', ':')): getattr(scene.view_settings, key)
             for key in ('view_transform', 'look', 'exposure', 'gamma')}
    print('PIPELINE_SETTINGS '+json.dumps(dict(width=scene.render.resolution_x,height=scene.render.resolution_y,percentage=scene.render.resolution_percentage,samples=scene.cycles.samples if scene.render.engine=='CYCLES' else getattr(getattr(scene,'eevee',None),'taa_render_samples',None),engine=scene.render.engine,format=scene.render.image_settings.file_format,start=scene.frame_start,end=scene.frame_end,camera=camera.name,denoise=scene.cycles.use_denoising if scene.render.engine=='CYCLES' else None,advanced=advanced,color_management=color,passes=next(iter(passes.values()),[]),layer_passes=passes,layer_samples=layer_samples,**chosen)),flush=True)
    scene.render.filepath=str(Path(job['output'])/(job['prefix'] if job['prefix'].endswith('_') else job['prefix']+'_'))
    if job.get('mode')=='STILL':scene.render.filepath+=f"{job['start']:04}"
    scene.render.filepath=blender_file_path(scene.render.filepath,extra=16)
    tree=compositor_tree(scene)
    print('PIPELINE_COMPOSITOR_OUTPUTS '+json.dumps(route(tree,job['output'],job['prefix']) if chosen['use_compositing'] else []),flush=True)
    advanced_errors=[]
    def prepare(current,*args):
        if current==scene:
            stage('Rendering',frame=current.frame_current)
            try:
                if advanced:apply_advanced(current,job.get('advanced',{}))
                apply_selection()
            except Exception as exc:advanced_errors.append(str(exc))
    def written(current,*args):
        stage('Frame saved',frame=current.frame_current)
        print('PIPELINE_FRAME '+json.dumps({'frame':current.frame_current}),flush=True)
        if current==scene and advanced:
            actual=read_advanced(current,advanced)
            print('PIPELINE_ADVANCED_FRAME '+json.dumps(dict(frame=current.frame_current,settings=actual)),flush=True)
            if actual!=advanced:advanced_errors.append('Animation or a driver changed a requested render setting at frame '+str(current.frame_current)+'.')
    bpy.app.handlers.render_pre.append(prepare)
    bpy.app.handlers.render_write.append(written)
    stage('Rendering',frame=job['start'])
    ready=time.monotonic()
    try:
        bpy.ops.render.render(animation=job.get('mode')!='STILL',write_still=job.get('mode')=='STILL',scene=scene.name)
    finally:
        bpy.app.handlers.render_pre.remove(prepare)
        bpy.app.handlers.render_write.remove(written)
    print('PIPELINE_TIMING '+json.dumps(dict(load_seconds=round(ready-started,3),render_seconds=round(time.monotonic()-ready,3))),flush=True)
    if advanced_errors:raise ValueError('\n'.join(dict.fromkeys(advanced_errors)))

if __name__=='__main__':
    execute(json.loads(Path(sys.argv[sys.argv.index('--')+1]).read_text(encoding='utf-8')))
