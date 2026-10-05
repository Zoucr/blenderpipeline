"""Saved render inputs and explicit consent for images that cannot be frozen."""
import os
from pathlib import Path

from blender_pipeline.project.model import digest
from blender_pipeline.rendering.images import capture_image


class RenderImageWarnings(ValueError):
    code = 'render_image_warnings'

    def __init__(self, warnings):
        self.dependency_warnings = unique_warnings(warnings)
        super().__init__('Review image dependencies before rendering. Render anyway is available for these images:\n' +
                         '\n'.join(w['path'] for w in self.dependency_warnings))


def unique_warnings(warnings):
    result = {}
    for warning in warnings:
        key = (warning['path'], warning['reason'])
        if key not in result or warning.get('severity', 'warning') == 'warning': result[key] = warning
    return list(result.values())


def warning_keys(warnings):
    if not isinstance(warnings, list) or any(not isinstance(w, dict) or
            any(not isinstance(w.get(k), str) for k in ('source_id', 'path', 'reason')) for w in warnings):
        raise ValueError('Invalid image warning acknowledgement.')
    return {(w['path'], w['reason']) for w in warnings}


def render_inputs(pipeline, node, collect_images=False, images=None, notices=None):
    lookup = {}
    for entry in pipeline.data['nodes']:
        if entry['type'] == 'blend':
            try: lookup[os.path.normcase(str(pipeline.path(entry)))] = entry
            except ValueError: pass
    pending = [pipeline.path(node)]
    files, warnings, seen, image_cache = {}, [], set(), {}
    while pending:
        path = pending.pop().resolve()
        key = os.path.normcase(str(path))
        if key in seen: continue
        seen.add(key)
        source = lookup.get(key)
        if not source or source.get('scan', {}).get('error'):
            raise ValueError('Refresh and resolve this render input first: ' + str(path))
        if pipeline.companion and any(s['dirty'] for s in pipeline.companion.opened(path)):
            raise ValueError('Save this render input first: ' + str(path))
        if not path.is_relative_to(pipeline.root):
            raise ValueError('Collect external libraries before rendering: ' + str(path))
        stat = path.stat()
        signature = source.get('scan', {}).get('signature')
        if signature and signature != [stat.st_mtime_ns, stat.st_size]:
            raise ValueError('Render input changed after scanning. Save and queue again: ' + str(path))
        relative=path.relative_to(pipeline.root).as_posix()
        if relative not in files:files[relative] = digest(path)
        for ref in source['scan'].get('refs', []):
            dependency = Path(ref['path']).resolve()
            if collect_images and ref['kind'] == 'Image':
                captured, issue = capture_image(pipeline, source, ref, image_cache)
                if issue: warnings.append(issue)
                elif images is not None: images.extend(captured)
                # Preserve the existing manifest for portable project images.
                if captured and not ref.get('pattern') and ref.get('relative') and dependency.is_relative_to(pipeline.root) and dependency.is_file():
                    files[dependency.relative_to(pipeline.root).as_posix()] = captured[0]['hash']
                continue
            reasons = []
            if ref.get('pattern'): reasons.append('Sequence / tiled image cannot be frozen')
            elif not ref.get('exists') or not dependency.is_file(): reasons.append('Image file is missing')
            if not dependency.is_relative_to(pipeline.root): reasons.append('Outside the project')
            if not ref.get('relative'): reasons.append('Absolute file reference')
            if reasons:
                if ref['kind'] != 'Image':
                    raise ValueError('Resolve dependency before rendering: ' + str(dependency))
                warnings.append({'source_id': source['id'], 'source_name': source['name'],
                                 'path': str(dependency), 'name': ref.get('name', ''), 'reason': ' · '.join(reasons)})
                continue
            relative=dependency.relative_to(pipeline.root).as_posix()
            if relative not in files:files[relative] = digest(dependency)
            if ref['kind'] == 'Library': pending.append(dependency)
    warnings = unique_warnings(warnings)
    if collect_images:
        if notices is not None: notices.extend(w for w in warnings if w.get('severity') == 'notice')
        warnings = [w for w in warnings if w.get('severity') != 'notice']
    return files, warnings
