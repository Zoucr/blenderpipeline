"""Read saved render versions and preview media without moving project outputs."""
from dataclasses import dataclass
import copy
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
import tempfile
import threading

from .inventory import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS
from blender_pipeline.project.model import META

NATIVE_IMAGES = {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}
MAX_FILES = 20000
MAX_MEDIA_BYTES = 256 * 1024 * 1024


@dataclass(frozen=True)
class OutputVersion:
    root: Path
    directory: Path
    run: dict


@dataclass(frozen=True)
class OutputMedia:
    path: Path
    content_type: str


class OutputBrowser:
    def __init__(self, model, settings_directory):
        self.model = model
        self.cache = Path(settings_directory) / 'output-previews'
        self.preview_lock = threading.Lock()

    def version(self, run_id):
        """Capture a version under the application's project-context lock."""
        run = next((r for r in self.model.data.get('renders', []) if r['id'] == run_id), None)
        if not run or run['status'] == 'Deleted':
            raise ValueError('This render version is unavailable.')
        root = self.model.root.resolve()
        raw = root / run['output']
        directory = raw.resolve()
        if directory == root or not directory.is_relative_to(root) or directory.is_relative_to(root / META):
            raise ValueError('Invalid render output directory.')
        self._no_links(raw, root)
        return OutputVersion(root, directory, copy.deepcopy(run))

    @staticmethod
    def _no_links(path, boundary):
        for item in [path, *path.parents]:
            if item == boundary:
                return
            if item.is_symlink() or getattr(item, 'is_junction', lambda: False)():
                raise ValueError('Linked output paths cannot be previewed.')
        raise ValueError('Output path is outside the project.')

    def file(self, version, relative):
        if not isinstance(relative, str) or not relative or '\\' in relative:
            raise ValueError('Choose a file from this render version.')
        reference = Path(relative)
        if reference.is_absolute() or '..' in reference.parts:
            raise ValueError('Invalid output file reference.')
        raw = version.directory / reference
        path = raw.resolve()
        if not path.is_relative_to(version.directory) or path.suffix.lower() not in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
            raise ValueError('Choose a rendered image or video.')
        self._no_links(raw, version.root)
        if not path.is_file():
            raise ValueError('This output file is missing. Refresh the browser.')
        return path

    def files(self, version):
        """Only the selected version is enumerated; older versions remain lazy."""
        groups = {}
        count = 0
        truncated = False
        if not version.directory.is_dir():
            return {'run_id': version.run['id'], 'sequences': [], 'missing': True, 'truncated': False}
        prefix = version.run.get('config', {}).get('prefix', '')
        for current, directories, names in os.walk(version.directory, followlinks=False):
            count += 1  # Also bound directory traversal, including empty trees.
            if count > MAX_FILES:
                truncated = True
                break
            directories[:] = sorted(d for d in directories if not (Path(current) / d).is_symlink()
                                    and not getattr(Path(current) / d, 'is_junction', lambda: False)())
            for name in sorted(names):
                count += 1
                if count > MAX_FILES:
                    truncated = True
                    break
                path = Path(current) / name
                extension = path.suffix.lower()
                if extension not in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS or path.is_symlink():
                    continue
                try:
                    stat = path.stat()
                except OSError:
                    continue  # A running render or cleanup may change the listing.
                relative = path.relative_to(version.directory).as_posix()
                video = extension in VIDEO_EXTENSIONS
                match = None if video else re.search(r'(-?\d{4,})$', path.stem)
                stem = path.stem[:match.start()] if match else path.stem
                kind = 'compositor' if 'compositor' in path.relative_to(version.directory).parts[:-1] else 'final'
                identity = str(path.parent.relative_to(version.directory).as_posix()) + '/' + stem + extension
                if identity not in groups:
                    label = stem.removeprefix(prefix).strip('_') or 'Output'
                    groups[identity] = {'id': identity, 'kind': kind, 'name': label if kind == 'compositor' else 'Final',
                                        'format': extension[1:].upper(), 'video': video, 'frames': []}
                groups[identity]['frames'].append({'path': relative, 'name': name,
                                                   'frame': int(match[1]) if match else None,
                                                   'size': stat.st_size, 'modified': str(stat.st_mtime_ns)})
            if truncated:
                break
        sequences = sorted(groups.values(), key=lambda s: (s['kind'] != 'final', s['name'].casefold(), s['format']))
        for sequence in sequences:
            sequence['frames'].sort(key=lambda f: (f['frame'] is None, f['frame'] or 0, f['name']))
        return {'run_id': version.run['id'], 'sequences': sequences, 'missing': False, 'truncated': truncated}

    def preview(self, version, relative):
        source = self.file(version, relative)
        extension = source.suffix.lower()
        if extension in NATIVE_IMAGES | VIDEO_EXTENSIONS:
            if source.stat().st_size > MAX_MEDIA_BYTES:
                raise ValueError('This file is too large for the browser viewer. Use Open folder.')
            return OutputMedia(source, mimetypes.guess_type(source.name)[0] or 'application/octet-stream')
        # Blender reads EXR/TIFF; generated display PNGs are machine-local and bounded.
        stat = source.stat()
        advanced = (version.run.get('actual_settings') or {}).get('advanced') or version.run.get('config', {}).get('advanced') or {}
        color = {**((version.run.get('actual_settings') or {}).get('color_management') or {}),
                 **{key: value for key, value in advanced.items() if key.startswith('["color",')}}
        key = hashlib.sha256(json.dumps([str(source), stat.st_size, stat.st_mtime_ns, color], sort_keys=True).encode()).hexdigest()
        with self.preview_lock:
            self.cache.mkdir(parents=True, exist_ok=True)
            target = self.cache / (key + '.png')
            if not target.is_file():
                # Keep the atomic rename on one volume, including custom data dirs.
                with tempfile.TemporaryDirectory(prefix='preview-', dir=self.cache) as temporary:
                    base = Path(temporary)
                    output = base / 'preview.png'
                    job = base / 'job.json'
                    job.write_text(json.dumps({'source': str(source), 'output': str(output), 'color': color}), encoding='utf-8')
                    self.model.runtime.run(self.model.blender, 'preview_image.py', [str(job)])
                    if not output.is_file():
                        raise ValueError('Blender did not generate a preview. Use Open folder to inspect this output.')
                    os.replace(output, target)
            os.utime(target, None)
            self._trim_cache(target)
        return OutputMedia(target, 'image/png')

    def _trim_cache(self, keep):
        entries = sorted(self.cache.glob('*.png'), key=lambda p: p.stat().st_mtime_ns, reverse=True)
        total = 0
        for index, path in enumerate(entries):
            total += path.stat().st_size
            if path != keep and (index >= 64 or total > MAX_MEDIA_BYTES):
                try:
                    path.unlink()
                except OSError:
                    pass  # A preview may still be streamed to an open viewer.
