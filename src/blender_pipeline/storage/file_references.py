"""One resolver for managed files and machine-local external storage mappings."""
import json
from pathlib import Path, PurePosixPath
from blender_pipeline.storage.projects import atomic_json
from blender_pipeline.storage.locks import exclusive_file


class FileResolver:
    def __init__(self, directory):
        self.directory = Path(directory)

    def locations(self, project_id):
        path = self.directory / 'storage-locations.json'
        data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        return data.get(project_id, {})

    def map_location(self, project_id, storage_id, directory):
        directory = Path(directory).resolve()
        if not directory.is_dir():
            raise ValueError('Choose an existing storage folder.')
        path = self.directory / 'storage-locations.json'
        with exclusive_file(path.with_suffix('.lock')):
            data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
            data.setdefault(project_id, {})[storage_id] = str(directory)
            atomic_json(path, data)

    def normalize(self, project_id, node):
        # Existing operation builders can supply a desktop path at registration.
        # Only the local mapping retains it; persisted references are relative.
        if node.get('external'):
            storage = node.get('storage_id') or 'external-' + node['id']
            absolute = Path(node['path'])
            if absolute.is_absolute():
                self.map_location(project_id, storage, absolute.parent)
                node['path'] = absolute.name
            node['storage_id'] = storage
        else:
            node['storage_id'] = 'project'

    def reference(self, node):
        return {'file_id': node['id'], 'storage_id': node.get('storage_id', 'project'),
                'relative_path': node['path']}

    def resolve(self, root, project_id, node):
        raw = node['path']
        # Temporary operation builders, before normalize/save.
        if node.get('external') and Path(raw).is_absolute():
            return Path(raw).resolve()
        relative = PurePosixPath(raw)
        if relative.is_absolute() or '..' in relative.parts or '\\' in raw or ':' in raw:
            raise ValueError('Invalid relative file reference.')
        storage = node.get('storage_id', 'project') if node.get('external') else 'project'
        if storage == 'project':
            base = Path(root).resolve()
        else:
            location = self.locations(project_id).get(storage)
            if not location:
                raise ValueError('Asset location unavailable: ' + storage + '. Map its storage folder on this machine.')
            base = Path(location).resolve()
        result = (base / raw).resolve()
        if not result.is_relative_to(base) or storage == 'project' and result.is_relative_to(base / '.pipeline'):
            raise ValueError('Invalid managed path.')
        if node.get('external') and result.suffix.lower() != '.blend':
            raise ValueError('External libraries must reference a .blend file.')
        return result
