"""Explicit output scopes, selective settings and owned render-version cleanup."""
import copy, json, math, re, shutil
from pathlib import Path
from blender_pipeline.project.model import META, name, stamp, digest
from blender_pipeline.project.folders import dated_prefix
from blender_pipeline.blender.blender_render_settings import validate as validate_advanced
from blender_pipeline.blender.render_layers import selection

class RenderManagement:
    def companion_render(self,node_id,scene,camera,start,end,percentage=None,prefix=None,folder_name='',folder_id=None,use_connected=True,expected_hash=None,allow_image_warnings=False):
        """Submit the saved active scene without replacing graph render overrides."""
        with self.lock:
            node=self.node(node_id)
            if node['type']!='blend' or node.get('external'):raise ValueError('Register a managed working Blend File first.')
            if expected_hash and digest(self.path(node))!=expected_hash:raise ValueError('Working file changed after its checkpoint. Save and submit again.')
            if any(q['node_id']==node_id and q['status'] in {'Queued','Preparing','Rendering'} for q in self.data.get('render_queue',[])):
                raise ValueError('This file is already queued. Finish or cancel its render first.')
            self.refresh(node_id)
            saved=next((s for s in node['scan'].get('scenes',[]) if s['name']==scene and not s.get('linked')),None)
            if not saved or camera not in saved['cameras']:raise ValueError('Choose a saved local scene with an active camera.')
            values=self.checked_overrides({'start':start,'end':end,**({'percentage':percentage} if percentage is not None else {})})
            if values['end']<values['start'] or values['end']-values['start']>10000:raise ValueError('Invalid frame range.')
            automatic=prefix is None
            prefix=dated_prefix(scene) if automatic else name(prefix)
            # Fail dependency/unsaved-input checks before creating any output directories.
            if type(allow_image_warnings) is not bool:raise ValueError('Image warning consent must be enabled or disabled.')
            expected_inputs=self.capture_render_inputs(node,allow_image_warnings=allow_image_warnings)
            if expected_hash and expected_inputs.get(node['path'])!=expected_hash:raise ValueError('Working file changed after its checkpoint. Save and submit again.')
            connected=copy.deepcopy(node.get('render_config') or {})
            operation=next((t for t in self.render_targets() if t.get('source_id')==node_id and t['render_config']['scene']==scene),None) if not connected else None
            if not connected and operation:connected=copy.deepcopy(operation['render_config'])
            destination=folder_id or (connected.get('folder_id') if use_connected else None)
            if destination:
                folder=self.node(destination)
                if folder['type']!='folder':raise ValueError('Choose an output folder node.')
            else:
                folder_name=name(folder_name or 'Out_'+scene)
                folder=next((n for n in self.data['nodes'] if n['type']=='folder' and n['path']==folder_name),None)
                if not folder:
                    self.folder(folder_name);folder=self.data['nodes'][-1]
                destination=folder['id']
            # A new target becomes visible in the graph; existing per-scene overrides survive.
            if not connected:
                self.render_config(node_id,destination,scene,auto_prefix=True)
            elif not operation and connected.get('folder_id')!=destination:
                node['render_config']={**connected,'folder_id':destination};self.save()
            settings={'folder_id':destination,'scene':scene,'camera':camera,**values,'percentage':percentage,'prefix':prefix,'auto_prefix':automatic}
            if operation:
                settings.update({k:connected[k] for k in ('operation_id','target_id','output_subfolder')})
            result=self.queue_render(node_id,settings=settings,label='From Blender · '+scene,expected_inputs=expected_inputs,allow_image_warnings=allow_image_warnings)
            job=self.data['render_queue'][-1]
            result['companion_result']={'queue_id':job['id'],'node_id':node_id,'scene':scene,'start':start,'end':end,'folder_id':destination}
            return result

    def read_render_settings(self,node_id):
        with self.lock:
            node=self.node(node_id)
            if node['type']!='blend':raise ValueError('Choose a Blend File.')
            return {'scenes':{scene['name']:copy.deepcopy(scene.get('advanced_settings',[])) for scene in node.get('scan',{}).get('scenes',[])}}

    def render_targets(self,folder_id=None):
        folders={n['id']:n for n in self.data['nodes'] if n['type']=='folder'}
        allowed=set(folders)
        if folder_id:
            root=self.node(folder_id)
            if root['type']!='folder':raise ValueError('Choose a folder scope.')
            allowed={folder_id}
            # Graph nesting remains meaningful even when its physical paths differ.
            for f in folders.values():
                current=f;seen=set()
                while current.get('group') in folders and current['id'] not in seen:
                    seen.add(current['id']);current=folders[current['group']]
                    if current['id']==folder_id:allowed.add(f['id']);break
                if self.path(f).is_relative_to(self.path(root)):allowed.add(f['id'])
        return [n for n in self.data['nodes'] if n['type']=='blend' and not n.get('external') and n.get('render_config',{}).get('folder_id') in allowed]

    def checked_overrides(self,settings):
        settings=copy.deepcopy(settings or {})
        ranges={'width':(4,65536),'height':(4,65536),'percentage':(1,100),'samples':(1,1048576),'start':(-1048574,1048574),'end':(-1048574,1048574),'step':(1,10000)}
        enums={'engine':{'CYCLES','BLENDER_EEVEE'},'format':{'PNG','OPEN_EXR','OPEN_EXR_MULTILAYER','JPEG','FFMPEG'}}
        for key,value in settings.items():
            if key=='advanced':
                if not isinstance(value,dict) or len(value)>1000:raise ValueError('Invalid advanced render settings.')
                for path,item in value.items():
                    if not isinstance(path,str) or len(path)>512:raise ValueError('Invalid render setting identifier.')
                    parts=json.loads(path)
                    if not isinstance(parts,list) or len(parts)!=2 or any(not isinstance(p,str) for p in parts):raise ValueError('Invalid render setting identifier.')
                    values=item if isinstance(item,list) else [item]
                    if len(values)>64 or any(type(v) not in {bool,int,float,str} or isinstance(v,float) and not math.isfinite(v) for v in values):raise ValueError('Invalid advanced render value.')
            elif key in ranges:
                if isinstance(value,bool) or str(value).strip()!=str(int(value)):raise ValueError('Use a whole number for '+key+'.')
                value=int(value);low,high=ranges[key]
                if not low<=value<=high:raise ValueError('Invalid '+key+'.')
                settings[key]=value
            elif key in enums:
                if value not in enums[key]:raise ValueError('Unsupported '+key+'.')
            elif key=='denoise':
                if type(value) is not bool:raise ValueError('Denoising must be true or false.')
            else:raise ValueError('Unsupported render override: '+key)
        return settings

    def effective_render(self,node,config,overrides=None):
        if not config:raise ValueError(node['name']+': connect an output folder first.')
        result=copy.deepcopy(config);overrides=self.checked_overrides(overrides)
        advanced={**result.get('advanced',{}),**overrides.get('advanced',{})}
        result.update({k:v for k,v in overrides.items() if k!='advanced'})
        if result.get('prefix') is not None:result['prefix']=name(result['prefix'])
        scene=next((s for s in node.get('scan',{}).get('scenes',[]) if s['name']==result['scene'] and not s.get('linked')),None)
        if not scene:raise ValueError(node['name']+': refresh and select a saved local scene.')
        if advanced:result['advanced']=validate_advanced(advanced,scene.get('advanced_settings',[]))
        else:result.pop('advanced',None)
        result.update(selection(scene, node.get('scan',{}).get('scenes',[]), result.get('view_layer',''), result.get('compositor','BLENDER'), advanced))
        if self.node(result['folder_id'])['type']!='folder':raise ValueError('Output folder is missing.')
        result['camera']=result.get('camera') or scene.get('camera')
        if result['camera'] not in scene['cameras']:raise ValueError(node['name']+': choose a saved scene camera.')
        for key in ('start','end'):
            if result.get(key) is None:result[key]=scene[key]
        if result.get('step') is None:result['step']=scene.get('step',1)
        if result.get('mode')=='STILL':
            frame=result.get('frame') if result.get('frame') is not None else scene.get('current_frame',scene['start'])
            result['start']=result['end']=frame
            if (result.get('format') or scene.get('format'))=='FFMPEG':raise ValueError('A still setup requires an image format, not video. Choose PNG or OpenEXR.')
        values={k:v for k,v in result.items() if k in {'width','height','percentage','samples','start','end','step','engine','format','denoise'} and v is not None}
        result.update(self.checked_overrides(values))
        engine=result.get('engine') or scene.get('engine')
        if result.get('denoise') is not None and engine!='CYCLES':raise ValueError(node['name']+': denoising override requires Cycles. Disable it or override the engine to Cycles.')
        if result.get('samples') is not None and engine not in {'CYCLES','BLENDER_EEVEE'}:raise ValueError(node['name']+': samples override requires Cycles or EEVEE.')
        if result['end']<result['start'] or result['end']-result['start']>10000:raise ValueError('Invalid frame range for '+node['name']+'.')
        result['_batch_overrides']=overrides
        return result

    def batch_settings(self,folder_id=None,overrides=None):
        checked=self.checked_overrides(overrides)
        target=self.node(folder_id) if folder_id else self.data
        if folder_id and target['type']!='folder':raise ValueError('Choose a folder.')
        target['render_overrides']=checked;self.save();return self.state()

    def render_delete(self,run_id,confirmed=False):
        if confirmed is not True:raise ValueError('Confirm permanent render-version deletion.')
        run=next((r for r in self.data.get('renders',[]) if r['id']==run_id),None)
        if not run:raise ValueError('Render version not found.')
        if run['status']=='Deleted':return self.state()
        if run['status'] in {'Preparing','Rendering'} or any(q.get('run_id')==run_id and q['status'] in {'Preparing','Rendering'} for q in self.data.get('render_queue',[])):raise ValueError('Cancel and finish this render before deleting it.')
        output=(self.root/run['output']).resolve();inputs=(self.root/run['inputs']).resolve()
        # Never allow a record to recursively remove a project or arbitrary directory.
        if output==self.root or not output.is_relative_to(self.root) or output.is_relative_to(self.root/META):raise ValueError('Invalid render output directory.')
        if not re.fullmatch('[a-f0-9]{32}',run_id) or not inputs.is_relative_to(self.root) or inputs!=(self.root/META/'render-inputs'/run_id).resolve():raise ValueError('Invalid frozen-input directory.')
        if output.exists():
            job=json.loads((output/'render-job.json').read_text(encoding='utf-8'))
            if Path(job['output']).resolve()!=output or not Path(job['input']).resolve().is_relative_to(inputs):raise ValueError('Render ownership check failed.')
            if job.get('run_id',run_id)!=run_id:raise ValueError('Render version identity does not match.')
            if output.name!=Path(job['input']).stem+f"_r{run['number']:03}":raise ValueError('Unexpected render version directory name.')
            if any(p.suffix.lower()=='.blend' for p in output.rglob('*')):raise ValueError('Output directory contains working Blend Files; cleanup stopped.')
        # Resolve every descendant before deletion, rejecting links/junctions outside its owner.
        for directory in (output,inputs):
            if directory.exists():
                if any(p.is_symlink() or p.is_junction() or not p.resolve().is_relative_to(directory) for p in directory.rglob('*')):raise ValueError('Linked directories cannot be deleted as render versions.')
        for directory in (output,inputs):
            if directory.exists():shutil.rmtree(directory)
        run.update(status='Deleted',deleted_at=stamp(),size_bytes=0,input_bytes=0,file_count=0,detail='')
        self._folder_cache={};self.save();return self.state()

    def render_sizes(self,run):
        for key,field in [('output','size_bytes'),('inputs','input_bytes')]:
            directory=(self.root/run[key]).resolve()
            paths=[p for p in directory.rglob('*') if p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(directory)]
            run[field]=sum(p.stat().st_size for p in paths)
            if key=='output':
                run['file_count']=sum(p.suffix.lower() not in {'.json','.log'} for p in paths)
                run['image_count']=sum(p.suffix.lower() in {'.png','.jpg','.jpeg','.exr','.tif','.tiff','.webp','.bmp'} for p in paths)
