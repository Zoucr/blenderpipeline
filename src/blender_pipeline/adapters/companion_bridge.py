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
        return {'root':snapshot.get('root',''), 'project_id':data.get('id',''),
            'revision':data.get('revision'),
            'files':[{'id':n['id'],'name':n['name'],'path':str(model.path(n)),
                'collections':n.get('scan',{}).get('collection_details',[]),'datablocks':n.get('scan',{}).get('datablocks',[])} for n in data.get('nodes',[]) if n['type']=='blend' and not n.get('hidden') and not snapshot.get('files',{}).get(n['id'],{}).get('missing')],
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
