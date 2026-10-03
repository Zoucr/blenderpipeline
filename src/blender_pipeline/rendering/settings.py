"""Explicit output scopes, selective settings and owned render-version cleanup."""
import copy, json, math, re, shutil
from pathlib import Path
from blender_pipeline.project.model import META, name, stamp
from blender_pipeline.blender.blender_render_settings import validate as validate_advanced

class RenderManagement:
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
        ranges={'width':(4,65536),'height':(4,65536),'percentage':(1,100),'samples':(1,1048576),'start':(-1048574,1048574),'end':(-1048574,1048574)}
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
        if self.node(result['folder_id'])['type']!='folder':raise ValueError('Output folder is missing.')
        result['camera']=result.get('camera') or scene.get('camera')
        if result['camera'] not in scene['cameras']:raise ValueError(node['name']+': choose a saved scene camera.')
        for key in ('start','end'):
            if result.get(key) is None:result[key]=scene[key]
        values={k:v for k,v in result.items() if k in {'width','height','percentage','samples','start','end','engine','format','denoise'} and v is not None}
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
            if key=='output':run['file_count']=sum(p.suffix.lower() not in {'.json','.log'} for p in paths)
