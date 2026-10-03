"""Serial project mutations with nonblocking browser polling."""
import copy, os, threading, weakref
from concurrent.futures import ThreadPoolExecutor
from blender_pipeline.project.model import uid,stamp
_owners=weakref.WeakValueDictionary()

def owner_alive(job):
    pid=job.get('owner_pid')
    if pid==os.getpid():return job.get('owner_id') in _owners
    if not isinstance(pid,int) or pid<=0:return False
    try:os.kill(pid,0);return True
    except OSError:return False

class Tasks:
    def __init__(self,model):
        self.model=model;self.pool=ThreadPoolExecutor(max_workers=1);self.lock=threading.RLock();self.jobs={}
        self.cached=copy.deepcopy(model.state())
        self.journal=None
        self.owner_id=uid();_owners[self.owner_id]=self
    def configure_journal(self,journal):
        self.journal=journal;self.jobs=journal.load()
        for job in self.jobs.values():
            if job['status'] in {'Queued','Running'} and not owner_alive(job):
                job.update(status='Interrupted',error='The application restarted before confirming this operation. Check its files before submitting a new request.',finished=stamp())
                journal.update(job)
    def record(self,job):
        if self.journal:self.journal.update(job)
    def active(self):return any(j['status'] in {'Queued','Running'} for j in self.jobs.values())
    def state(self):
        with self.lock:
            if self.journal:
                for key,job in self.journal.load().items():
                    if job.get('owner_id')!=self.owner_id:self.jobs[key]=job
            if not self.active():self.cached=copy.deepcopy(self.model.state())
            result=copy.deepcopy(self.cached)
            # Render progress is maintained independently of queued file operations.
            if result.get('project') and self.model.data and result['project']['id']==self.model.data['id']:
                result['project']['renders']=copy.deepcopy(self.model.data.get('renders',[]))
                result['project']['render_queue']=copy.deepcopy(self.model.data.get('render_queue',[]))
            jobs=[j for j in self.jobs.values() if j.get('kind')!='direct']
            shown={j['id']:j for j in jobs[-40:]}
            shown.update({j['id']:j for j in jobs if j['status'] in {'Queued','Running'}})
            result['jobs']=copy.deepcopy(list(shown.values()));return result
    def submit(self,action,args,method,context=None,fingerprint=None):
        with self.lock:
            context=context or {}
            job={'id':uid(),'action':action,'args':copy.deepcopy(args),'node_id':args.get('node_id') or args.get('target_id'),'status':'Queued','created':stamp(),'error':'',**context,'fingerprint':fingerprint,'owner_pid':os.getpid(),'owner_id':self.owner_id}
            # Reserve first so retries can retrieve an existing job even if busy.
            if self.journal:
                existing,created=self.journal.reserve(job)
                if not created:
                    self.jobs[existing['id']]=existing
                    return {'job':existing['id'],'duplicate':True,'status':existing['status']}
            if action in {'load','create'} and (self.active() or self.model.render_busy()):
                job.update(status='Failed',error='Finish queued operations and renders before switching projects.',finished=stamp());self.record(job)
                self.jobs[job['id']]=job
                return {'job':job['id']}
            self.jobs[job['id']]=job
            self.pool.submit(self.execute,job,args,method)
            return {'job':job['id']}
    def execute(self,job,args,method):
        with self.lock:job['status']='Running';self.record(job)
        try:
            with self.model.lock:
                result=method(**args)
                if job['node_id'] and self.model.data and job.get('project_id')==self.model.data['id']:
                    node=next((n for n in self.model.data['nodes'] if n['id']==job['node_id']),None)
                    if node and node.pop('last_error',None) is not None:self.model.save()
            with self.lock:
                self.cached=copy.deepcopy(result);job.update(status='Complete',finished=stamp())
                if result.get('companion_result'):job['companion_result']=result['companion_result']
                self.record(job)
        except Exception as exc:
            # A rejected precondition must never write a node error to another project.
            if job['node_id'] and self.model.data and job.get('project_id')==self.model.data['id'] and getattr(exc,'code',None) not in {'revision_conflict','project_context_changed'}:
                with self.model.lock:
                    node=next((n for n in self.model.data['nodes'] if n['id']==job['node_id']),None)
                    if node:
                        node['last_error']={'action':job['action'],'args':copy.deepcopy(args),'message':str(exc)}
                        try:self.model.save()
                        except Exception as save_error:node['last_error']['message']+='; could not persist error: '+str(save_error)
            with self.lock:
                job.update(status='Failed',error=str(exc),finished=stamp(),error_code=getattr(exc,'code','operation_failed'))
                self.record(job)
                self.cached=copy.deepcopy(self.model.state())
