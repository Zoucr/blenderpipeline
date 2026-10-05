"""Sequential render queue with settings and input identity captured at submission."""
import copy,threading,time
from pathlib import Path
from blender_pipeline.project.model import uid,stamp,digest
from blender_pipeline.rendering.inputs import render_inputs, RenderImageWarnings, unique_warnings, warning_keys
from blender_pipeline.rendering.images import locate_image, inspect_image
class RenderQueue:
    def capture_render_inputs(self,node,allow_image_warnings=None,warnings=None,images=None,notices=None):
        files,issues=render_inputs(self,node,collect_images=allow_image_warnings is not None,images=images,notices=notices)
        if issues and not allow_image_warnings:
            if allow_image_warnings is False:raise RenderImageWarnings(issues)
            raise ValueError('Resolve dependency before rendering: '+issues[0]['path'])
        if warnings is not None:warnings.extend(issues)
        return files
    def locate_render_image(self,source_id,path,replacement):
        return locate_image(self,source_id,path,replacement)
    def refresh_render_sources(self):
        # Rendering reuses unchanged scan metadata. A manual Refresh still rescans.
        changed=False
        for node in self.data['nodes']:
            if node['type']!='blend':continue
            try:
                info=self.path(node).stat();signature=[info.st_mtime_ns,info.st_size]
            except (OSError,ValueError):signature=None
            if signature is None or node.get('scan',{}).get('error') or node.get('scan',{}).get('signature')!=signature:
                self.inspect(node);changed=True
        if changed:self.save()

    def render_busy(self):
        return any(r['status'] in {'Preparing','Rendering'} for r in (self.data or {}).get('renders',[])) or any(r['status'] in {'Queued','Preparing','Rendering'} for r in (self.data or {}).get('render_queue',[]))
    def queue_render(self,node_id,overrides=None,label='',settings=None,expected_inputs=None,allow_image_warnings=False,accepted_image_warnings=None):
        return self.queue_batch(node_ids=[node_id],overrides=overrides,label=label,settings=settings,expected_inputs=expected_inputs,allow_image_warnings=allow_image_warnings,accepted_image_warnings=accepted_image_warnings)
    def queue_batch(self,folder_id=None,node_ids=None,overrides=None,label='',settings=None,expected_inputs=None,allow_image_warnings=False,accepted_image_warnings=None):
        with self.lock:
            if type(allow_image_warnings) is not bool:raise ValueError('Image warning consent must be enabled or disabled.')
            self.refresh_render_sources()
            if node_ids is None:nodes=self.render_targets(folder_id)
            else:
                allowed={n['id'] for n in self.render_targets(folder_id,include_disabled=True)}
                if settings is not None and len(node_ids)==1:
                    source=self.node(node_ids[0]) if ':' not in node_ids[0] else None
                    if source and source['type']=='blend' and not source.get('external'):allowed.add(source['id'])
                if any(i not in allowed for i in node_ids):raise ValueError('Choose files with explicit output connections in this scope.')
                lookup={n['id']:n for n in self.render_targets(folder_id,include_disabled=True)}
                if settings is not None and len(node_ids)==1 and source:lookup[source['id']]=source
                nodes=[lookup[i] for i in dict.fromkeys(node_ids)]
            if not nodes:raise ValueError('No output connections in this folder scope.')
            if settings is not None and len(nodes)!=1:raise ValueError('Retry settings require one render target.')
            if expected_inputs is not None and len(nodes)!=1:raise ValueError('An input precondition requires one render target.')
            checked=self.checked_overrides(overrides)
            queue=self.data.setdefault('render_queue',[])
            # Validate the whole selection before adding any jobs. Scene settings are frozen here.
            captured={};source_inputs={}
            for node in nodes:
                effective=self.effective_render(node,settings if settings is not None else node.get('render_config'),checked)
                source_id=node.get('source_id',node['id'])
                if source_id not in source_inputs:
                    image_warnings=[];image_inputs=[];image_notices=[]
                    inputs=self.capture_render_inputs(node,allow_image_warnings=True,warnings=image_warnings,images=image_inputs,notices=image_notices)
                    source_inputs[source_id]={'expected_inputs':inputs,'image_inputs':image_inputs,'image_notices':image_notices,'dependency_warnings':image_warnings,'allow_image_warnings':allow_image_warnings}
                captured[node['id']]={'effective_settings':effective,**copy.deepcopy(source_inputs[source_id])}
                if expected_inputs is not None and captured[node['id']]['expected_inputs']!=expected_inputs:raise ValueError('Render inputs changed after submission. Save and submit again.')
                operation_id=effective.get('operation_id');target_id=effective.get('target_id')
                target_key=operation_id+':'+target_id if operation_id and target_id else node['id']
                if any(q.get('target_key',q['node_id'])==target_key and q['status'] in {'Queued','Preparing','Rendering'} for q in queue):raise ValueError(node['name']+' is already queued.')
            warnings=unique_warnings([w for item in captured.values() for w in item['dependency_warnings']])
            if warnings and (not allow_image_warnings or accepted_image_warnings is not None and warning_keys(warnings)!=warning_keys(accepted_image_warnings)):raise RenderImageWarnings(warnings)
            batch_id=uid()
            for node in nodes:
                source_id=node.get('source_id',node['id'])
                config=settings if settings is not None else node['render_config']
                operation_id=node.get('operation_id') or config.get('operation_id')
                target_id=node.get('target_id') or config.get('target_id')
                queue.append({'id':uid(),'project_id':self.data['id'],'project_revision':self.data['revision'],'file_ref':self.resolver.reference(self.node(source_id)),'batch_id':batch_id,'label':str(label)[:120],'node_id':source_id,'target_key':operation_id+':'+target_id if operation_id and target_id else node['id'],'operation_id':operation_id,'target_id':target_id,'name':node['name'],'settings':copy.deepcopy(config),'overrides':copy.deepcopy(checked),'status':'Queued','created':stamp(),'run_id':'','error':'','finished':'',**captured[node['id']]})
            self.save()
            if not getattr(self,'queue_worker',None):
                self.queue_worker=threading.Thread(target=self._queue_loop,args=(self.data['id'],),daemon=True);self.queue_worker.start()
            return self.state()
    def cancel_queue(self,queue_id):
        with self.lock:
            item=next(q for q in self.data.get('render_queue',[]) if q['id']==queue_id)
            if item['status'] not in {'Queued','Preparing','Rendering'}:return self.state()
            if item['run_id']:self.render_cancel(item['run_id'])
            item.update(status='Cancelled',finished=stamp());self.save();return self.state()
    def _queue_loop(self,project_id):
        while True:
            with self.lock:
                if not self.data or self.data['id']!=project_id or getattr(self,'_render_shutdown',False):self.queue_worker=None;return
                item=next((q for q in self.data.get('render_queue',[]) if q['status']=='Queued'),None)
                if not item:
                    worker=getattr(self,'_render_worker',None)
                    if worker:worker.close();self._render_worker=None
                    self.queue_worker=None;return
                active=any(r['status']=='Rendering' for r in self.data.get('renders',[]))
            if active:time.sleep(.5);continue
            try:
                with self.lock:
                    if item['status']!='Queued':continue
                    if item.get('project_id')!=project_id:raise ValueError('Render job belongs to another project.')
                    for relative,expected in item['expected_inputs'].items():
                        path=(self.root/relative).resolve()
                        if not path.is_relative_to(self.root) or not path.is_file() or digest(path)!=expected:raise ValueError('Queued render input changed: '+relative+'. Queue a new render to use the new saved state.')
                    item['status']='Preparing';self.save();self.render_start(item['node_id'],settings=item.get('effective_settings'),overrides=item.get('overrides'),batch_id=item.get('batch_id'),label=item.get('label',''),expected_inputs=item['expected_inputs'],allow_image_warnings=item.get('allow_image_warnings',False),expected_image_warnings=item.get('dependency_warnings',[]),expected_images=item.get('image_inputs',[]));run=self.data['renders'][-1]
                    item.update(status='Rendering',run_id=run['id']);self.save()
                while run['status']=='Rendering':time.sleep(.25)
                with self.lock:item.update(status=run['status'],error=run.get('error',''),finished=stamp());self.save()
            except Exception as exc:
                with self.lock:item.update(status='Failed',error=str(exc),finished=stamp());self.save()
    def preflight_report(self,node_id=None):
        self.refresh(node_id);nodes=[self.node(node_id)] if node_id else self.data['nodes'];errors=[];warnings=[]
        if not node_id and self.data.get('default_template') and self.data['default_template']!='__factory__':
            try:self.template_entry(self.data['default_template'])
            except ValueError as exc:errors.append('Startup template: '+str(exc))
        for node in nodes:
            if node['type']!='blend':continue
            scan=node.get('scan',{});prefix=node['name']+': '
            if scan.get('error'):errors.append(prefix+scan['error'])
            for ref in scan.get('refs',[]):
                if ref['kind']=='Image':
                    issue=inspect_image(self,node,ref)
                    if issue and issue['severity']=='warning':warnings.append(prefix+issue['reason']+' '+ref['raw'])
                    continue
                if not ref['exists'] or ref['pattern'] or not ref['relative'] or not ref['inside']:
                    errors.append(prefix+'unsupported / missing dependency '+ref['raw'])
            scenes=[s for s in scan.get('scenes',[]) if not s.get('linked')]
            if not any(s['camera'] and s['camera'] in s['cameras'] for s in scenes):warnings.append(prefix+'no active scene camera')
            if not node.get('render_config'):warnings.append(prefix+'render output not configured')
            if scan.get('overrides'):warnings.append(prefix+str(len(scan['overrides']))+' override objects; review after structural source edits')
            if self.companion and any(s['dirty'] for s in self.companion.opened(self.path(node))):warnings.append(prefix+'unsaved Blender edits are not captured')
        result=self.state();result['companion_result']={'errors':errors,'warnings':warnings,'ok':not errors};return result
