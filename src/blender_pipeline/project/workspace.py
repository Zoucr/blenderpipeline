"""Workspace editing, portable archives and recorded local rendering."""
import copy, json, os, re, shutil, subprocess, tempfile, threading, time, zipfile
from datetime import datetime
from pathlib import Path
from blender_pipeline.project.model import Pipeline as BasePipeline, META, uid, stamp, digest, name, atomic_json
from blender_pipeline.paths import BLENDER_SCRIPTS_DIR
from blender_pipeline import __version__
from blender_pipeline.rendering.queue import RenderQueue
from blender_pipeline.project.templates import Templates
from blender_pipeline.project.external_libraries import ExternalLibraries
from blender_pipeline.project.folders import FolderWorkflow,dated_prefix
from blender_pipeline.rendering.settings import RenderManagement
from blender_pipeline.project.graph_nodes import GraphNodes
from blender_pipeline.exporting.service import ExportWorkflow
from blender_pipeline.blender.export_settings import EXPORT_SETTINGS
from blender_pipeline.rendering.graph import RenderGraph
from blender_pipeline.project.dependencies import dependency_health, file_signature
from blender_pipeline.project.node_editing import NodeEditing
from blender_pipeline.rendering.inputs import warning_keys
from blender_pipeline.rendering.images import image_identity, freeze_images
from blender_pipeline.rendering.progress import read_markers
from blender_pipeline.rendering.worker import RenderWorker
from blender_pipeline.rendering.environment import render_environment
from blender_pipeline.adapters.background_process import start_background_process, cleanup_background_process

class Pipeline(NodeEditing,RenderGraph,ExportWorkflow,GraphNodes,RenderManagement,FolderWorkflow,ExternalLibraries,Templates,RenderQueue,BasePipeline):
    def __init__(self, repository=None, runtime=None, desktop=None, resolver=None, data_directory=None):
        super().__init__(repository=repository, runtime=runtime, desktop=desktop, resolver=resolver, data_directory=data_directory)
        self.lock=threading.RLock()
        self.render_processes={}
        self.render_cancelled=set()
        self.companion=None
        self.global_template_config=self.settings_directory/'startup-default.json'
    def stop_render_workers(self):
        """Stop owned background workers when the local application's console closes."""
        with self.lock:
            self._render_shutdown=True
            for item in self.data.get('render_queue',[]) if self.data else []:
                if item['status'] in {'Queued','Preparing','Rendering'}:
                    item.update(status='Cancelled',error='Local application closed.',finished=stamp())
            for identity,process in list(self.render_processes.items()):
                self.render_cancelled.add(identity)
                if process.poll() is None:process.terminate()
            worker=getattr(self,'_render_worker',None)
            if worker:worker.stop()
            if self.data:self.save()
    def save(self):
        with self.lock: super().save()
    def archive_blend(self,node_id,closed=False):
        node=self.node(node_id)
        if node['type']!='blend':raise ValueError('Select a Blend File.')
        self.ensure_closed(node,closed)
        if self.render_busy():raise ValueError('Finish or cancel the render queue before archiving files.')
        self.refresh()
        source=self.path(node)
        if not source.is_file():raise ValueError('The working file is missing. Locate it before archiving.')
        dependents=[]
        for other in self.data['nodes']:
            if other['type']!='blend' or other['id']==node_id:continue
            if other.get('scan',{}).get('error'):raise ValueError('Resolve scan errors before archiving so dependency checks can complete.')
            if any(r.get('kind')=='Library' and os.path.normcase(str(Path(r['path']).resolve()))==os.path.normcase(str(source)) for r in other.get('scan',{}).get('refs',[])):dependents.append(other['name'])
        if dependents:raise ValueError('This file is used by: '+', '.join(dependents)+'. Unlink or replace those dependencies before archiving.')
        archive_id=uid();directory=(self.root/META/'archive'/archive_id).resolve()
        if not directory.is_relative_to((self.root/META/'archive').resolve()):raise ValueError('Invalid archive location.')
        directory.mkdir(parents=True);target=directory/source.name
        record={'id':archive_id,'archived_at':stamp(),'node':copy.deepcopy(node),'path':target.relative_to(self.root).as_posix(),'hash':digest(source)}
        before=copy.deepcopy(self.data)
        os.replace(source,target)
        try:
            if digest(target)!=record['hash']:raise ValueError('The file changed during archiving. Save and close it before retrying.')
            self.data['nodes']=[n for n in self.data['nodes'] if n['id']!=node_id]
            self.data.setdefault('archived_files',[]).append(record);self.save()
        except Exception:
            self.data=before;os.replace(target,source);raise
        return self.state()
    def restore_archived(self,archive_id):
        if self.render_busy():raise ValueError('Finish or cancel the render queue before restoring archived files.')
        record=next((r for r in self.data.get('archived_files',[]) if r['id']==archive_id),None)
        if not record:raise ValueError('Archived file not found.')
        node=copy.deepcopy(record['node']);target=self.path(node);source=(self.root/record['path']).resolve()
        if not source.is_relative_to((self.root/META/'archive').resolve()):raise ValueError('Invalid archive path.')
        if target.exists() or any(n['id']==node['id'] or n.get('path')==node['path'] for n in self.data['nodes']):raise ValueError('The original path is occupied. Move or rename the replacement before restoring.')
        if not source.is_file() or digest(source)!=record['hash']:raise ValueError('Archived file is missing or changed; restore stopped.')
        target.parent.mkdir(parents=True,exist_ok=True);before=copy.deepcopy(self.data);os.replace(source,target)
        try:
            if not any(n['id']==node.get('group') and n['type'] in {'folder','frame'} for n in self.data['nodes']):node['group']=None
            node['hidden']=False;node.pop('last_error',None);self.data['nodes'].append(node)
            self.data['archived_files']=[r for r in self.data['archived_files'] if r['id']!=archive_id]
            self.inspect(node);self.save()
        except Exception:
            self.data=before;os.replace(target,source);raise
        return self.state()
    def create(self,parent,title,preset='empty'):
        if self.render_busy():raise ValueError('Finish or cancel the render queue before switching projects.')
        if preset not in {'empty','asset_shots','product_stills'}:raise ValueError('Unknown project preset')
        super().create(parent,title)
        if preset!='empty':
            names=['Assets','Shots','Outputs'] if preset=='asset_shots' else ['Models','Lighting','Cameras','Outputs']
            for i,folder in enumerate(names):self.folder(folder,x=50+(i%2)*750,y=50+(i//2)*500)
        return self.state()
    def state(self):
        result=super().state();result['build']=__version__
        result['export_settings']=EXPORT_SETTINGS
        try:result['app_startup']=json.loads(self.global_template_config.read_text(encoding='utf-8'))
        except (OSError,ValueError):result['app_startup']=None
        if self.companion:
            result['live']=self.companion.live()
            if self.data:
                for n in self.data['nodes']:
                    if n['type']=='blend':
                        try:sessions=self.companion.opened(self.path(n))
                        except ValueError:sessions=[]
                        if sessions:result.setdefault('open',[]).append(n['id'])
        if self.data:
            result['folder_info']={n['id']:self.folder_inventory(n) for n in self.data['nodes'] if n['type']=='folder' and not n.get('hidden')}
            for node in self.data['nodes']:
                node.setdefault('group',None);node.setdefault('hidden',False)
            self.data.setdefault('renders',[])
            result['updates']={}
            lookup={}
            for n in self.data['nodes']:
                if n['type']=='blend':
                    try:lookup[os.path.normcase(str(self.path(n)))]=n
                    except ValueError:pass
            for node in self.data['nodes']:
                if node['type']!='blend':continue
                updates=[]
                for ref in node.get('scan',{}).get('refs',[]):
                    if ref['kind']!='Library':continue
                    source=lookup.get(os.path.normcase(str(Path(ref['path']).resolve())))
                    if source and source.get('scan',{}).get('hash')!=node.get('dependency_hashes',{}).get(source['id']):updates.append(source['id'])
                if updates:result['updates'][node['id']]=updates
        if self.data:
            result['health']=dependency_health(self,result.get('files',{}))
            result['render_targets']=[{k:n[k] for k in ('id','source_id','operation_id','target_id','name','render_config') if k in n} for n in self.render_targets()]
            # Large RNA catalogues are served only when a settings browser requests them.
            result['project']['nodes']=[{**n,'scan':{**n.get('scan',{}),'scenes':[{**{k:v for k,v in s.items() if k!='advanced_settings'},'advanced_setting_count':len(s.get('advanced_settings',[]))} for s in n.get('scan',{}).get('scenes',[])]}} if n['type']=='blend' else n for n in result['project']['nodes']]
        return result
    def load(self,path):
        if self.render_busy():raise ValueError('Finish or cancel the render queue before switching projects.')
        result=super().load(path)
        for queued in self.data.get('render_queue',[]):
            if queued['status'] in {'Queued','Preparing','Rendering'}:queued.update(status='Interrupted',error='Queue stopped when the previous app session ended.')
        for run in self.data.get('renders',[]):
            if run['status'] in {'Rendering','Preparing','Queued'} and run['id'] not in self.render_processes:
                run.update(status='Interrupted',error='The previous application session ended. Its render process may still need to be stopped manually.')
        self.save();return self.state()
    def inspect(self,node):
        previous=node.get('scan',{})
        baseline=copy.deepcopy(node.get('dependency_hashes',{}))
        super().inspect(node)
        if not node.get('scan',{}).get('error'):
            unchanged=previous.get('hash') and previous['hash']==node['scan'].get('hash')
            node['dependency_hashes']={}
            for source in self.data.get('nodes',[]) if self.data else []:
                if source['type']!='blend':continue
                try:
                    source_path=self.path(source)
                    if any(r['kind']=='Library' and os.path.normcase(str(Path(r['path']).resolve()))==os.path.normcase(str(source_path)) for r in node['scan']['refs']):node['dependency_hashes'][source['id']]=baseline[source['id']] if unchanged and source['id'] in baseline else digest(source_path)
                except (OSError,ValueError):pass
            if previous.get('hash') and not unchanged:
                before={(d['kind'],d['name']) for d in previous.get('datablocks',[])}
                after={(d['kind'],d['name']) for d in node['scan'].get('datablocks',[])}
                node['content_changes']={'added':[{'kind':k,'name':v} for k,v in sorted(after-before)][:20],'removed':[{'kind':k,'name':v} for k,v in sorted(before-after)][:20],'at':stamp(),'hash':node['scan'].get('hash')}
    def create_blend(self,title=None,folder_id=None,template=None,x=None,y=None,template_id=None):
        chosen=template_id if template_id is not None else self.data.get('default_template','')
        if template:chosen=''
        if not template and template_id is None and not chosen:
            chosen=self.capture_app_startup()
        if chosen=='__factory__':chosen=''
        if chosen and not template:
            _,path=self.template_entry(chosen);template=str(path)
        physical=self.physical_folder(folder_id)
        parent=self.path(self.node(physical)) if physical else self.root
        display_name=self.new_blend_name(title,parent)
        naming={'date':datetime.now().strftime('%y%m%d'),'version':1}
        result=super().create_blend(self.blend_filename(display_name,naming),physical,template,x,y)
        self.data['nodes'][-1].update(name=display_name,file_naming=naming)
        self.data['nodes'][-1]['group']=folder_id
        if chosen:self.data['nodes'][-1]['startup_template']=chosen
        self.save();return self.state()
    def import_blend(self,*args,**kwargs):
        folder=kwargs.get('folder_id',args[1] if len(args)>1 else None)
        args=list(args)
        if len(args)>1:args[1]=self.physical_folder(folder)
        else:kwargs['folder_id']=self.physical_folder(folder)
        result=super().import_blend(*args,**kwargs)
        self.data['nodes'][-1]['group']=folder;self.save();return self.state()
    def folder(self,title=None,folder_id=None,x=None,y=None,node_ids=None,width=650,height=420):
        members=[self.node(i) for i in dict.fromkeys(node_ids or [])]
        if folder_id and any(n['id']==folder_id for n in members):raise ValueError('A selected folder cannot also be the parent.')
        width,height=max(300,float(width)),max(150,float(height))
        provisional=copy.deepcopy(self.data['nodes']);frame_id=uid()
        provisional.append({'id':frame_id,'type':'folder','group':folder_id})
        for node in provisional:
            if node['id'] in {n['id'] for n in members}:node['group']=frame_id
        self.validate_groups(provisional)
        if not title:
            physical=self.physical_folder(folder_id)
            parent=self.path(self.node(physical)) if physical else self.root;number=1
            while (parent/f'Folder {number:03}').exists():number+=1
            title=f'Folder {number:03}'
        super().folder(title,self.physical_folder(folder_id),x,y);frame=self.data['nodes'][-1]
        frame.update(width=width,height=height,collapsed=False,group=folder_id)
        for node in members:node['group']=frame['id']
        self.validate_groups(self.data['nodes'])
        self.fit_frames()
        self.save();return self.state()
    def snapshot(self,node_id,note=''):
        if self.node(node_id).get('external'):raise ValueError('Collect this external library into the project before managing its history.')
        result=super().snapshot(node_id,note)
        self.node(node_id)['snapshots'][-1]['origin_path']=self.node(node_id)['path'];self.save();return self.state()
    def snapshot_note(self,node_id,snapshot_id,note,checkpoint=False):
        item=next(s for s in self.node(node_id)['snapshots'] if s['id']==snapshot_id)
        item.update(note=str(note)[:1000],checkpoint=bool(checkpoint));self.save();return self.state()
    def graph_edit(self,node_id,group=None,collapsed=None,history_open=None,hidden=None,width=None,height=None,collections_closed=None,notes=None,color=None,stage=None,pinned_collections=None):
        node=self.node(node_id)
        if group:
            if self.node(group)['type'] not in {'folder','frame'} or group==node_id:raise ValueError('Choose a different frame or folder.')
            check=copy.deepcopy(self.data['nodes'])
            next(n for n in check if n['id']==node_id)['group']=group
            self.validate_groups(check)
        node['group']=group
        if pinned_collections is not None:node['pinned_collections']=list(dict.fromkeys(str(c) for c in pinned_collections))[:100]
        for key,value in [('collapsed',collapsed),('history_open',history_open),('hidden',hidden),('collections_closed',collections_closed)]:
            if value is not None:node[key]=bool(value)
        if width is not None:node['width']=max(300,float(width))
        if height is not None:node['height']=max(150,float(height))
        if notes is not None:node['notes']=str(notes)[:5000]
        if color is not None:
            if color not in {'default','blue','green','purple','orange','red'}:raise ValueError('Choose a supported node color.')
            node['color']=color
        if stage is not None:
            if stage not in {'draft','working','review','ready','done','blocked'}:raise ValueError('Choose a supported workflow stage.')
            node['stage']=stage
        self.save();return self.state()
    def dismiss_error(self,node_id):
        node=self.node(node_id);node.pop('last_error',None);self.save();return self.state()
    def ensure_closed(self,node,acknowledged):
        if self.companion and self.companion.opened(self.path(node)):
            raise ValueError('The companion reports this file open in Blender. Close it before background editing, or perform the link inside Blender.')
        return super().ensure_closed(node,acknowledged)
    def register_working(self,source,project_id):
        if not self.data or self.data['id']!=project_id:raise ValueError('Project changed. Choose the project again in Blender.')
        source=Path(source).resolve()
        if not source.is_file() or source.suffix.lower()!='.blend' or not source.is_relative_to(self.root) or source.is_relative_to(self.root/META):raise ValueError('Save the working file inside the chosen project first.')
        existing=next((n for n in self.data['nodes'] if n['type']=='blend' and self.path(n)==source),None)
        if existing:
            self.inspect(existing);self.save();return self.state()
        return self.import_blend(source)
    def companion_link_plan(self,source_id,target_id,collection='',mode='instance',camera='',scene='',kind='collections',item='',apply='keep',object_name=''):
        source,target=self.node(source_id),self.node(target_id)
        if mode not in {'instance','collection','override'} or source_id==target_id:raise ValueError('Invalid link mode or self-link.')
        self.refresh()
        if any(n.get('scan',{}).get('error') for n in self.data['nodes'] if n['type']=='blend'):raise ValueError('Resolve scan errors before linking.')
        if kind=='collections':
            detail=next((c for c in source['scan']['collection_details'] if c['name']==collection),None)
            if not detail or not detail['objects']:raise ValueError('Choose a saved non-empty collection.')
        elif not any(d['kind']==kind and d['name']==item for d in source['scan'].get('datablocks',[])):raise ValueError('Choose a saved datablock from the source file.')
        pending=[source];seen=set()
        while pending:
            node=pending.pop()
            if node['id']==target_id:raise ValueError('This link would create a dependency cycle.')
            if node['id'] in seen:continue
            seen.add(node['id'])
            for ref in node['scan']['refs']:
                if ref['kind']!='Library':continue
                linked=next((n for n in self.data['nodes'] if n['type']=='blend' and self.path(n)==Path(ref['path']).resolve()),None)
                if not linked:raise ValueError('Register external linked files before adding links.')
                pending.append(linked)
        if kind=='collections' and any(i['source']==str(self.path(source)) and i['collection']==collection for i in target['scan'].get('instances',[])):raise ValueError('Collection is already linked into this file.')
        if kind!='collections' and any(i['source']==str(self.path(source)) and i['kind']==kind and i['name']==item for i in target['scan'].get('data_links',[])):raise ValueError('Datablock already linked into this file.')
        self.snapshot(target_id,'Before link: '+(collection or item))
        result=self.state();result['companion_result']={'project_id':self.data['id'],'source':str(self.path(source)),'target':str(self.path(target)),'collection':collection,'mode':mode,'camera':camera,'scene':scene,'kind':kind,'item':item,'apply':apply,'object_name':object_name,'source_hash':digest(self.path(source)),'target_hash':digest(self.path(target))}
        return result
    def link_data(self,source_id,target_id,kind,item,closed,apply='keep',object_name='',scene='',unlink=False):
        target=self.node(target_id);source=self.node(source_id);self.ensure_closed(target,closed)
        if unlink:
            self.snapshot(target_id,'Before unlinking '+item)
            plan={'source':str(self.path(source)),'kind':kind,'item':item}
        else:plan=self.companion_link_plan(source_id,target_id,kind=kind,item=item,apply=apply,object_name=object_name,scene=scene)['companion_result']
        self.transaction(target,{'action':'unlink_data' if unlink else 'link_data',**plan})
        self.inspect(target);self.save();return self.state()
    def prepare_materials(self,node_id,closed=False):
        self.ensure_closed(self.node(node_id),closed);self.refresh()
        order=[];seen=set();required={}
        def visit(node):
            if node['id'] in seen:return
            seen.add(node['id'])
            if node.get('scan',{}).get('error'):raise ValueError('Resolve file scan errors before preparing materials.')
            for obj in node['scan'].get('objects',[]):
                if not obj.get('reference') or obj.get('reference_slots') is None:continue
                needed=max(1,len(obj.get('material_slots',[])))
                if obj['reference_slots']>=needed:continue
                override=next((o for o in node['scan'].get('overrides',[]) if o['name']==obj['name'] and o['reference']==obj['reference']),None)
                source=next((n for n in self.data['nodes'] if n['type']=='blend' and override and self.path(n)==Path(override['source']).resolve()),None)
                if not source:raise ValueError('Register the object source before preparing its material slots.')
                self.ensure_closed(source,closed)
                slots=required.setdefault(source['id'],{});slots[obj['reference']]=max(slots.get(obj['reference'],0),needed)
                visit(source)
            order.append(node)
        visit(self.node(node_id))
        for node in order:self.ensure_closed(node,closed)
        # Snapshot every affected file before the first write. Each write is atomic.
        for node in order:self.snapshot(node['id'],'Before persistent material slot preparation')
        for node in order:
            self.transaction(node,{'action':'prepare_materials','reload':True,'required_slots':required.get(node['id'],{})})
            self.inspect(node)
        self.save();return self.state()
    def link_batch(self,source_id,target_id,items,closed,mode='override',scene='',camera='',prepare_source=False):
        from blender_pipeline.blender.blender_linking_schema import validate_items
        items=validate_items(items)
        source,target=self.node(source_id),self.node(target_id)
        if source_id==target_id or source['type']!='blend' or target['type']!='blend':raise ValueError('Choose two different Blend Files.')
        if mode not in {'override','collection','instance'}:raise ValueError('Choose a supported link mode.')
        self.ensure_closed(target,closed);self.refresh()
        if any(n.get('scan',{}).get('error') for n in self.data['nodes'] if n['type']=='blend'):raise ValueError('Resolve scan errors before linking.')
        if scene and not any(s['name']==scene and not s['linked'] for s in target['scan'].get('scenes',[])):raise ValueError('Choose a local destination scene.')
        pending=[source];seen=set()
        while pending:
            node=pending.pop()
            if node['id']==target_id:raise ValueError('This link would create a dependency cycle.')
            if node['id'] in seen:continue
            seen.add(node['id'])
            for ref in node['scan']['refs']:
                if ref['kind']!='Library':continue
                linked=next((n for n in self.data['nodes'] if n['type']=='blend' and self.path(n)==Path(ref['path']).resolve()),None)
                if not linked:raise ValueError('Register external linked files before adding links.')
                pending.append(linked)
        available={(d['kind'],d['name']) for d in source['scan'].get('datablocks',[])}
        collections={c['name']:c for c in source['scan'].get('collection_details',[])}
        existing={(d['kind'],d['name']) for d in target['scan'].get('data_links',[]) if Path(d['source']).resolve()==self.path(source)}
        existing.update(('collections',c['collection']) for c in target['scan'].get('instances',[]) if Path(c['source']).resolve()==self.path(source))
        descendants=[collection for kind,collection in existing if kind=='collections'];visited=set()
        while descendants:
            collection=descendants.pop()
            if collection in visited:continue
            visited.add(collection);detail=collections.get(collection,{})
            existing.add(('collections',collection));existing.update(('objects',obj) for obj in detail.get('members',[]))
            descendants.extend(detail.get('children',[]))
        existing.update(('objects',o['reference']) for o in target['scan'].get('overrides',[]) if Path(o['source']).resolve()==self.path(source))
        existing.update(('objects',o['name']) for o in target['scan'].get('objects',[]) if o.get('source') and Path(o['source']).resolve()==self.path(source))
        fresh=[]
        for item in items:
            key=(item['kind'],item['name'])
            if item['kind']=='collections':
                if item['name'] not in collections or not collections[item['name']]['objects']:raise ValueError('Choose a saved non-empty collection: '+item['name'])
            elif key not in available:raise ValueError('Source item no longer exists; refresh: '+item['name'])
            if key in existing:continue
            fresh.append(item)
        if not fresh:raise ValueError('The selected items are already linked. Choose additional items.')
        overridden={o['reference'] for o in target['scan'].get('overrides',[]) if Path(o['source']).resolve()==self.path(source)}
        if mode!='instance' and any(overridden&set(collections[i['name']].get('members',[])) for i in fresh if i['kind']=='collections'):
            raise ValueError('A selected collection shares objects with an existing override hierarchy. Extend that hierarchy in Blender to avoid creating duplicate objects.')
        if mode=='override':
            names={i['name'] for i in fresh if i['kind']=='collections'};descendants=set()
            def visit(collection,seen=None):
                seen=set() if seen is None else seen
                if collection in seen:return
                seen.add(collection)
                for child in collections.get(collection,{}).get('children',[]):
                    descendants.add(child);visit(child,seen)
            for collection in names:visit(collection)
            members=set()
            for collection in names-descendants:
                objects=set(collections[collection].get('members',[]))
                if members&objects:raise ValueError('Selected collections share objects. Use a common parent collection for one override hierarchy, or choose direct linking. Separate override roots would duplicate objects.')
                members.update(objects)
            selected_objects={i['name'] for i in fresh if i['kind']=='objects'}
            selected_objects.update(obj for i in fresh if i['kind']=='collections' for obj in collections[i['name']].get('members',[]))
            missing=[d['name'] for d in source['scan'].get('datablocks',[]) if d['kind']=='objects' and d.get('object_type')=='MESH' and d['name'] in selected_objects and d.get('material_slot_count',0)==0]
            if missing:
                if not prepare_source:raise ValueError('Source mesh objects need material slots for persistent assignments. Confirm the source is saved and closed, or prepare materials on its node first.')
                self.ensure_closed(source,closed)
                self.snapshot(source_id,'Before preparing material slots for linked objects')
                self.transaction(source,{'action':'prepare_materials','objects':missing,'strict':False})
                self.inspect(source)
        # Parents include nested collections and objects; record the actual submitted selection for review.
        self.snapshot(target_id,'Before batch link: '+str(len(fresh))+' items from '+source['name'])
        self.transaction(target,{'action':'link_batch','source':str(self.path(source)),'source_hash':digest(self.path(source)),
                                'items':fresh,'mode':mode,'scene':scene,'camera':camera})
        target['last_link_batch']={'source_id':source_id,'items':fresh,'mode':mode,'created':stamp()}
        self.inspect(target);self.save();return self.state()
    def adopt(self,node_id,source,closed):
        node=self.node(node_id);self.ensure_closed(node,closed)
        source=Path(source).resolve()
        if source.suffix.lower()!='.blend' or not source.is_file():raise ValueError('Choose an existing .blend file.')
        if source.is_relative_to(self.root/META):raise ValueError('Use snapshot Restore for history files.')
        target=self.path(node)
        if source==target:return self.refresh(node_id)
        if target.exists():self.snapshot(node_id,'Before adopting a located file')
        target.parent.mkdir(parents=True,exist_ok=True)
        self.transaction(node,{'action':'create','template':str(source)},new=not target.exists())
        self.inspect(node);self.save();return self.state()
    def restore(self,node_id,snapshot_id,closed):
        node=self.node(node_id);item=next(s for s in node['snapshots'] if s['id']==snapshot_id)
        origin=item.get('origin_path',node['path'])
        if origin==node['path']:
            super().restore(node_id,snapshot_id,closed)
            self.repair_history_links(node)
            self.inspect(node);self.save();return self.state()
        self.ensure_closed(node,closed)
        backup=(self.root/item['path']).resolve()
        if not backup.is_relative_to(self.root/META/'history') or digest(backup)!=item['hash']:raise ValueError('Snapshot integrity check failed.')
        parent=(self.root/origin).resolve().parent
        if not parent.is_relative_to(self.root):raise ValueError('Invalid snapshot origin.')
        parent.mkdir(parents=True,exist_ok=True)
        stage=parent/('.pipeline-history-'+uid()+'.blend')
        try:
            shutil.copy2(backup,stage);self.snapshot(node_id,'Before restoring moved-file snapshot')
            self.transaction(node,{'action':'create','template':str(stage)})
        finally:stage.unlink(missing_ok=True)
        self.repair_history_links(node)
        self.inspect(node);self.save();return self.state()
    def repair_history_links(self,node):
        aliases=self.data.get('path_aliases',{})
        if aliases:self.transaction(node,{'action':'repair_paths','reload':True,'aliases':{str(self.root/old):str(self.root/new) for old,new in aliases.items()}})
    def inspect_snapshot(self,node_id,snapshot_id):
        node=self.node(node_id);item=next(s for s in node['snapshots'] if s['id']==snapshot_id)
        origin=item.get('origin_path',node['path'])
        self.require_desktop()
        source=(self.root/item['path']).resolve()
        if not source.is_relative_to(self.root/META/'history') or digest(source)!=item['hash']:raise ValueError('Snapshot integrity check failed.')
        parent=(self.root/origin).resolve().parent
        if not parent.is_relative_to(self.root):raise ValueError('Invalid snapshot origin.')
        parent.mkdir(parents=True,exist_ok=True);target=parent/('.inspection-'+uid()+'.blend')
        shutil.copy2(source,target)
        try:
            self.repair_history_links(dict(node,path=target.relative_to(self.root).as_posix()))
            self.start_blender(target)
        except Exception:target.unlink(missing_ok=True);raise
        return self.state()
    def refresh_dependencies(self,node_id,closed):
        node=self.node(node_id);self.ensure_closed(node,closed)
        self.snapshot(node_id,'Before refreshing linked assets')
        self.transaction(node,{'action':'reload_libraries'})
        node.pop('dependency_hashes',None)
        self.inspect(node);self.save();return self.state()
    def preflight(self):
        self.refresh();issues=[]
        for node in self.data['nodes']:
            if node['type']!='blend':continue
            scan=node.get('scan',{})
            if scan.get('error'):issues.append(node['path']+': '+scan['error'])
            for ref in scan.get('refs',[]):
                if not ref['exists'] or ref['pattern'] or not ref['inside'] or not ref['relative'] or not Path(ref['path']).is_file():
                    issues.append(node['path']+': '+ref['path']+' (missing, absolute, outside project, sequence or directory reference)')
        return sorted(set(issues))
    def backup(self,destination,allow_incomplete=False,include_renders=True):
        if self.render_busy():raise ValueError('Finish or cancel the render queue before backing up.')
        destination=Path(destination).resolve()
        if destination.exists() or destination.suffix.lower()!='.zip':raise ValueError('Choose a new .zip destination.')
        issues=self.preflight()
        if issues and not allow_incomplete:raise ValueError('Portable backup preflight failed:\n'+'\n'.join(issues)+'\nChoose incomplete archive only if you accept these unresolved references.')
        excluded=[]
        for run in self.data.get('renders',[]):
            if run['status']=='Rendering':raise ValueError('Finish or cancel renders before backing up.')
            if not include_renders:excluded.append((self.root/run['output']).resolve())
        temp=destination.with_name('.pipeline-backup-'+uid()+'.zip');hashes={}
        try:
            with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as archive:
                for path in self.root.rglob('*'):
                    if not path.is_file() or path.resolve() in {temp,destination}:continue
                    relative=path.relative_to(self.root).as_posix()
                    if path.is_symlink():issues.append('Skipped symbolic link: '+relative);continue
                    if any(path.resolve().is_relative_to(e) for e in excluded):continue
                    if '.pipeline-operation-' in relative or path.name.startswith(('.inspection-','.pipeline-history-')):continue
                    before=digest(path);archive.write(path,relative)
                    if digest(path)!=before:raise ValueError('A file changed while backing up: '+relative)
                    hashes[relative]=before
                archive.writestr('_pipeline_backup.json',json.dumps({'created':stamp(),'portable':not issues,'warnings':issues,'hashes':hashes,'render_outputs_included':include_renders},indent=2))
            os.replace(temp,destination)
        finally:temp.unlink(missing_ok=True)
        result=self.state();result['notice']='Backup created: '+str(destination)+(f' · {len(issues)} warnings' if issues else ' · relative dependencies verified');return result
    def render_config(self,node_id,folder_id,scene,camera='',start=None,end=None,percentage=None,prefix=None,auto_prefix=False,width=None,height=None,samples=None,engine=None,format=None,denoise=None,advanced=None,step=None):
        node=self.node(node_id)
        if node.get('external'):raise ValueError('Collect the external library before configuring renders.')
        if node['type']!='blend' or self.node(folder_id)['type']!='folder':raise ValueError('Choose a Blend File and output folder.')
        auto_prefix=bool(auto_prefix or prefix is None)
        config={'folder_id':folder_id,'scene':scene,'camera':camera,'start':start,'end':end,'percentage':percentage,'prefix':name(dated_prefix(scene) if auto_prefix else prefix),'auto_prefix':auto_prefix}
        config.update({k:v for k,v in dict(width=width,height=height,samples=samples,engine=engine,format=format,denoise=denoise,step=step).items() if v is not None})
        if advanced:config['advanced']=self.checked_overrides({'advanced':advanced})['advanced']
        checked=self.effective_render(node,config)
        # Keep inheritance as null; saved scene settings are read again when the job starts.
        for key,value in checked.items():
            if key in config and config[key] is not None and key in {'start','end','percentage','width','height','samples','engine','format','denoise'}:config[key]=value
        node['render_config']=config
        self.save();return self.state()
    def render_start(self,node_id,settings=None,overrides=None,batch_id=None,label='',expected_inputs=None,allow_image_warnings=False,expected_image_warnings=None,expected_images=None):
        if getattr(self,'_render_shutdown',False):raise ValueError('The local application is closing.')
        if type(allow_image_warnings) is not bool:raise ValueError('Image warning consent must be enabled or disabled.')
        node=self.node(node_id);base_config=copy.deepcopy(settings if settings is not None else node.get('render_config'));config=copy.deepcopy(base_config)
        if self.companion and any(s['dirty'] for s in self.companion.opened(self.path(node))):raise ValueError('Save the unsaved Blender session before rendering.')
        if any(r['status']=='Rendering' for r in self.data.get('renders',[])):raise ValueError('Another render is active. Add this file to the sequential queue instead.')
        if not config:raise ValueError('Configure an output folder, scene, camera and frames first.')
        if config.get('auto_prefix'):config['prefix']=dated_prefix(config['scene'] + ('_' + config['view_layer'] if config.get('view_layer') else '_All_layers' if config.get('operation_id') else ''))
        if any(r['node_id']==node_id and r['status']=='Rendering' for r in self.data.get('renders',[])):raise ValueError('This file is already rendering.')
        self.refresh_render_sources()
        config=self.effective_render(node,config,overrides)
        if config.get('auto_prefix'):config['prefix']=dated_prefix(config['scene'] + ('_' + config['view_layer'] if config.get('view_layer') else '_All_layers' if config.get('operation_id') else ''))
        image_warnings=[];image_inputs=[];image_notices=[]
        current=self.capture_render_inputs(node,allow_image_warnings=allow_image_warnings,warnings=image_warnings,images=image_inputs,notices=image_notices)
        if expected_image_warnings is not None and warning_keys(image_warnings)!=warning_keys(expected_image_warnings):
            raise ValueError('Image dependency warnings changed after submission. Queue a new render to review them.')
        if expected_inputs is not None and current!=expected_inputs:raise ValueError('Queued render inputs changed. Queue a new render to use the new saved state.')
        if expected_images is not None and image_identity(image_inputs)!=image_identity(expected_images):raise ValueError('Queued images changed. Queue a new render to use the new saved state.')
        files=[self.root/relative for relative in current]
        output_folder=self.path(self.node(config['folder_id']))
        if config.get('output_subfolder'):
            relative=Path(config['output_subfolder'])
            if relative.is_absolute() or '..' in relative.parts or not relative.parts:raise ValueError('Invalid setup output directory.')
            for part in relative.parts:name(part)
            nested=(output_folder/relative).resolve()
            if not nested.is_relative_to(output_folder):raise ValueError('Invalid scene output directory.')
            output_folder=nested
        stem=self.path(node).stem
        versions = [r['number'] for r in self.data.get('renders', [])
                    if ((r.get('operation_id'), r.get('target_id')) == (config['operation_id'], config['target_id'])
                        if config.get('operation_id') else r['node_id'] == node_id)]
        number = 1 + max([0, *versions])
        while (output_folder/f'{stem}_r{number:03}').exists():number+=1
        output=output_folder/f'{stem}_r{number:03}';output.mkdir(parents=True)
        run_id=uid();inputs=self.root/META/'render-inputs'/run_id;inputs.mkdir(parents=True)
        hashes={};signatures={}
        log=output/'render.log';job=output/'render-job.json'
        atomic_json(job,dict(config,input=str(inputs/node['path']),input_root=str(inputs),project_root=str(self.root),image_inputs=image_inputs,image_warnings=image_warnings+image_notices,output=str(output),run_id=run_id))
        run={'id':run_id,'project_id':self.data['id'],'file_ref':self.resolver.reference(node),'node_id':node_id,'number':number,'created':stamp(),'status':'Preparing','progress':0,
             'config':copy.deepcopy(config),'base_config':base_config,'operation_id':config.get('operation_id'),'target_id':config.get('target_id'),'overrides':copy.deepcopy(overrides or {}),'batch_id':batch_id,'label':str(label)[:120],'name':node['name'],'output':output.relative_to(self.root).as_posix(),'inputs':inputs.relative_to(self.root).as_posix(),
             'input_hashes':{},'image_inputs':copy.deepcopy(image_inputs),'image_notices':copy.deepcopy(image_notices),'dependency_warnings':copy.deepcopy(image_warnings),'log':log.relative_to(self.root).as_posix(),'error':'','detail':'','frame':config['start']-1,'phase':'Freezing saved inputs','finished':''}
        if config.get('setup_label'):run['name']=node['name']+' · '+config['setup_label']
        self.data.setdefault('renders',[]).append(run);self.save()
        preparation_started=time.monotonic()
        try:
            reusable=next((r for r in reversed(self.data['renders'][:-1]) if batch_id and r.get('batch_id')==batch_id
                           and r.get('input_hashes')==current and r.get('status')=='Complete'),None)
            for path in files:
                relative=path.relative_to(self.root);target=inputs/relative;target.parent.mkdir(parents=True,exist_ok=True)
                signatures[relative.as_posix()]=file_signature(path)
                before=digest(path)
                frozen=(self.root/reusable['inputs']/relative).resolve() if reusable else None
                # Link only immutable snapshots owned by this batch, never working
                # files. Each version owns its path and can be deleted independently.
                if frozen and frozen.is_relative_to((self.root/META/'render-inputs').resolve()) and frozen.is_file() and digest(frozen)==before:
                    try:os.link(frozen,target)
                    except OSError:shutil.copy2(path,target)
                else:shutil.copy2(path,target)
                if expected_inputs is not None and before!=expected_inputs.get(relative.as_posix()):raise ValueError('Queued input changed during preparation: '+str(path))
                if digest(path)!=before or digest(target)!=before:raise ValueError('Input changed while freezing: '+str(path))
                hashes[relative.as_posix()]=before
            freeze_images(self,image_inputs,inputs)
            manifest={'config':config,'inputs':hashes,'image_inputs':image_inputs,'image_notices':image_notices,'dependency_warnings':image_warnings,'blender':node['scan'].get('version'),'created':stamp()}
            atomic_json(inputs/'manifest.json',manifest)
            if getattr(self,'_render_shutdown',False):raise ValueError('The local application closed during render preparation.')
            run.update(status='Rendering',phase='Starting Blender',started=stamp(),preparation_seconds=round(time.monotonic()-preparation_started,3),input_hashes=copy.deepcopy(hashes),input_signatures=signatures);self.save()
            command=[self.blender,'--background','--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(BLENDER_SCRIPTS_DIR/'render_job.py'),'--',str(job)]
            if not hasattr(self,'_render_environment'):self._render_environment=render_environment(self.settings_directory)
            if batch_id:
                worker=getattr(self,'_render_worker',None)
                if not worker or worker.batch_id!=batch_id or not worker.usable:
                    if worker:worker.close()
                    worker=RenderWorker(self.blender,BLENDER_SCRIPTS_DIR/'render_worker.py',batch_id,self._render_environment)
                    self._render_worker=worker
                process=worker.submit(run_id,job,log)
                run['worker_pid']=process.pid
            else:
                with log.open('wb') as stream:process=start_background_process(command,stdout=stream,stderr=subprocess.STDOUT,env=self._render_environment,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                run['worker_pid']=process.pid
            self.render_processes[run_id]=process
            threading.Thread(target=self.monitor_render,args=(run,process,log),daemon=True).start()
        except Exception as exc:
            run.update(status='Failed',error=str(exc),finished=stamp(),input_hashes=copy.deepcopy(hashes))
            try:self.render_sizes(run)
            except OSError:pass
            self.save()
            raise
        return self.state()
    def monitor_render(self,run,process,log):
        while process.poll() is None:
            try:
                lines=log.read_text(encoding='utf-8',errors='replace').splitlines()
                read_markers(lines,run)
                run['detail']='\n'.join(lines[-4:])[-700:]
            except (OSError,ValueError):pass
            threading.Event().wait(.5)
        cleanup_background_process(process)
        with self.lock:
            if not self.data or run.get('project_id')!=self.data['id']:return
            if run['id'] in self.render_cancelled:run['status']='Cancelled'
            elif process.returncode:
                try:detail=log.read_text(encoding='utf-8',errors='replace')[-2500:]
                except OSError:detail='The render log could not be read.'
                run.update(status='Failed',error=f'Blender exited with code {process.returncode}.\n'+detail)
            else:run.update(status='Complete',progress=100)
            try:
                lines=log.read_text(encoding='utf-8',errors='replace').splitlines()
                run['detail']='\n'.join(lines[-6:])[-1200:]
                read_markers(lines,run)
            except (OSError,ValueError,StopIteration):pass
            run['finished']=stamp()
            try:self.render_sizes(run)
            except OSError:pass
            if run['status']=='Complete' and not run.get('file_count'):
                run.update(status='Failed',progress=0,error='Blender exited without saving render output. Check the render log before retrying.')
            run['phase']=run['status']
            self.render_processes.pop(run['id'],None)
            self._folder_cache={};self.save()
    def render_cancel(self,run_id):
        process=self.render_processes.get(run_id)
        if not process or process.poll() is not None:raise ValueError('No active render process for this run.')
        self.render_cancelled.add(run_id);process.terminate();return self.state()
    def render_open(self,run_id):
        self.require_desktop();run=next(r for r in self.data['renders'] if r['id']==run_id)
        if run['status']=='Deleted':raise ValueError('This render version was deleted.')
        path=(self.root/run['output']).resolve()
        if not path.is_relative_to(self.root):raise ValueError('Invalid render output path.')
        os.startfile(str(path),'open');return self.state()

