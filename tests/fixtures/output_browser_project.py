"""Small synthetic saved-render project for browser QA; no production files needed."""
import struct
import zlib
from pathlib import Path

from blender_pipeline.project.model import stamp


def image_png(path, phase=0):
    """Draw a small recognizable test pattern without adding a graphics dependency."""
    width, height = 640, 360
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    pixels = bytearray()
    for y in range(height):
        pixels.append(0)
        for x in range(width):
            circle = (x - 320 - phase * 12) ** 2 + (y - 180) ** 2 < 85 ** 2
            if circle:
                rgb = (70 + x // 5, 110 + y // 4, 150 + phase * 8)
            else:
                rgb = (24 + y // 12, 30 + y // 12, 38 + y // 12)
            pixels.extend(rgb)
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)) +
                     chunk(b'IDAT', zlib.compress(pixels)) + chunk(b'IEND', b''))


def make_project(p, base):
    p.create(base, 'Output Browser Demo')
    p.folder('Outputs', x=620, y=10)
    parent = p.data['nodes'][-1]
    p.folder('Shots', x=650, y=140, folder_id=parent['id'])
    folder = p.data['nodes'][-1]
    source = {'id': 'shot', 'type': 'blend', 'name': 'Scene File', 'path': 'Scene.blend',
              'x': 20, 'y': 40, 'scan': {'refs': [], 'scenes': []}, 'snapshots': []}
    path = p.root / source['path']; path.write_bytes(b'disposable saved-file fixture')
    stat = path.stat(); source['scan']['signature'] = [stat.st_mtime_ns, stat.st_size]
    p.data['nodes'].append(source)
    p.render_node(source_ids=[], x=310, y=50)
    operation = p.data['nodes'][-1]; operation['name'] = 'Render Shots'
    targets = []
    for scene in ['Scene One', 'Scene Two']:
        for layer in ['Beauty', 'Mask']:
            identity = scene + '-' + layer
            targets.append({'id': identity, 'source_id': source['id'], 'scene': scene, 'view_layer': layer,
                            'camera': '', 'compositor': 'OFF', 'prefix': '', 'label': '',
                            'mode': 'ANIMATION', 'frame': None, 'enabled': True, 'overrides': {}})
    operation['render_plan'] = {'targets': targets, 'source_ids': [source['id']], 'folder_id': folder['id'], 'overrides': {}}
    p.data['renders'] = []
    for target in targets:
        numbers = [1, 2, 3] if target is targets[0] else [1]
        for number in numbers:
            identity = target['id'] + '-r' + str(number)
            frames = [] if number == 3 else [1, 3, 5] if number == 2 else [1, 2, 3, 4, 5]
            prefix = '261005_' + target['scene'].replace(' ', '_') + '_'
            output = folder['path'] + '/' + target['scene'] + '/' + target['view_layer'] + '/r' + str(number).zfill(3)
            config = {'folder_id': folder['id'], 'scene': target['scene'], 'view_layer': target['view_layer'],
                      'start': 1, 'end': 5, 'step': 1, 'mode': 'ANIMATION', 'prefix': prefix}
            run = {'id': identity, 'node_id': source['id'], 'operation_id': operation['id'], 'target_id': target['id'],
                   'name': source['name'], 'config': config, 'number': number, 'created': stamp(), 'finished': stamp(),
                   'status': 'Failed' if number == 3 else 'Cancelled' if number == 2 else 'Complete',
                   'output': output, 'image_count': len(frames) * 2, 'progress': 100, 'queue_id': None}
            p.data['renders'].append(run)
            for frame in frames:
                image_png(p.root / output / (prefix + str(frame).zfill(4) + '.png'), frame)
                image_png(p.root / output / 'compositor' / (prefix + 'Mist_' + str(frame).zfill(4) + '.png'), 0)
    p.save()
    return parent, folder
