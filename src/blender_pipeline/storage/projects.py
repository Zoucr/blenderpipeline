"""Versioned project persistence. No Blender, HTTP, or UI dependencies."""
import copy
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Protocol
from blender_pipeline.storage.locks import exclusive_file

CURRENT_SCHEMA = 3


class RevisionConflict(ValueError):
    status = 412
    code = 'revision_conflict'

    def __init__(self, expected, actual):
        self.expected, self.actual = expected, actual
        super().__init__(f'Project changed (expected revision {expected}, current revision {actual}). Refresh before retrying; your edit was not applied.')


def atomic_json(path, data):
    """Use a unique sibling file so unrelated writers cannot share a temp name."""
    path = Path(path)
    content = json.dumps(data, indent=2, ensure_ascii=False)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix=path.name + '.', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def validate_project(data):
    if not isinstance(data, dict):
        raise ValueError('Project data must be an object.')
    if not isinstance(data.get('id'), str) or not data['id']:
        raise ValueError('Project ID is missing.')
    if not isinstance(data.get('name'), str) or not data['name']:
        raise ValueError('Project name is missing.')
    if not isinstance(data.get('nodes'), list):
        raise ValueError('Project nodes must be a list.')
    if type(data.get('revision')) is not int or data['revision'] < 0:
        raise ValueError('Project revision is missing or invalid.')
    seen = set()
    for node in data['nodes']:
        if not isinstance(node, dict) or not isinstance(node.get('id'), str) or not node['id']:
            raise ValueError('Each project node must have an ID.')
        if node['id'] in seen:
            raise ValueError('Project contains duplicate node IDs.')
        seen.add(node['id'])
        if node.get('type') in {'frame', 'export', 'render'}:
            if 'path' in node or node.get('external'):
                raise ValueError('Operation nodes and frames do not own working file paths.')
            continue
        if node.get('type') not in {'blend', 'folder'} or not isinstance(node.get('path'), str):
            raise ValueError('Project contains an invalid file or folder node.')
        raw = node['path']
        if not raw or Path(raw).is_absolute() or '\\' in raw or ':' in raw or '..' in Path(raw).parts:
            raise ValueError('Project files require portable relative paths.')
        if node.get('external'):
            if not isinstance(node.get('storage_id'), str) or not node['storage_id'].startswith('external-'):
                raise ValueError('External library storage reference is missing.')
    view = data.get('view')
    if not isinstance(view, dict) or any(type(view.get(k)) not in {int, float} for k in ('x', 'y', 'zoom')):
        raise ValueError('Project graph view is invalid.')
    if any(not math.isfinite(view[k]) for k in ('x', 'y', 'zoom')) or view['zoom'] <= 0:
        raise ValueError('Project graph view is invalid.')


def validate_document(source):
    """Validate fresh-format metadata without modifying the caller or disk."""
    data = copy.deepcopy(source)
    if not isinstance(data, dict):
        raise ValueError('Project data must be an object.')
    version = data.get('schema')
    if type(version) is not int or version != CURRENT_SCHEMA:
        raise ValueError('This build uses fresh project format 3. Create a new project; older project files are left untouched. Newer formats require a newer Pipeline build.')
    validate_project(data)
    return data


class ProjectRepository(Protocol):
    def load(self, root: Path) -> dict: ...
    def save(self, root: Path, data: dict) -> None: ...


class JsonProjectRepository:
    def load(self, root):
        path = Path(root) / '.pipeline' / 'project.json'
        return validate_document(json.loads(path.read_bytes()))

    def save(self, root, data):
        if data.get('schema') != CURRENT_SCHEMA:
            raise ValueError('Create a fresh format-3 project before saving.')
        validate_project(data)
        path = Path(root) / '.pipeline' / 'project.json'
        with exclusive_file(path.with_suffix('.lock')):
            if path.exists():
                current = json.loads(path.read_bytes())
                if current.get('id') != data['id']:
                    raise ValueError('Project identity changed on disk.')
                if current.get('revision') != data['revision']:
                    raise RevisionConflict(data['revision'], current.get('revision'))
            elif data['revision'] != 0:
                raise ValueError('Project metadata disappeared. Save stopped.')
            saved = copy.deepcopy(data)
            saved['revision'] += 1
            atomic_json(path, saved)
            data['revision'] = saved['revision']
