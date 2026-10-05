bl_info={'name':'Pipeline Companion','author':'Local Pipeline','version':(1,7,0),'blender':(5,0,0),'location':'3D View > Sidebar > Pipeline','description':'Project workflow, material assignments and versioned render submission','category':'Pipeline'}
import bpy,json,os,time,uuid,hashlib,zlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request,urlopen
from urllib.parse import urlparse
from bpy.app.handlers import persistent
from bpy.props import StringProperty,BoolProperty,EnumProperty,PointerProperty
try:from .blender_linking import link_collection,link_datablock,prepare_material_slots,KINDS
except ImportError:
    import sys
    sys.path.insert(0,str(Path(__file__).parent))
    from blender_linking import link_collection,link_datablock,prepare_material_slots,KINDS
try:from . import material_assistant
except ImportError:import material_assistant

def default_connection():
    import sys
    if override := os.environ.get('PIPELINE_DATA_DIR'):
        directory=Path(override).expanduser().resolve()
    elif sys.platform=='win32':
        directory=Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData'/'Local'))/'BlenderPipeline'
    elif sys.platform=='darwin':
        directory=Path.home()/'Library'/'Application Support'/'BlenderPipeline'
    else:
        directory=Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local'/'share'))/'BlenderPipeline'
    return str(directory/'companion-connection.json')

DEFAULT_CONNECTION=default_connection()
_pool=None;_pending=[];_jobs={};_requests=[];_catalog={};_status='Start the local Pipeline tool to connect';_session=uuid.uuid4().hex;_last_beat=0;_last_saved=None;_enabled=False;_report=[];_enum_cache={}

def _connection_path():
    addon=bpy.context.preferences.addons.get(__package__ or __name__)
    return bpy.path.abspath(addon.preferences.connection_file) if addon else DEFAULT_CONNECTION
def _request(connection,action,args):
    config=json.loads(Path(connection).read_text(encoding='utf-8'))
    url=urlparse(config['url'])
    if url.scheme!='http' or url.hostname!='127.0.0.1' or not url.port:raise ValueError('Connection must point to the local Pipeline server')
    req=Request(config['url']+action,data=json.dumps(args).encode(),headers={'Content-Type':'application/json','X-Pipeline-Token':config['token']})
    try:
        with urlopen(req,timeout=4) as response:return json.load(response)
    except Exception as exc:
        if hasattr(exc,'read'):
            try:raise RuntimeError(json.loads(exc.read())['error']) from None
            except (ValueError,KeyError):pass
        raise
def _send(action,args,callback=None):
    global _status
    if not _pool:raise RuntimeError('Companion is not enabled')
    future=_pool.submit(_request,_connection_path(),action,args);_pending.append((future,callback))
    if action!='companion_heartbeat':_status='Working…'
def _enqueue(action,args,callback=None):
    parameters=dict(args)
    if _catalog.get('project_id'):parameters.setdefault('project_id',_catalog['project_id'])
    _requests.append((action,parameters,callback))

def _submit_next():
    action,args,callback=_requests.pop(0)
    def queued(result):
        global _status
        _jobs[result['job']]=(callback,action,time.monotonic());_status='Queued: '+action
    # Read the latest catalog before constructing a mutation precondition.
    def ready(catalog):
        _received(catalog)
        project=args.get('project_id') or catalog.get('project_id')
        if project!=catalog.get('project_id'):raise ValueError('Project changed. Choose the intended project again.')
        _send('async',{'action':action,**args,'project_id':project,'expected_revision':catalog.get('revision'),
                       'request_id':uuid.uuid4().hex,'client_id':_session},queued)
    _send('companion_heartbeat',_payload(),ready)
def _node():return next((n for n in _catalog.get('files',[]) if n['path'] and bpy.data.filepath and Path(n['path']).resolve()==Path(bpy.data.filepath).resolve()),None)
def _source_node(path):return next((n for n in _catalog.get('files',[]) if n.get('path') and Path(n['path']).resolve()==Path(path).resolve()),None)
def _save():
    if not bpy.data.filepath:raise ValueError('Create or join a project first to save this untitled file')
    prepare_material_slots(strict=True)
    bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)
    _send('companion_heartbeat',_payload(),_received)
def _hash(path):
    with open(path,'rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def _payload():
    return {'session_id':_session,'file':bpy.data.filepath,'dirty':bpy.data.is_dirty,'pid':os.getpid(),'version':bpy.app.version_string,
        'collections':[{'name':c.name,'objects':len(c.all_objects)} for c in list(bpy.data.collections)[:300] if not c.library],
        'libraries':[bpy.path.abspath(l.filepath) for l in list(bpy.data.libraries)[:300]],
        'overrides':sum(bool(o.override_library) for o in bpy.data.objects)}
def _received(data):
    global _catalog,_status
    _catalog=data
    for job in data.get('jobs',[]):
        if job['id'] not in _jobs or job['status'] not in {'Complete','Failed','Interrupted'}:continue
        callback,action,created=_jobs.pop(job['id'])
        if job['status']!='Complete':_status=job['error']
        else:
            _status='Done: '+action
            if callback:callback(job.get('result'))
    known={j['id'] for j in data.get('jobs',[])}
    for job_id,(callback,action,created) in list(_jobs.items()):
        if job_id not in known and time.monotonic()-created>30:_jobs.pop(job_id);_status='Tool restarted or job unavailable. Check the saved file before retrying.'
    if _status.startswith('Start the local'):_status='Connected to '+(data.get('root') or 'local Pipeline')
def _tick():
    global _status,_last_beat
    if not _enabled:return None
    for future,callback in list(_pending):
        if not future.done():continue
        _pending.remove((future,callback))
        try:
            result=future.result()
            if callback:callback(result)
        except Exception as exc:_status=str(exc)
    # Save handlers can enqueue enrollment while an operator queues its follow-up.
    # Finish our prior mutation before reading the revision for the next one.
    if _requests and not _jobs and not _pending:
        try:_submit_next()
        except Exception as exc:_status=str(exc)
    if time.monotonic()-_last_beat>2.5 and not any(not f.done() for f,_ in _pending):
        _last_beat=time.monotonic()
        try:_send('companion_heartbeat',_payload(),_received)
        except Exception as exc:_status=str(exc)
    for area in bpy.context.screen.areas if bpy.context.screen else []:
        if area.type=='VIEW_3D':area.tag_redraw()
    return .3

@persistent
def _prepare_save(_):
    global _status
    if not _enabled or not _node():return
    _,missing=prepare_material_slots(strict=False)
    if missing:_status='Prepare source material slots in the tool first: '+', '.join(missing)

@persistent
def _saved(_):
    global _last_saved
    _last_saved=bpy.data.filepath
    if _enabled and _node():_enqueue('register_working',{'source':bpy.data.filepath,'project_id':_catalog['project_id']})

def _sources(self,context):
    _enum_cache['sources']=[(n['id'],n['name'],n['path'],zlib.crc32(n['id'].encode())&0x7fffffff) for n in _catalog.get('files',[]) if n.get('path')!=bpy.data.filepath] or [('NONE','No registered sources','Refresh the project first',0)]
    return _enum_cache['sources']
def _collections(self,context):
    source=next((n for n in _catalog.get('files',[]) if n['id']==self.source),None)
    _enum_cache['collections']=[(c['name'],c['name']+' · '+str(c['objects'])+' objects',c['name'],zlib.crc32(c['name'].encode())&0x7fffffff) for c in (source or {}).get('collections',[]) if c['objects']] or [('NONE','No saved collections','Save source and refresh',0)]
    return _enum_cache['collections']
def _items(self,context):
    source=next((n for n in _catalog.get('files',[]) if n['id']==self.source),None)
    _enum_cache['items']=[(d['name'],d['name'],d.get('tree_type',''),zlib.crc32(d['name'].encode())&0x7fffffff) for d in (source or {}).get('datablocks',[]) if d['kind']==self.kind] or [('NONE','No saved datablocks','Save source and refresh',0)]
    return _enum_cache['items']

def _outputs(self,context):
    _enum_cache['outputs']=[('CONNECTED','Connected / automatic output','Use the connected folder, or create Out_<scene> if none is connected',0),
        ('NEW','New output folder','Create or reuse a project-root output folder',1)] + [
        (f['id'],f['path'],f['name'],zlib.crc32(f['id'].encode())&0x7fffffff) for f in _catalog.get('folders',[])]
    return _enum_cache['outputs']

class PIPELINE_Preferences(bpy.types.AddonPreferences):
    bl_idname=__package__ or __name__
    connection_file:StringProperty(name='Connection file',subtype='FILE_PATH',default=DEFAULT_CONNECTION)
    def draw(self,context):
        self.layout.prop(self,'connection_file');self.layout.label(text='The local tool writes this file while Launch.cmd is running.')
class PIPELINE_Settings(bpy.types.PropertyGroup):
    project_folder:StringProperty(name='Project folder',subtype='DIR_PATH')
    filename:StringProperty(name='File name',default='Untitled 001')
    create:BoolProperty(name='Create new project',default=True)
    source:EnumProperty(name='Source file',items=_sources)
    collection:EnumProperty(name='Collection',items=_collections)
    kind:EnumProperty(name='Datablock type',items=[('collections','Collections','')] + [(k,k.replace('_',' ').title(),'') for k in KINDS])
    item:EnumProperty(name='Datablock',items=_items)
    apply:EnumProperty(name='Use linked data',items=[('keep','Import reference only','No assignment; reference remains saved'),('material','Assign material','Assign to first object material slot'),('modifier','Geometry Nodes modifier','Add modifier to the selected object'),('shader','Shader setup','Create a local material using the linked shader group'),('world','Scene world','Use linked world'),('animation','Object animation','Use linked action on the selected object'),('object','Add object to scene','Use linked object')])
    target_object:StringProperty(name='Object (blank = active)')
    mode:EnumProperty(name='Link mode',items=[('instance','Collection instance','Read-only asset, move the instance as a whole'),('collection','Linked collection','Read-only objects, supports scene camera selection'),('override','Editable override','Editable object hierarchy; meshes and materials may remain linked')])
    camera:StringProperty(name='Camera name (optional)')
    material_choice:PointerProperty(name='Replacement material',type=bpy.types.Material)
    render_mode:EnumProperty(name='Frames',items=[('FRAME','Current frame','Render the current timeline frame'),('ANIMATION','Scene range','Render the scene start/end range')],default='FRAME')
    render_output:EnumProperty(name='Output',items=_outputs)
    output_folder:StringProperty(name='Folder name',default='')
    render_auto_prefix:BoolProperty(name='Automatic date + scene filename',default=True)
    render_prefix:StringProperty(name='Filename prefix',default='render')

class PIPELINE_OT_enroll(bpy.types.Operator):
    bl_idname='pipeline.enroll';bl_label='Save into project';bl_description='Create or join a project, save this working file inside it and register it in the graph'
    def execute(self,context):
        settings=context.scene.pipeline_companion;path=bpy.path.abspath(settings.project_folder)
        if not path:return self.fail('Choose a full project folder path')
        filename=settings.filename.strip()
        if not filename or any(c in filename for c in '<>:"/\\|?*'):return self.fail('Use a simple file name')
        filename=filename if filename.lower().endswith('.blend') else filename+'.blend'
        original=bpy.data.filepath;target=Path(path)/filename
        if target.exists() and str(target.resolve())!=str(Path(original).resolve() if original else ''):return self.fail('That filename exists. Choose a new name; existing files will not be overwritten.')
        create=settings.create
        def ready(catalog):
            global _catalog
            if bpy.data.filepath!=original:raise ValueError('Working file changed while preparing project. Retry.')
            _catalog=catalog
            bpy.ops.wm.save_as_mainfile(filepath=str(target))
            _enqueue('register_working',{'source':bpy.data.filepath,'project_id':catalog['project_id']})
        try:_send('companion_prepare',{'path':path,'create':create},ready)
        except Exception as exc:return self.fail(str(exc))
        return {'FINISHED'}
    def fail(self,message):self.report({'ERROR'},message);return {'CANCELLED'}
class PIPELINE_OT_snapshot(bpy.types.Operator):
    bl_idname='pipeline.save_snapshot';bl_label='Save + Snapshot';bl_description='Save Blender first, then back up the saved file in the node history'
    def execute(self,context):
        try:
            node=_node()
            if not node:raise ValueError('Register this working file in a project first')
            _save();_enqueue('snapshot',{'node_id':node['id'],'note':'Saved from Blender companion'})
            return {'FINISHED'}
        except Exception as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
class PIPELINE_OT_register(bpy.types.Operator):
    bl_idname='pipeline.register_current';bl_label='Save + Register / Refresh'
    def execute(self,context):
        try:
            if not _catalog.get('project_id'):raise ValueError('Choose a project first')
            _save();_enqueue('register_working',{'source':bpy.data.filepath,'project_id':_catalog['project_id']});return {'FINISHED'}
        except Exception as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
class PIPELINE_OT_link(bpy.types.Operator):
    bl_idname='pipeline.link_here';bl_label='Save + Link into this file';bl_description='Save a recovery snapshot, link the chosen collection in this live Blender session, then save and refresh the graph'
    def execute(self,context):
        settings=context.scene.pipeline_companion;node=_node()
        if not node:self.report({'ERROR'},'Register this file first');return {'CANCELLED'}
        try:
            _save();target=bpy.data.filepath
            def planned(plan):
                if plan['project_id']!=_catalog.get('project_id'):raise ValueError('Project changed before linking. Nothing linked; choose the project again.')
                if bpy.data.filepath!=target or bpy.data.is_dirty:raise ValueError('File changed while preparing the link. Nothing linked; retry after saving.')
                if _hash(target)!=plan['target_hash'] or _hash(plan['source'])!=plan['source_hash']:raise ValueError('Saved source or destination changed. Retry the link.')
                if plan['kind']=='collections':link_collection(plan['source'],plan['collection'],plan['mode'],plan['scene'],plan['camera'])
                else:link_datablock(plan['source'],plan['kind'],plan['item'],plan['apply'],plan['object_name'],plan['scene'])
                bpy.ops.wm.save_as_mainfile(filepath=target)
                _enqueue('register_working',{'source':target,'project_id':_catalog['project_id']})
            _enqueue('companion_link_plan',{'source_id':settings.source,'target_id':node['id'],'collection':settings.collection if settings.kind=='collections' else '',
                'mode':settings.mode,'camera':settings.camera if settings.kind=='collections' and settings.mode!='instance' else '',
                'scene':context.scene.name,'kind':settings.kind,'item':settings.item if settings.kind!='collections' else '',
                'apply':settings.apply,'object_name':settings.target_object or (context.object.name if context.object else '')},planned)
            return {'FINISHED'}
        except Exception as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
class PIPELINE_OT_local_material(bpy.types.Operator):
    bl_idname='pipeline.local_material';bl_label='Make active material a local copy';bl_description='Copy the active material for local shader editing; linked node groups keep their source links'
    bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        try:
            material_assistant.local_copy(context.object)
            self.report({'INFO'},'Local copy created. Source shader changes no longer update this copy.');return {'FINISHED'}
        except Exception as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}

class PIPELINE_OT_material_assign(bpy.types.Operator):
    bl_idname='pipeline.material_assign';bl_label='Assign material to active slot';bl_description='Use the chosen material on this object without changing shared mesh assignments'
    bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        try:
            material_assistant.assign(context.object,context.scene.pipeline_companion.material_choice)
            self.report({'INFO'},'Assigned on this object. Shared mesh materials are unchanged.');return {'FINISHED'}
        except Exception as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}

class PIPELINE_OT_material_object_slot(bpy.types.Operator):
    bl_idname='pipeline.material_object_slot';bl_label='Use object material assignment';bl_description='Keep the current shader linked while storing the assignment on this object'
    bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        try:
            material_assistant.assign(context.object,context.object.active_material if context.object else None)
            return {'FINISHED'}
        except Exception as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}

class PIPELINE_OT_material_restore(bpy.types.Operator):
    bl_idname='pipeline.material_restore';bl_label='Restore inherited material assignment';bl_description='Restore the source object binding or shared mesh binding for this slot; shader copies are not deleted'
    bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        try:material_assistant.restore(context.object);return {'FINISHED'}
        except Exception as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}

class PIPELINE_OT_material_add_slot(bpy.types.Operator):
    bl_idname='pipeline.material_add_slot';bl_label='Add a material slot';bl_description='Add a slot to local geometry; linked geometry must be prepared in its source file'
    bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        try:material_assistant.add_slot(context.object);return {'FINISHED'}
        except Exception as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}

class PIPELINE_OT_material_source(bpy.types.Operator):
    bl_idname='pipeline.material_source';bl_label='Open material source file';bl_description='Open the registered source in another Blender window'
    path:StringProperty(options={'HIDDEN'})
    def execute(self,context):
        node=_source_node(self.path)
        if not node:self.report({'ERROR'},'Register the source file in this project first');return {'CANCELLED'}
        _enqueue('launch',{'node_id':node['id']});return {'FINISHED'}
class PIPELINE_OT_reload(bpy.types.Operator):
    bl_idname='pipeline.reload_links';bl_label='Save + Reload linked assets';bl_description='Save a snapshot before reloading libraries; Blender handles automatic override resynchronization'
    def execute(self,context):
        try:
            node=_node()
            if not node:raise ValueError('Register this file first')
            _save();target=bpy.data.filepath;expected=_hash(target)
            def ready(_):
                if bpy.data.filepath!=target or bpy.data.is_dirty or _hash(target)!=expected:raise ValueError('Working file changed while preparing reload. Retry.')
                for library in list(bpy.data.libraries):
                    if not library.parent:library.reload()
                bpy.ops.wm.save_as_mainfile(filepath=target);_enqueue('register_working',{'source':target,'project_id':_catalog['project_id']})
            _enqueue('snapshot',{'node_id':node['id'],'note':'Before companion library reload'},ready);return {'FINISHED'}
        except Exception as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
class PIPELINE_OT_open_tool(bpy.types.Operator):
    bl_idname='pipeline.open_tool';bl_label='Open Pipeline interface'
    def execute(self,context):
        try:
            import webbrowser
            config=json.loads(Path(_connection_path()).read_text(encoding='utf-8'));parsed=urlparse(config['url'])
            if parsed.hostname!='127.0.0.1' or parsed.scheme!='http':raise ValueError('Invalid local tool URL')
            webbrowser.open(config['url']);return {'FINISHED'}
        except Exception as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
class PIPELINE_OT_preflight(bpy.types.Operator):
    bl_idname='pipeline.preflight';bl_label='Check saved file';bl_description='Read dependencies, camera, render setup and override warnings'
    def execute(self,context):
        node=_node()
        if not node:self.report({'ERROR'},'Register this file first');return {'CANCELLED'}
        def ready(report):
            global _report,_status
            _report=['Errors: '+str(len(report['errors'])),'Warnings: '+str(len(report['warnings'])),*report['errors'],*report['warnings']];_status='Preflight completed; see the report below'
        _enqueue('preflight_report',{'node_id':node['id']},ready);return {'FINISHED'}
class PIPELINE_OT_queue_render(bpy.types.Operator):
    bl_idname='pipeline.queue_render';bl_label='Save checkpoint + Queue render';bl_description='Save a checkpoint, then render the active scene and camera from a frozen saved copy through Pipeline'
    def execute(self,context):
        try:
            node=_node();scene=context.scene;settings=scene.pipeline_companion
            if not node:raise ValueError('Register this file first')
            if _jobs or _requests:raise ValueError('Wait for the current companion operation before submitting another render')
            if any(j['node_id']==node['id'] and j['status'] in {'Queued','Preparing','Rendering'} for j in _catalog.get('render_queue',[])):
                raise ValueError('This file is already queued. Finish or cancel its render in Pipeline first.')
            if not scene.camera:raise ValueError('Set an active scene camera before rendering')
            if scene.library:raise ValueError('Choose a local scene before rendering')
            if not settings.render_auto_prefix and not settings.render_prefix.strip():raise ValueError('Enter a filename prefix or enable automatic naming')
            destination=settings.render_output
            if destination not in {'CONNECTED','NEW'} and not any(f['id']==destination for f in _catalog.get('folders',[])):raise ValueError('Choose an available output folder')
            start,end=(scene.frame_current,scene.frame_current) if settings.render_mode=='FRAME' else (scene.frame_start,scene.frame_end)
            parameters={'node_id':node['id'],'scene':scene.name,'camera':scene.camera.name,'start':start,'end':end,
                'prefix':None if settings.render_auto_prefix else settings.render_prefix,
                'folder_name':settings.output_folder if destination=='NEW' else '',
                'folder_id':None if destination in {'CONNECTED','NEW'} else destination,'use_connected':destination=='CONNECTED'}
            _save();target=bpy.data.filepath;expected=_hash(target);project_id=_catalog['project_id']
            def checkpoint_ready(_):
                if _catalog.get('project_id')!=project_id or bpy.data.filepath!=target or bpy.data.is_dirty or _hash(target)!=expected:
                    raise ValueError('Working file or project changed after saving. Save and submit the render again.')
                _enqueue('companion_render',{**parameters,'project_id':project_id,'expected_hash':expected})
            _enqueue('snapshot',{'node_id':node['id'],'note':'Before companion render: '+scene.name+' · '+str(start)+'–'+str(end)},checkpoint_ready)
            self.report({'INFO'},'Saving checkpoint, then submitting to the Pipeline render queue.');return {'FINISHED'}
        except Exception as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
class PIPELINE_PT_panel(bpy.types.Panel):
    bl_label='Pipeline';bl_idname='PIPELINE_PT_companion';bl_space_type='VIEW_3D';bl_region_type='UI';bl_category='Pipeline'
    def draw(self,context):
        layout=self.layout;settings=context.scene.pipeline_companion
        layout.operator('pipeline.open_tool',icon='URL')
        head,box=layout.panel('pipeline_project_enrollment',default_closed=bool(_node()));head.label(text='Project enrollment')
        if box:box.prop(settings,'project_folder');box.prop(settings,'create');box.prop(settings,'filename');box.operator('pipeline.enroll')
        box=layout.box();box.label(text='Working file');box.label(text=Path(bpy.data.filepath).name if bpy.data.filepath else 'Untitled / not saved',icon='FILE_BLEND');box.label(text='Unsaved edits' if bpy.data.is_dirty else 'Saved',icon='ERROR' if bpy.data.is_dirty else 'CHECKMARK');box.operator('pipeline.register_current');box.operator('pipeline.save_snapshot')
        head,box=layout.panel('pipeline_link_assets',default_closed=True);head.label(text='Link assets into this file')
        if box:
            box.prop(settings,'source');box.prop(settings,'kind')
            if settings.kind=='collections':
                box.prop(settings,'collection');box.prop(settings,'mode')
                if settings.mode!='instance':box.prop(settings,'camera')
            else:
                box.prop(settings,'item');box.prop(settings,'apply')
                if settings.apply in {'material','modifier','shader','animation'}:box.prop(settings,'target_object')
            box.operator('pipeline.link_here');box.operator('pipeline.reload_links')
        head,box=layout.panel('pipeline_material_assistant',default_closed=True);head.label(text='Material / override assistant')
        if box:material_assistant.draw(box,context,settings,_source_node)
        head,box=layout.panel('pipeline_render_tools',default_closed=True);head.label(text='Render through Pipeline')
        if box:
            scene=context.scene;node=_node();box.label(text='Scene: '+scene.name,icon='SCENE_DATA');box.label(text='Camera: '+(scene.camera.name if scene.camera else 'Not set'),icon='CAMERA_DATA')
            box.prop(settings,'render_mode',expand=True)
            box.label(text='Frame '+str(scene.frame_current) if settings.render_mode=='FRAME' else 'Frames '+str(scene.frame_start)+'–'+str(scene.frame_end))
            box.prop(settings,'render_output')
            if settings.render_output=='NEW':box.prop(settings,'output_folder');box.label(text='Blank name creates Out_'+scene.name)
            elif settings.render_output=='CONNECTED':
                folder=next((f for f in _catalog.get('folders',[]) if f['id']==(node or {}).get('render_config',{}).get('folder_id')),None)
                box.label(text=folder['path'] if folder else 'Creates Out_'+scene.name+' on first submission',icon='FILE_FOLDER')
            box.prop(settings,'render_auto_prefix')
            if not settings.render_auto_prefix:box.prop(settings,'render_prefix')
            box.label(text='Uses this saved scene’s render settings.')
            box.label(text='Each submission gets a separate version.')
            if not node:box.label(text='Register this working file first.',icon='INFO')
            elif not scene.camera:box.label(text='Set an active scene camera first.',icon='INFO')
            job=next((j for j in reversed(_catalog.get('render_queue',[])) if j['node_id']==(node or {}).get('id')),None)
            rendering=job and job['status'] in {'Queued','Preparing','Rendering'}
            row=box.row();row.enabled=bool(node and scene.camera and not _jobs and not _requests and not rendering);row.operator('pipeline.queue_render',icon='RENDER_ANIMATION' if settings.render_mode=='ANIMATION' else 'RENDER_STILL')
            if job:
                box.label(text=job['status']+(' · '+str(job['progress'])+'%' if job['status']=='Rendering' else ''),icon='RENDER_STILL')
                box.label(text=job['scene']+' · '+str(job['start'])+'–'+str(job['end']))
                if job.get('error'):box.label(text=job['error'][:70],icon='ERROR')
                if job.get('run_id'):box.operator('pipeline.open_render_output',text='Open version folder',icon='FILE_FOLDER').run_id=job['run_id']
            box.operator('pipeline.preflight')
            for message in _report[:12]:box.label(text=message[:75])
        layout.label(text=_status[:75])

class PIPELINE_OT_open_render_output(bpy.types.Operator):
    bl_idname='pipeline.open_render_output';bl_label='Open render version folder'
    run_id:StringProperty(options={'HIDDEN'})
    def execute(self,context):
        _enqueue('render_open',{'run_id':self.run_id});return {'FINISHED'}

_classes=(PIPELINE_Preferences,PIPELINE_Settings,PIPELINE_OT_enroll,PIPELINE_OT_snapshot,PIPELINE_OT_register,PIPELINE_OT_link,PIPELINE_OT_reload,PIPELINE_OT_local_material,PIPELINE_OT_material_assign,PIPELINE_OT_material_object_slot,PIPELINE_OT_material_restore,PIPELINE_OT_material_add_slot,PIPELINE_OT_material_source,PIPELINE_OT_preflight,PIPELINE_OT_queue_render,PIPELINE_OT_open_render_output,PIPELINE_OT_open_tool,PIPELINE_PT_panel)
def register():
    global _pool,_enabled,_session
    _session=uuid.uuid4().hex;_pending.clear();_jobs.clear();_requests.clear()
    for cls in _classes:bpy.utils.register_class(cls)
    bpy.types.Scene.pipeline_companion=PointerProperty(type=PIPELINE_Settings)
    _pool=ThreadPoolExecutor(max_workers=1);_enabled=True
    if _saved not in bpy.app.handlers.save_post:bpy.app.handlers.save_post.append(_saved)
    if _prepare_save not in bpy.app.handlers.save_pre:bpy.app.handlers.save_pre.append(_prepare_save)
    bpy.app.timers.register(_tick,first_interval=.5,persistent=True)
def unregister():
    global _enabled,_pool
    _enabled=False
    _requests.clear()
    if _saved in bpy.app.handlers.save_post:bpy.app.handlers.save_post.remove(_saved)
    if _prepare_save in bpy.app.handlers.save_pre:bpy.app.handlers.save_pre.remove(_prepare_save)
    if bpy.app.timers.is_registered(_tick):bpy.app.timers.unregister(_tick)
    if _pool:
        _pool.submit(_request,_connection_path(),'companion_goodbye',{'session_id':_session});_pool.shutdown(wait=False,cancel_futures=False);_pool=None
    del bpy.types.Scene.pipeline_companion
    for cls in reversed(_classes):bpy.utils.unregister_class(cls)
