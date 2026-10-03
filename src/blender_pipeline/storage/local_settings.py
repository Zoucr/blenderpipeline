"""Machine-local preferences and executable configuration, outside project data."""
import json
import hashlib
import math
from pathlib import Path
from blender_pipeline.storage.projects import atomic_json
from blender_pipeline.storage.locks import exclusive_file


class LocalSettings:
    def __init__(self, directory):
        self.directory = Path(directory)

    def client_path(self, client_id):
        if not isinstance(client_id,str) or not 1<=len(client_id)<=128:
            raise ValueError('Invalid client ID.')
        return self.directory/'clients'/(hashlib.sha256(client_id.encode()).hexdigest()+'.json')

    def project_view(self, project_id, client_id, update=None):
        path=self.client_path(client_id)
        with exclusive_file(path.with_suffix('.lock')):
            data=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
            if update is not None:
                view=update.get('view')
                if view is not None and (not isinstance(view,dict) or any(type(view.get(k)) not in {int,float} or not math.isfinite(view[k]) for k in ('x','y','zoom')) or view['zoom']<=0):
                    raise ValueError('Invalid graph view.')
                if update.get('selected') is not None and not isinstance(update['selected'],str):raise ValueError('Invalid selection.')
                if update.get('tab') is not None and (not isinstance(update['tab'],str) or len(update['tab'])>50):raise ValueError('Invalid inspector tab.')
                previous=data.setdefault('projects',{}).get(project_id,{})
                data['projects'][project_id]={**previous,**{k:v for k,v in update.items() if k in {'view','selected','tab'}}}
                atomic_json(path,data)
            return data.get('projects',{}).get(project_id,{})

    def preferences(self, args):
        client_id=args.get('client_id')
        path = self.client_path(client_id) if client_id else self.directory / 'ui-preferences.json'
        data=json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
        previous=data.get('panels',{}) if client_id else data
        if args.get('read'):
            return previous
        width = args.get('width', 360)
        if type(width) is not int or not 290 <= width <= 600:
            raise ValueError('Panel width must be between 290 and 600 pixels.')
        if any(type(args.get(key)) is not bool for key in ('navigator', 'inspector')):
            raise ValueError('Panel visibility must be true or false.')
        result = {key: args[key] for key in ('navigator', 'inspector')}
        result['width'] = width
        nav_width = args.get('navigator_width', previous.get('navigator_width', 220))
        if type(nav_width) is not int or not 160 <= nav_width <= 520:
            raise ValueError('Project files width must be between 160 and 520 pixels.')
        if 'navigator_width' in args or 'navigator_width' in previous:
            result['navigator_width'] = nav_width
        with exclusive_file(path.with_suffix('.lock')):
            if client_id:
                data=json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
                data['panels']=result;atomic_json(path,data)
            else:atomic_json(path, result)
        return result

    def configure_blender(self, model, executable):
        executable = Path(executable)
        if not executable.is_file():
            raise ValueError('Blender executable not found')
        atomic_json(self.directory / 'settings.json', {'blender': str(executable)})
        model.blender = str(executable)
        return model.state()
