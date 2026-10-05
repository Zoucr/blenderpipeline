"""Restore approved live image paths in disposable render data only."""
import os
from pathlib import Path


def blender_file_path(path, extra=0):
    """OpenImageIO on Windows needs an extended path for long filenames."""
    value = str(path)
    if os.name == 'nt' and len(value) + extra >= 240 and not value.startswith('\\\\?\\'):
        return '\\\\?\\UNC\\' + value[2:] if value.startswith('\\\\') else '\\\\?\\' + value
    return value


def original_image_path(image, job, abspath):
    current = Path(abspath(image.filepath, library=image.library)).resolve()
    return (Path(job['project_root']) / os.path.relpath(current, job['input_root'])).resolve() if image.filepath.startswith('//') else current


def restore_image_inputs(images, job, abspath):
    mapping = {os.path.normcase(item['original_path']): item for item in job.get('image_inputs', [])}
    restored = []
    for image in images:
        if image.source not in {'FILE', 'TILED', 'SEQUENCE'} or image.packed_file: continue
        original = original_image_path(image, job, abspath)
        record = mapping.get(os.path.normcase(str(original)))
        if not record: continue
        root = Path(job['input_root']).resolve()
        target = (root / record['target']).resolve()
        if record.get('pattern_name'): target = target.with_name(record['pattern_name'])
        if not target.is_relative_to(root): raise ValueError('Image snapshot is outside the render inputs.')
        image.filepath = blender_file_path(target)
        restored.append({'name': image.name, 'original': str(original), 'snapshot': str(target)})
    return restored


def restore_warning_images(images, job, abspath):
    warnings = {os.path.normcase(w['path']) for w in job.get('image_warnings', [])}
    if not warnings: return []
    restored = []
    for image in images:
        if image.source not in {'FILE', 'TILED', 'SEQUENCE'} or image.packed_file: continue
        original = original_image_path(image, job, abspath)
        if os.path.normcase(str(original)) in warnings:
            image.filepath = str(original)
            restored.append({'name': image.name, 'path': str(original)})
    return restored
