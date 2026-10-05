"""Summarize actual image sequences on disk without returning every frame."""
import re
from pathlib import Path

IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.exr', '.tif', '.tiff', '.webp', '.bmp'}
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.mkv', '.avi', '.webm'}


def frame_ranges(frames, step=1):
    ranges = []
    for frame in sorted(frames):
        if ranges and frame == ranges[-1][1] + step:
            ranges[-1][1] = frame
        else:
            ranges.append([frame, frame])
    return ranges


class SequenceInventory:
    def __init__(self, directory, project_root, runs):
        self.directory = directory
        self.owners = sorted(((project_root / r['output'], r) for r in runs if r.get('output') and r['status'] != 'Deleted'),
                             key=lambda item: len(item[0].parts), reverse=True)
        self.groups = {}
        self.owner_cache = {}

    def add(self, file):
        if file.suffix.lower() not in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
            return
        if file.parent not in self.owner_cache:
            self.owner_cache[file.parent] = next((r for path, r in self.owners if file.is_relative_to(path)), None)
        owner = self.owner_cache[file.parent]
        video = file.suffix.lower() in VIDEO_EXTENSIONS
        match = None if video else re.search(r'(-?\d{4,})$', file.stem)
        prefix = file.stem[:match.start()] if match else file.stem
        relative = file.relative_to(self.directory).as_posix()
        kind = 'compositor' if 'compositor' in file.relative_to(self.directory).parts[:-1] else 'final'
        key = (file.parent, prefix, file.suffix.lower())
        if key not in self.groups:
            config = (owner or {}).get('config', {})
            self.groups[key] = dict(directory=file.parent.relative_to(self.directory).as_posix(), prefix=prefix,
                                    scene=config.get('scene', ''), view_layer=config.get('view_layer', ''),
                                    node_id=(owner or {}).get('node_id'), run_id=(owner or {}).get('id'), version=(owner or {}).get('number'),
                                    operation_id=(owner or {}).get('operation_id'), target_id=(owner or {}).get('target_id'),
                                    status=(owner or {}).get('status'), step=config.get('step', 1), kind=kind,
                                    images=0, videos=0, frames=set(), sample=relative,
                                    expected_frames=len(range(config['start'], config['end'] + 1, config.get('step', 1)))
                                    if 'start' in config and 'end' in config else None)
        group = self.groups[key]
        group['videos' if video else 'images'] += 1
        if match:
            group['frames'].add(int(match[1]))

    def result(self):
        result = []
        for group in self.groups.values():
            frames = group.pop('frames')
            group.update(frame_count=len(frames), ranges=frame_ranges(frames, group['step']))
            result.append(group)
        return result
