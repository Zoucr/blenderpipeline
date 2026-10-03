"""Recent/pinned project catalog; removal never deletes project files."""
from pathlib import Path
from blender_pipeline.storage.projects import atomic_json


class ProjectLibrary:
    def __init__(self, model, tasks):
        self.model, self.tasks = model, tasks

    def manage(self, mode='list', path=None, entry=None):
        entries = self.model.recent()
        if mode != 'list' and self.tasks.active():
            raise ValueError('Wait for the queued file operation before editing the project library.')
        if mode in {'remove', 'pin'}:
            selected = next((item for item in entries if item['path'] == path), None)
            if selected is None:
                raise ValueError('Project is not in the library.')
            if mode == 'remove':
                entries.remove(selected)
            else:
                selected['pinned'] = not selected.get('pinned', False)
            atomic_json(self.model.registry, entries)
        elif mode == 'restore':
            entry = entry or {}
            root = Path(entry.get('path', ''))
            if not root.is_absolute() or not (root / '.pipeline' / 'project.json').is_file():
                raise ValueError('Project folder is missing. Use Open project to locate it.')
            if not any(item['path'] == str(root) for item in entries):
                entries.append({'path': str(root), 'name': str(entry.get('name', root.name)),
                                'pinned': bool(entry.get('pinned', False))})
                atomic_json(self.model.registry, entries)
        elif mode != 'list':
            raise ValueError('Unknown project library action.')
        return {'projects': [{**item, 'available': (Path(item['path']) / '.pipeline' / 'project.json').is_file()}
                             for item in entries]}
