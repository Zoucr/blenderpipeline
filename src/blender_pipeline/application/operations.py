"""Explicit local project contexts and persisted request identity. No HTTP dependency."""
import copy
import hashlib
import json
from pathlib import Path
from blender_pipeline.storage.projects import RevisionConflict, atomic_json
from blender_pipeline.storage.locks import exclusive_file


class ProjectContextError(ValueError):
    status=409
    code='project_context_changed'


class OperationJournal:
    def __init__(self, directory):
        self.path=Path(directory)/'operation-jobs.json'
        self.lock_path=self.path.with_suffix('.lock')

    def _read(self):
        return json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {}

    def load(self):
        with exclusive_file(self.lock_path):
            return self._read()

    def reserve(self, job):
        with exclusive_file(self.lock_path):
            data=self._read()
            key=job.get('request_id')
            if key:
                previous=next((j for j in data.values() if j.get('request_id')==key and j.get('project_id')==job.get('project_id')),None)
                if previous:
                    if previous['fingerprint']!=job['fingerprint']:
                        raise ValueError('This request ID was already used with different arguments. Submit a new request.')
                    return previous,False
            data[job['id']]=copy.deepcopy(job)
            atomic_json(self.path,data)
            return job,True

    def update(self, job):
        with exclusive_file(self.lock_path):
            data=self._read();data[job['id']]=copy.deepcopy(job);atomic_json(self.path,data)


class OperationContracts:
    def __init__(self, model):
        self.model=model

    def context(self, args, action):
        parameters=copy.deepcopy(args)
        explicit='project_id' in parameters
        current=(self.model.data or {}).get('id')
        project_id=parameters.pop('project_id',current)
        revision=parameters.pop('expected_revision',None)
        request_id=parameters.pop('request_id',None)
        client_id=parameters.pop('client_id','local')
        if project_id is not None and (not isinstance(project_id,str) or not project_id or len(project_id)>128):raise ValueError('Invalid project ID.')
        if request_id is not None and (not isinstance(request_id,str) or not 1<=len(request_id)<=128):raise ValueError('Invalid request ID.')
        if revision is not None and (type(revision) is not int or revision<0):raise ValueError('Invalid expected revision.')
        if action not in {'create','load'}:
            if not explicit:raise ValueError('Project ID is required. Refresh the interface and submit again.')
            if not current or project_id!=current:raise ProjectContextError('Project changed. Choose the intended project again; nothing was applied.')
            if action not in {'launch','render_open','read_render_settings','output_files','output_image','project_view','storage_locations'} and revision is None:
                raise ValueError('Expected project revision is required.')
        context={'project_id':project_id,'expected_revision':revision,'request_id':request_id,'client_id':client_id}
        # Enrollment validates the project again within its domain operation.
        if action=='register_working':parameters['project_id']=project_id
        return parameters,context

    def validate(self, context):
        current=(self.model.data or {}).get('id')
        if current!=context['project_id']:
            raise ProjectContextError('Project changed before this operation ran. Choose its original project and submit again.')
        if self.model.data:
            actual=self.model.data.get('revision')
            expected=context['expected_revision']
            if expected is not None and actual!=expected:raise RevisionConflict(expected,actual)
            # Check disk BEFORE any file-system or Blender side effect.
            disk=self.model.repository.load(self.model.root)
            if disk['id']!=current:raise ProjectContextError('Project identity changed on disk.')
            if disk['revision']!=actual:raise RevisionConflict(actual,disk['revision'])

    def bind(self, action, method, context):
        def execute(**args):
            # One operation owner across local processes, before side effects.
            root=self.model.root
            lock_path=root/'.pipeline'/'operations.lock' if root else self.model.registry.parent/'operations.lock'
            with exclusive_file(lock_path):
                try:
                    self.validate(context)
                    return method(**args)
                except Exception:
                    if self.model.data and self.model.data['id']==context['project_id']:
                        self.model.reload_metadata()
                    raise
        return execute

    @staticmethod
    def fingerprint(action, args, context):
        # Revision is a precondition, not the identity of the requested work.
        content={'action':action,'args':args,'project_id':context['project_id']}
        return hashlib.sha256(json.dumps(content,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
