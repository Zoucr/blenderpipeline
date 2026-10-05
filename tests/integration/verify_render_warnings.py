"""Real linked image paths, missing unused texture, explicit consent and CPU render."""
import json
from pathlib import Path
import tempfile
import threading
import time
from unittest.mock import patch
import subprocess

from blender_pipeline.project.workspace import Pipeline
from blender_pipeline.project.model import digest
from blender_pipeline.rendering.inputs import RenderImageWarnings
from support import WORKERS


def prepare_fixture(p, base):
    p.create(base, 'Image warnings')
    p.folder('Outputs'); folder = p.data['nodes'][-1]
    p.create_blend('Models', template_id=''); model = p.data['nodes'][-1]
    textures = base / 'Textures'; textures.mkdir()
    fixture = base / 'images.py'
    fixture.write_text('''import bpy, os, sys
from pathlib import Path
target, textures = map(Path,sys.argv[sys.argv.index('--')+1:])
bpy.ops.wm.read_factory_settings(use_empty=False)
image=bpy.data.images.new('Green image',width=2,height=2)
image.pixels=[0,1,0,1]*4
image.filepath_raw=str(textures/'green.png');image.file_format='PNG';image.save()
green=bpy.data.images.load(str(textures/'green.png'));green.name='External green'
green.filepath='//'+os.path.relpath(textures/'green.png',target.parent)
missing=bpy.data.images.new('Unused alpha',width=2,height=2)
missing.source='FILE';missing.filepath='//'+os.path.relpath(textures/'unused_ALPHA.png',target.parent)
mat=bpy.data.materials.new('Green material');mat.use_nodes=True
nodes=mat.node_tree.nodes
tex=nodes.new('ShaderNodeTexImage');tex.image=green
unused=nodes.new('ShaderNodeTexImage');unused.image=missing
mat.node_tree.links.new(tex.outputs['Color'],nodes.get('Principled BSDF').inputs['Base Color'])
bpy.data.objects['Cube'].data.materials.clear();bpy.data.objects['Cube'].data.materials.append(mat)
s=bpy.context.scene;s.render.engine='CYCLES';s.cycles.samples=1;s.cycles.use_denoising=False
s.render.resolution_x=16;s.render.resolution_y=16;s.render.resolution_percentage=100
s.frame_start=1;s.frame_end=1;s.view_settings.view_transform='Standard'
bpy.context.preferences.filepaths.save_version=0
bpy.ops.wm.save_as_mainfile(filepath=str(target))
''', encoding='utf-8')
    p.run(str(fixture), [p.path(model), textures]); p.refresh(model['id'])
    p.create_blend('Lighting', template_id=''); shot = p.data['nodes'][-1]
    p.link_batch(model['id'], shot['id'], [{'kind': 'collections', 'name': 'Collection'}], closed=True,
                 mode='override', camera='Camera', scene='Scene')
    p.render_node(source_ids=[shot['id']]); operation = p.data['nodes'][-1]
    plan = operation['render_plan']; plan['folder_id'] = folder['id']
    plan['overrides'] = {'engine': 'CYCLES', 'samples': 1, 'width': 16, 'height': 16, 'percentage': 100, 'denoise': False, 'start': 1, 'end': 1}
    p.render_node_config(operation['id'], plan)
    return model, shot, operation, folder


def add_used_missing(p, base, model):
    script = base / 'missing-used.py'
    script.write_text('''import bpy,sys,os
from pathlib import Path
missing=Path(sys.argv[sys.argv.index('--')+1])
image=bpy.data.images.new('Missing roughness',width=2,height=2)
image.source='FILE';image.filepath='//'+os.path.relpath(missing,Path(bpy.data.filepath).parent)
tree=bpy.data.materials['Green material'].node_tree
node=tree.nodes.new('ShaderNodeTexImage');node.image=image
tree.links.new(node.outputs['Color'],tree.nodes.get('Principled BSDF').inputs['Roughness'])
bpy.context.preferences.filepaths.save_version=0
bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)
''', encoding='utf-8')
    p.run(str(script), [base / 'Textures/roughness.png'], p.path(model)); p.refresh()


def run_queue(p, require_complete=True):
    worker = threading.Thread(target=p._queue_loop, args=(p.data['id'],), daemon=True)
    p.queue_worker = worker; worker.start()
    deadline = time.monotonic() + 90
    while p.render_busy() and time.monotonic() < deadline: time.sleep(.2)
    if require_complete: assert p.data['render_queue'][-1]['status'] == 'Complete', p.data['render_queue']
    else: assert p.data['render_queue'][-1]['status'] in {'Complete', 'Failed'}, p.data['render_queue']
    return p.data['renders'][-1]


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='image-warning-test-') as temporary:
        base = Path(temporary); (base / 'settings').mkdir()
        p = Pipeline(data_directory=base / 'settings')
        model, shot, operation, folder = prepare_fixture(p, base)
        hashes = {n['id']: digest(p.path(n)) for n in (model, shot)}
        p.queue_worker = object()
        p.queue_render_node(operation['id'])
        queued = p.data['render_queue'][-1]
        assert not queued['dependency_warnings'], queued
        assert len(queued['image_notices']) == 1 and 'unused_ALPHA' in queued['image_notices'][0]['path'], queued
        green = base / 'Textures/green.png'; content = green.read_bytes()
        native_popen = subprocess.Popen
        def start_process(command, *args, **kwargs):
            if any('render_job.py' in str(item) for item in command):
                job = json.loads(Path(command[-1]).read_text(encoding='utf-8'))
                assert all((Path(job['input_root']) / image['target']).is_file() for image in job['image_inputs'])
                green.unlink()  # It must render correctly using the collected copy.
            return native_popen(command, *args, **kwargs)
        with patch('blender_pipeline.project.workspace.subprocess.Popen', side_effect=start_process): run = run_queue(p)
        green.write_bytes(content)
        assert not run['dependency_warnings'] and len(run['image_notices']) == 1
        log = (p.root / run['log']).read_text(encoding='utf-8', errors='replace')
        restored = json.loads(next(line.split('PIPELINE_IMAGE_WARNINGS ',1)[1] for line in log.splitlines() if 'PIPELINE_IMAGE_WARNINGS ' in line))
        assert {Path(i['path']).name for i in restored} == {'unused_ALPHA.png'}, restored
        collected = json.loads(next(line.split('PIPELINE_IMAGE_INPUTS ',1)[1] for line in log.splitlines() if 'PIPELINE_IMAGE_INPUTS ' in line))
        assert len(collected) == 1 and Path(collected[0]['snapshot']).is_relative_to(p.root / run['inputs']), collected
        image = next((p.root / run['output']).glob('*.png'))
        check = base / 'pixels.py'
        check.write_text('''import bpy,sys
sys.path.insert(0,__WORKERS__)
from render_resources import blender_file_path
image=bpy.data.images.load(blender_file_path(sys.argv[sys.argv.index('--')+1]))
pixels=list(image.pixels);i=(8*image.size[0]+8)*4
assert pixels[i+1]>pixels[i]+.05 and pixels[i+1]>pixels[i+2]+.05,pixels[i:i+4]
print('PASS: linked external texture renders green',flush=True)
'''.replace('__WORKERS__',repr(str(WORKERS))), encoding='utf-8')
        p.run(str(check), [image])
        assert all(digest(p.path(n)) == hashes[n['id']] for n in (model, shot))
        assert not p.state()['health']['outputs']['renders'][run['id']]['unverified_inputs']
        add_used_missing(p, base, model)
        hashes = {n['id']: digest(p.path(n)) for n in (model, shot)}
        p.queue_worker = object()
        try: p.queue_render_node(operation['id']); raise AssertionError('Used missing image was ignored')
        except RenderImageWarnings as warning: warnings = warning.dependency_warnings
        assert len(warnings) == 1 and warnings[0]['usage'] == 'used' and 'roughness.png' in warnings[0]['path'], warnings
        p.queue_render_node(operation['id'], allow_image_warnings=True, accepted_image_warnings=warnings)
        warned_run = run_queue(p, require_complete=False)
        assert len(warned_run['dependency_warnings']) == 1
        if warned_run['status'] == 'Failed': assert 'roughness.png' in warned_run['error'], warned_run['error']
        try: p.queue_render_node(operation['id']); raise AssertionError('Consent became a global ignore')
        except RenderImageWarnings: pass
        p.locate_render_image(warnings[0]['source_id'], warnings[0]['path'], str(green))
        p.queue_worker = object(); p.queue_render_node(operation['id'])
        fixed_run = run_queue(p)
        assert not fixed_run['dependency_warnings'] and any(i['replacement'] for i in fixed_run['image_inputs'])
        assert all(digest(p.path(n)) == hashes[n['id']] for n in (model, shot))
        # Ordinary project-relative images reuse the normal frozen file once.
        local = p.root / 'local.png'; local.write_bytes(content)
        script = base / 'local-image.py'
        script.write_text("import bpy\nbpy.data.images['External green'].filepath='//local.png'\nbpy.context.preferences.filepaths.save_version=0\nbpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)\n",encoding='utf-8')
        p.run(str(script), [], p.path(model));p.refresh();p.queue_worker=object()
        p.queue_render_node(operation['id']);local_run=run_queue(p)
        assert any(i['managed'] and i['target']=='local.png' for i in local_run['image_inputs'])
        assert (p.root/local_run['inputs']/'local.png').read_bytes()==content
    print('PASS: collected linked textures after original deletion, unused notices, used-image review, locate replacement, immutable sources and per-submission consent')
