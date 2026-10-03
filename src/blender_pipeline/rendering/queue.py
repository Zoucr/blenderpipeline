"""Sequential render queue with settings and input identity captured at submission."""
import copy,threading,time
from pathlib import Path
from blender_pipeline.project.model import uid,stamp,digest
class RenderQueue:
    def capture_render_inputs(self,node):
        lookup={}
        for entry in self.data['nodes']:
            if entry['type']=='blend':
                try:lookup[str(self.path(entry))]=entry
                except ValueError:pass
        pending=[self.path(node)];files={};seen=set()
        while pending:
            path=pending.pop().resolve()
            if str(path) in seen:continue
            seen.add(str(path));source=lookup.get(str(path))
            if not source or source.get('scan',{}).get('error'):raise ValueError('Refresh and resolve this render input first: '+str(path))
            if self.companion and any(s['dirty'] for s in self.companion.opened(path)):raise ValueError('Save this render input first: '+str(path))
            if not path.is_relative_to(self.root):raise ValueError('Collect external libraries before rendering: '+str(path))
            stat=path.stat();signature=source.get('scan',{}).get('signature')
            if signature and signature!=[stat.st_mtime_ns,stat.st_size]:raise ValueError('Render input changed after scanning. Save and queue again: '+str(path))
            files[path.relative_to(self.root).as_posix()]=digest(path)
            for ref in source['scan'].get('refs',[]):
                dependency=Path(ref['path']).resolve()
                if ref.get('pattern') or not ref.get('exists') or not ref.get('relative') or not dependency.is_file() or not dependency.is_relative_to(self.root):
                    raise ValueError('Resolve dependency before rendering: '+str(dependency))
                files[dependency.relative_to(self.root).as_posix()]=digest(dependency)
                if ref['kind']=='Library':pending.append(dependency)
        return files
    def render_busy(self):
        return any(r['status'] in {'Preparing','Rendering'} for r in (self.data or {}).get('renders',[])) or any(r['status'] in {'Queued','Preparing','Rendering'} for r in (self.data or {}).get('render_queue',[]))
    def queue_render(self,node_id,overrides=None,label='',settings=None):
        return self.queue_batch(node_ids=[node_id],overrides=overrides,label=label,settings=settings)
    def queue_batch(self,folder_id=None,node_ids=None,overrides=None,label='',settings=None):
        with self.lock:
            self.refresh()
            if node_ids is None:nodes=self.render_targets(folder_id)
            else:
                allowed={n['id'] for n in self.render_targets(folder_id)}
                if any(i not in allowed for i in node_ids):raise ValueError('Choose files with explicit output connections in this scope.')
                nodes=[self.node(i) for i in dict.fromkeys(node_ids)]
            if not nodes:raise ValueError('No output connections in this folder scope.')
            if settings is not None and len(nodes)!=1:raise ValueError('Retry settings require one render target.')
            checked=self.checked_overrides(overrides)
            queue=self.data.setdefault('render_queue',[])
            # Validate the whole selection before adding any jobs. Scene settings are frozen here.
            captured={}
            for node in nodes:
                effective=self.effective_render(node,settings if settings is not None else node.get('render_config'),checked)
                captured[node['id']]={'effective_settings':effective,'expected_inputs':self.capture_render_inputs(node)}
                if any(q['node_id']==node['id'] and q['status'] in {'Queued','Preparing','Rendering'} for q in queue):raise ValueError(node['name']+' is already queued.')
            batch_id=uid()
            for node in nodes:
                queue.append({'id':uid(),'project_id':self.data['id'],'project_revision':self.data['revision'],'file_ref':self.resolver.reference(node),'batch_id':batch_id,'label':str(label)[:120],'node_id':node['id'],'name':node['name'],'settings':copy.deepcopy(settings if settings is not None else node['render_config']),'overrides':copy.deepcopy(checked),'status':'Queued','created':stamp(),'run_id':'','error':'','finished':'',**captured[node['id']]})
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
                if not self.data or self.data['id']!=project_id:self.queue_worker=None;return
                item=next((q for q in self.data.get('render_queue',[]) if q['status']=='Queued'),None)
                if not item:self.queue_worker=None;return
                active=any(r['status']=='Rendering' for r in self.data.get('renders',[]))
            if active:time.sleep(.5);continue
            try:
                with self.lock:
                    if item['status']!='Queued':continue
                    if item.get('project_id')!=project_id:raise ValueError('Render job belongs to another project.')
                    for relative,expected in item['expected_inputs'].items():
                        path=(self.root/relative).resolve()
                        if not path.is_relative_to(self.root) or not path.is_file() or digest(path)!=expected:raise ValueError('Queued render input changed: '+relative+'. Queue a new render to use the new saved state.')
                    item['status']='Preparing';self.save();self.render_start(item['node_id'],settings=item.get('effective_settings'),overrides=item.get('overrides'),batch_id=item.get('batch_id'),label=item.get('label',''),expected_inputs=item['expected_inputs']);run=self.data['renders'][-1]
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
                if not ref['exists'] or ref['pattern'] or not ref['relative'] or not ref['inside']:errors.append(prefix+'unsupported / missing dependency '+ref['raw'])
            scenes=[s for s in scan.get('scenes',[]) if not s.get('linked')]
            if not any(s['camera'] and s['camera'] in s['cameras'] for s in scenes):warnings.append(prefix+'no active scene camera')
            if not node.get('render_config'):warnings.append(prefix+'render output not configured')
            if scan.get('overrides'):warnings.append(prefix+str(len(scan['overrides']))+' override objects; review after structural source edits')
            if self.companion and any(s['dirty'] for s in self.companion.opened(self.path(node))):warnings.append(prefix+'unsaved Blender edits are not captured')
        result=self.state();result['companion_result']={'errors':errors,'warnings':warnings,'ok':not errors};return result
