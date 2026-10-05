"""Image references, project-owned replacements and immutable render copies."""
import copy
import hashlib
import os
from pathlib import Path
import shutil

from blender_pipeline.project.model import META, digest, stamp


def image_key(source, ref):
    identity = str(ref.get('raw', ref['path'])) + '\0' + ref.get('name', '')
    return source['id'] + ':' + hashlib.sha256(identity.encode()).hexdigest()


def image_location(pipeline, source, ref):
    original = Path(ref['path']).resolve()
    replacement = pipeline.data.get('image_replacements', {}).get(image_key(source, ref))
    # A restored original takes precedence over a render-only replacement.
    if not replacement: return original, False
    try:
        if original.is_file():
            with original.open('rb') as stream: stream.read(1)
            return original, False
    except OSError: pass
    path = (pipeline.root / replacement['path']).resolve()
    area = (pipeline.root / META / 'render-assets').resolve()
    if not path.is_relative_to(area) or not area.is_relative_to(pipeline.root):
        raise ValueError('Invalid render image replacement location.')
    return path, True


def image_members(ref, location):
    if not ref.get('pattern'): return [location], ''
    # Scanner supplies exact UDIM tile members; unknown sequences remain warnings.
    files = ref.get('image_files', [])
    if ref.get('image_source') == 'TILED' and files:
        return [Path(path).resolve() for path in files], ''
    return [], 'Sequence / tiled image could not be reliably collected'


def inspect_image(pipeline, source, ref):
    location, replaced = image_location(pipeline, source, ref)
    members, problem = image_members(ref, location)
    if not problem and any(not path.is_file() for path in members): problem = 'Image file is missing'
    if not problem: return None
    unused = ref.get('image_usage') == 'unused'
    return {'source_id': source['id'], 'source_name': source['name'], 'path': str(Path(ref['path']).resolve()),
            'name': ref.get('name', ''), 'reason': problem, 'usage': ref.get('image_usage', 'unknown'),
            'severity': 'notice' if unused else 'warning', 'can_locate': not ref.get('pattern'),
            'image_id': image_key(source, ref)}


def capture_image(pipeline, source, ref, cache=None):
    location, replaced = image_location(pipeline, source, ref)
    members, problem = image_members(ref, location)
    if problem: return [], inspect_image(pipeline, source, ref)
    original = str(Path(ref['path']).resolve())
    directory = META + '/images/' + hashlib.sha256(os.path.normcase(original).encode()).hexdigest()
    result = []
    try:
        for member in members:
            info = member.stat(); signature = [info.st_mtime_ns, info.st_size]
            key = (str(member), *signature)
            content = cache.get(key) if cache is not None else None
            if content is None:
                content = digest(member)
                if cache is not None: cache[key] = content
            managed = not replaced and not ref.get('pattern') and ref.get('relative') and member.is_relative_to(pipeline.root)
            result.append({'original_path': original, 'source_path': str(member),
                           'source_relative': member.relative_to(pipeline.root).as_posix() if member.is_relative_to(pipeline.root) else None,
                           'target': member.relative_to(pipeline.root).as_posix() if managed else directory + '/' + member.name, 'hash': content,
                           'signature': signature, 'image_id': image_key(source, ref), 'managed': bool(managed),
                           'name': ref.get('name', ''), 'replacement': replaced,
                           'pattern_name': location.name if ref.get('pattern') else ''})
    except OSError as exc:
        try: issue = inspect_image(pipeline, source, ref)
        except OSError: issue = None
        if not issue:
            issue = {'source_id': source['id'], 'source_name': source['name'], 'path': original,
                     'name': ref.get('name', ''), 'reason': 'Image cannot be read: ' + str(exc),
                     'usage': ref.get('image_usage', 'unknown'), 'severity': 'notice' if ref.get('image_usage') == 'unused' else 'warning',
                     'can_locate': not ref.get('pattern'), 'image_id': image_key(source, ref)}
        return [], issue
    return result, None


def image_identity(images):
    return {(image['original_path'], image['source_path'], image['target'], image['hash']) for image in images}


def freeze_images(pipeline, images, inputs):
    copied = {}
    for image in images:
        source = (pipeline.root / image['source_relative']).resolve() if image.get('source_relative') else Path(image['source_path']).resolve()
        target = (inputs / image['target']).resolve()
        if image.get('managed'):
            if not target.is_relative_to(inputs) or digest(target) != image['hash']:
                raise ValueError('Managed image snapshot changed: ' + str(source))
            continue
        area = (inputs / META / 'images').resolve()
        if not area.is_relative_to(inputs) or not target.is_relative_to(area): raise ValueError('Invalid image snapshot destination.')
        if target in copied:
            if copied[target] != image['hash']: raise ValueError('Conflicting image snapshot inputs.')
            continue
        copied[target] = image['hash']
        target.parent.mkdir(parents=True, exist_ok=True)
        before = digest(source)
        if before != image['hash']: raise ValueError('Queued image changed: ' + str(source) + '. Submit a new render.')
        shutil.copy2(source, target)
        if digest(source) != before or digest(target) != before:
            raise ValueError('Image changed while freezing: ' + str(source))


def locate_image(pipeline, source_id, path, replacement):
    """Copy a chosen file for rendering; never modify a working Blend file."""
    source = pipeline.node(source_id)
    if source['type'] != 'blend': raise ValueError('Choose an image dependency from a Blend File.')
    original = os.path.normcase(str(Path(path).resolve()))
    ref = next((r for r in source.get('scan', {}).get('refs', []) if r.get('kind') == 'Image'
                and os.path.normcase(str(Path(r['path']).resolve())) == original), None)
    if not ref or ref.get('pattern'): raise ValueError('Choose a missing single-image reference from the current scan.')
    chosen = Path(replacement).expanduser().resolve()
    if not chosen.is_file(): raise ValueError('Choose an existing image file.')
    if chosen.suffix.lower() not in {'.png','.jpg','.jpeg','.exr','.hdr','.tif','.tiff','.tga','.bmp','.webp','.dds','.jp2','.j2c','.sgi','.rgb','.rgba','.cin','.dpx','.psd'}:
        raise ValueError('Choose an image file, such as PNG, JPEG, EXR or TIFF.')
    content = digest(chosen)
    area = (pipeline.root / META / 'render-assets').resolve()
    target = (area / content / chosen.name).resolve()
    if not area.is_relative_to(pipeline.root) or not target.is_relative_to(area): raise ValueError('Invalid replacement directory.')
    before = copy.deepcopy(pipeline.data.get('image_replacements', {})); created = not target.exists()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if created: shutil.copy2(chosen, target)
        if digest(chosen) != content or digest(target) != content: raise ValueError('Replacement changed while copying. Choose it again.')
        entries = pipeline.data.setdefault('image_replacements', {})
        for node in pipeline.data['nodes']:
            for candidate in node.get('scan', {}).get('refs', []):
                if candidate.get('kind') == 'Image' and not candidate.get('pattern') and os.path.normcase(str(Path(candidate['path']).resolve())) == original:
                    entries[image_key(node, candidate)] = {'path': target.relative_to(pipeline.root).as_posix(), 'hash': content, 'created': stamp()}
        pipeline.save()
    except Exception:
        pipeline.data['image_replacements'] = before
        if created: target.unlink(missing_ok=True)
        raise
    return pipeline.state()
