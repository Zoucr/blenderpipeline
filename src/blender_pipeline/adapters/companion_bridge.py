"""Authenticated loopback companion sessions; no Blender imports in the server."""
import copy,os,time,threading
from pathlib import Path
from blender_pipeline.project.model import META,uid,name,atomic_json

class Bridge:
    def __init__(self,model):
        self.model=model;self.lock=threading.RLock();self.sessions={};model.companion=self
    def publish(self,port,token,path=None):
        path=Path(path or self.model.settings_directory/'companion-connection.json')
        atomic_json(path,{'url':f'http://127.0.0.1:{port}/','token':token,'version':1,'pid':os.getpid()})
        return path
    def live(self):
        with self.lock:return copy.deepcopy([s for s in self.sessions.values() if time.monotonic()-s['_seen']<15])
    def opened(self,path):
        key=os.path.normcase(str(Path(path).resolve()))
        return [s for s in self.live() if s.get('file') and os.path.normcase(str(Path(s['file']).resolve()))==key]
    def catalog(self):
        model=self.model
        snapshot=self.tasks.state() if getattr(self,'tasks',None) else model.state()
        data=snapshot.get('project') or {}
        recent_queue={q['id'] for q in data.get('render_queue',[])[-50:]}
        operation_outputs={}
        for node in data.get('nodes',[]):
            targets=[t for t in snapshot.get('render_targets',[]) if t.get('source_id')==node['id']]
            target=next((t for t in targets if t['render_config']['scene']==node.get('scan',{}).get('active_scene')), targets[0] if targets else None)
            if target:operation_outputs[node['id']]=target['render_config']
        return {'root':snapshot.get('root',''), 'project_id':data.get('id',''),
            'revision':data.get('revision'),
            'files':[{'id':n['id'],'name':n['name'],'path':str(model.path(n)),
                'collections':n.get('scan',{}).get('collection_details',[]),'datablocks':n.get('scan',{}).get('datablocks',[]),
                'render_config':copy.deepcopy(n.get('render_config') or operation_outputs.get(n['id'],{}))} for n in data.get('nodes',[]) if n['type']=='blend' and not n.get('hidden') and not snapshot.get('files',{}).get(n['id'],{}).get('missing')],
            'folders':[{'id':n['id'],'name':n['name'],'path':n['path']} for n in data.get('nodes',[]) if n['type']=='folder' and not n.get('hidden')],
            'render_queue':[{'id':q['id'],'node_id':q['node_id'],'status':q['status'],'scene':q['settings']['scene'],
                'start':q.get('effective_settings',q['settings']).get('start'),'end':q.get('effective_settings',q['settings']).get('end'),
                'run_id':q.get('run_id',''),'error':q.get('error',''),
                'progress':next((r.get('progress',0) for r in data.get('renders',[]) if r['id']==q.get('run_id')),0)} for q in data.get('render_queue',[]) if q['id'] in recent_queue or q['status'] in {'Queued','Preparing','Rendering'}],
            'jobs':[{'id':j['id'],'status':j['status'],'error':j.get('error',''),'result':j.get('companion_result')} for j in getattr(self,'tasks',None).jobs.values()] if getattr(self,'tasks',None) else []}
    def heartbeat(self,session_id,file='',dirty=False,pid=0,version='',collections=None,libraries=None,overrides=0):
        if not session_id or len(session_id)>100:raise ValueError('Invalid session')
        with self.lock:
            self.sessions[session_id]={'id':session_id,'file':str(file)[:4096],'dirty':bool(dirty),'pid':int(pid),'version':str(version)[:50],
                'collections':(collections or [])[:300],'libraries':(libraries or [])[:300],'overrides':int(overrides),'_seen':time.monotonic()}
            for key in list(self.sessions):
                if time.monotonic()-self.sessions[key]['_seen']>60:self.sessions.pop(key)
        return self.catalog()
    def goodbye(self,session_id):
        with self.lock:self.sessions.pop(session_id,None)
        return {'ok':True}
    def prepare(self,path,create=False,preset='empty'):
        root=Path(path).resolve()
        if self.tasks.active():raise ValueError('Wait for queued operations before choosing a project')
        with self.model.lock:
            if self.tasks.active() or self.model.render_busy():raise ValueError('Finish queued operations and renders before changing projects')
            if create:self.model.create(root.parent,root.name,preset=preset)
            else:self.model.load(root)
        return self.catalog()
