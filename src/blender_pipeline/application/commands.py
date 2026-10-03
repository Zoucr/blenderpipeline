"""Application commands and rules. HTTP is only one adapter to this interface."""
from dataclasses import dataclass
from pathlib import Path
from blender_pipeline.storage.local_settings import LocalSettings
from blender_pipeline.project.library import ProjectLibrary
from blender_pipeline.adapters.file_browser import browse_directory, choose_system_path
import copy
import threading
import os
from blender_pipeline.project.model import uid, stamp
from blender_pipeline.application.operations import OperationContracts, OperationJournal
from blender_pipeline.storage.file_references import FileResolver


@dataclass(frozen=True)
class Command:
    method: str
    queued: bool = True
    direct: bool = False


COMMANDS = {
    'state': Command('state', queued=False, direct=True),
    'create': Command('create', queued=True, direct=True),
    'load': Command('load', queued=True, direct=True),
    'folder': Command('folder', queued=True, direct=True),
    'blend': Command('create_blend', queued=True, direct=True),
    'import': Command('import_blend', queued=True, direct=True),
    'refresh': Command('refresh', queued=True, direct=True),
    'snapshot': Command('snapshot', queued=True, direct=True),
    'restore': Command('restore', queued=True, direct=True),
    'organize': Command('organize', queued=True, direct=True),
    'label': Command('label', queued=True, direct=True),
    'duplicate': Command('duplicate', queued=True, direct=True),
    'snapshot_note': Command('snapshot_note', queued=True, direct=True),
    'graph_edit': Command('graph_edit', queued=True, direct=True),
    'adopt': Command('adopt', queued=True, direct=True),
    'relocate': Command('relocate', queued=True, direct=True),
    'refresh_dependencies': Command('refresh_dependencies', queued=True, direct=True),
    'backup': Command('backup', queued=True, direct=True),
    'render_config': Command('render_config', queued=True, direct=True),
    'render_start': Command('render_start', queued=True, direct=True),
    'render_open': Command('render_open', queued=True, direct=True),
    'dismiss_error': Command('dismiss_error', queued=True, direct=True),
    'link': Command('link', queued=True, direct=True),
    'launch': Command('launch', queued=True, direct=True),
    'layout': Command('layout', queued=False, direct=True),
    'inspect_snapshot': Command('inspect_snapshot', queued=True, direct=True),
    'group_nodes': Command('group_nodes', queued=True, direct=False),
    'archive_folder': Command('archive_folder', queued=True, direct=False),
    'restore_folder': Command('restore_folder', queued=True, direct=False),
    'archive_blend': Command('archive_blend', queued=True, direct=False),
    'restore_archived': Command('restore_archived', queued=True, direct=False),
    'register_working': Command('register_working', queued=True, direct=False),
    'companion_link_plan': Command('companion_link_plan', queued=True, direct=False),
    'link_data': Command('link_data', queued=True, direct=False),
    'link_batch': Command('link_batch', queued=True, direct=False),
    'prepare_materials': Command('prepare_materials', queued=True, direct=False),
    'save_app_startup': Command('save_app_startup', queued=True, direct=False),
    'queue_render': Command('queue_render', queued=True, direct=False),
    'queue_batch': Command('queue_batch', queued=True, direct=False),
    'batch_settings': Command('batch_settings', queued=True, direct=False),
    'render_delete': Command('render_delete', queued=True, direct=False),
    'preflight_report': Command('preflight_report', queued=True, direct=False),
    'companion_render': Command('companion_render', queued=True, direct=False),
    'save_template': Command('save_template', queued=True, direct=False),
    'template_default': Command('template_default', queued=True, direct=False),
    'external_register': Command('external_register', queued=True, direct=False),
    'localize_external': Command('localize_external', queued=True, direct=False),
}


class Application:
    def __init__(self, model, tasks, bridge, settings_directory):
        self.model, self.tasks, self.bridge = model, tasks, bridge
        self.settings_directory = Path(settings_directory)
        self.local_settings = LocalSettings(self.settings_directory)
        self.project_library = ProjectLibrary(model, tasks)
        self.contracts=OperationContracts(model)
        self.journal=OperationJournal(self.settings_directory)
        if hasattr(model,'resolver'):model.resolver=FileResolver(self.settings_directory)
        if hasattr(tasks,'configure_journal'):tasks.configure_journal(self.journal)

    def client_state(self, result, client_id):
        if not isinstance(result,dict) or not isinstance(result.get('project'),dict):return result
        result=copy.deepcopy(result)
        project=result['project']
        personal=self.local_settings.project_view(project['id'],client_id)
        project['view']=copy.deepcopy(personal.get('view',(self.model.data or {}).get('view',{'x':0,'y':0,'zoom':1})))
        result['view_state']=personal
        return result

    def _direct(self, action, parameters, context, method):
        if not context['request_id']:
            raise ValueError('Request ID is required for project operations.')
        entry={'id':uid(),'action':action,'project_id':context['project_id'],'request_id':context['request_id'],
               'fingerprint':self.contracts.fingerprint(action,parameters,context),'status':'Running','created':stamp(),'error':'','kind':'direct','owner_pid':os.getpid(),'owner_id':getattr(self.tasks,'owner_id',None)}
        previous,created=self.journal.reserve(entry)
        if not created:
            if previous['status']=='Complete':return self.tasks.state()
            raise ValueError(previous.get('error') or 'This request is already running. Check its status before submitting again.')
        try:
            result=method(**parameters)
            entry.update(status='Complete',finished=stamp());self.journal.update(entry)
            return result
        except Exception as exc:
            entry.update(status='Failed',finished=stamp(),error=str(exc));self.journal.update(entry)
            raise

    def commands(self, queued):
        return {name: getattr(self.model, command.method) for name, command in COMMANDS.items()
                if (command.queued if queued else command.direct)}

    def command(self, action, queued):
        command = COMMANDS.get(action) if isinstance(action, str) else None
        if command is None or not (command.queued if queued else command.direct):
            raise ValueError('Unknown queued action' if queued else 'Unknown action')
        return getattr(self.model, command.method)

    def dispatch(self, action, args, settings_directory=None):
        if not isinstance(args, dict):
            raise ValueError('Request arguments must be an object.')
        settings = LocalSettings(settings_directory) if settings_directory is not None else self.local_settings
        if action == 'projects':
            return self.project_library.manage(**args)
        if action == 'choose_system_path':
            self.model.require_desktop()
            return choose_system_path(**args)
        if action == 'browse_directory':
            return browse_directory(**args)
        if action == 'read_render_settings':
            parameters,context=self.contracts.context(args,action)
            with self.model.lock:
                self.contracts.validate(context)
                return self.model.read_render_settings(**parameters)
        if action == 'ui_preferences':
            return settings.preferences(args)
        if action == 'state':
            return self.client_state(self.tasks.state(),args.get('client_id','local'))
        bridge_methods = {'companion_heartbeat': 'heartbeat', 'companion_goodbye': 'goodbye',
                          'companion_prepare': 'prepare'}
        if action in bridge_methods:
            return getattr(self.bridge, bridge_methods[action])(**args)
        if action=='project_view':
            parameters,context=self.contracts.context(args,action)
            # Personal navigation must not wait on the Blender worker/model lock.
            return self.local_settings.project_view(context['project_id'],context['client_id'],parameters if parameters else None)
        if action in {'storage_locations','storage_map'}:
            parameters,context=self.contracts.context(args,action)
            with self.model.lock:
                self.contracts.validate(context)
                if action=='storage_locations':return self.model.resolver.locations(context['project_id'])
                storage_id=parameters.get('storage_id')
                if not any(n.get('external') and n.get('storage_id')==storage_id for n in self.model.data['nodes']):raise ValueError('Unknown external storage reference.')
                self.model.resolver.map_location(context['project_id'],storage_id,parameters['path'])
                return self.client_state(self.model.state(),context['client_id'])
        if action == 'async':
            task = args.get('action')
            parameters = {key: value for key, value in args.items() if key != 'action'}
            method=self.command(task,queued=True)
            parameters,context=self.contracts.context(parameters,task)
            if not context['request_id']:raise ValueError('Request ID is required for queued operations.')
            bound=self.contracts.bind(task,method,context)
            return self.tasks.submit(task, parameters, bound,context=context,fingerprint=self.contracts.fingerprint(task,parameters,context))
        if self.tasks.active() and action not in {'render_cancel','cancel_queue'}:
            raise ValueError('A file operation is running. Graph navigation remains available; retry editing when it finishes.')
        if action == 'settings':
            return settings.configure_blender(self.model, args['blender'])
        method=getattr(self.model,action) if action in {'render_cancel','cancel_queue'} else self.command(action,queued=False)
        parameters,context=self.contracts.context(args,action)
        bound=self.contracts.bind(action,method,context)
        with self.model.lock:
            result=self._direct(action,parameters,context,bound)
            if action=='layout':self.local_settings.project_view(context['project_id'],context['client_id'],{'view':parameters['view']})
            return self.client_state(result,context['client_id'])
