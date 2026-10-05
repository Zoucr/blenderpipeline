"""Render-node batches with multiple saved scenes and output freshness."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import time

from blender_pipeline.project.workspace import Pipeline
from blender_pipeline.project.model import digest


with tempfile.TemporaryDirectory(prefix='render-graph-') as temporary:
    base = Path(temporary)
    settings = base / 'settings'
    settings.mkdir()
    p = Pipeline(data_directory=settings)
    p.create(base, 'Render graph')
    p.folder('Outputs')
    output = p.data['nodes'][-1]
    for title in ['Shot A', 'Shot B']:
        p.create_blend(title, template_id='')
        n = p.data['nodes'][-1]
        fixture = base / 'setup.py'
        fixture.write_text('''import bpy
bpy.ops.wm.read_factory_settings(use_empty=False)
s=bpy.context.scene;s.name='Main';s.render.engine='CYCLES';s.cycles.device='CPU';s.cycles.samples=1;s.cycles.use_denoising=False
s.render.resolution_x=16;s.render.resolution_y=16;s.render.resolution_percentage=100;s.frame_start=1;s.frame_end=2
bpy.context.preferences.filepaths.save_version=0
other=s.copy();other.name='Detail';other.use_fake_user=True;other.frame_start=4;other.frame_end=4;other.render.resolution_x=24
bpy.ops.wm.save_as_mainfile(filepath=TARGET)
'''.replace('TARGET', repr(str(p.path(n)))), encoding='utf-8')
        # run() uses the same production Blender adapter, with --disable-autoexec.
        p.runtime.run(p.blender, str(fixture), [])
        p.refresh(n['id'])
    a, b = [n for n in p.data['nodes'] if n['type'] == 'blend']
    hashes = {n['id']: digest(p.path(n)) for n in [a, b]}
    p.render_node(source_ids=[a['id'], b['id']])
    operation = p.data['nodes'][-1]
    plan = copy.deepcopy(operation['render_plan'])
    plan['folder_id'] = output['id']
    for target in plan['targets']:
        target['scene'] = 'Main'
    plan['targets'][0]['overrides'] = {'width': 20}
    plan['targets'].append({**plan['targets'][0], 'id': 'detail', 'scene': 'Detail', 'overrides': {}})
    plan['overrides'] = {'samples': 2}
    p.render_node_config(operation['id'], plan)
    plan = copy.deepcopy(operation['render_plan'])
    p.queue_worker = object()
    p.queue_render_node(operation['id'])
    jobs = p.data['render_queue']
    assert len(jobs) == 3 and len({q['target_key'] for q in jobs}) == 3
    worker = threading.Thread(target=p._queue_loop, args=(p.data['id'],), daemon=True)
    p.queue_worker = worker
    worker.start()
    deadline = time.monotonic() + 100
    while p.render_busy() and time.monotonic() < deadline:
        time.sleep(.2)
    assert all(q['status'] == 'Complete' for q in jobs), jobs
    runs = p.data['renders']
    assert len(runs) == 3
    assert len({r['output'] for r in runs}) == 3
    for run in runs:
        assert run['operation_id'] == operation['id']
        path = p.root / run['output']
        expected_width = 24 if run['config']['scene'] == 'Detail' else 20 if run['node_id'] == a['id'] else 16
        assert run['actual_settings']['width'] == expected_width, run['actual_settings']
        assert run['actual_settings']['samples'] == 2
        assert len(list(path.glob('*.png'))) == (1 if run['config']['scene'] == 'Detail' else 2)
        assert path.parent.name == run['config']['view_layer']
        assert run['input_signatures'] and not p.state()['health']['outputs']['renders'][run['id']]['outdated']
        assert all(f.name.startswith(run['config']['prefix']) for f in path.glob('*.png'))
    assert all(digest(p.path(n)) == hashes[n['id']] for n in [a, b])
    # Re-rendering reserves a new version without overwriting the first.
    first = runs[0]
    p.queue_render_node(operation['id'], target_ids=[first['target_id']])
    deadline = time.monotonic() + 70
    while p.render_busy() and time.monotonic() < deadline:
        time.sleep(.2)
    last = p.data['renders'][-1]
    assert last['status'] == 'Complete' and last['output'] != first['output'], last
    assert (p.root / first['output']).exists()
    # Save an edited scene through Blender, then refresh the changed file.
    edit = base / 'edit.py'
    edit.write_text('import bpy\nbpy.data.scenes["Main"].render.resolution_x=32\nbpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)', encoding='utf-8')
    p.runtime.run(p.blender, str(edit), [], p.path(a))
    p.refresh(a['id'])
    health = p.state()['health']['outputs']['renders']
    assert health[last['id']]['outdated']
    assert not health[next(r['id'] for r in runs if r['node_id'] == b['id'])]['outdated']
    assert not a.get('render_config') and operation['render_plan'] == plan
    # Actual linked-library scans must preserve pending updates on unchanged files.
    p.link(a['id'], b['id'], 'Collection', True)
    baseline = b['dependency_hashes'][a['id']]
    edit.write_text('import bpy\nbpy.data.collections["Collection"].name="Models Renamed"\nbpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)', encoding='utf-8')
    p.runtime.run(p.blender, str(edit), [], p.path(a))
    p.refresh(a['id'])
    reasons = p.state()['health']['nodes'][b['id']]['reasons']
    assert {'source_updated', 'asset_missing'} <= {r['kind'] for r in reasons}, reasons
    p.refresh(b['id'])
    assert b['dependency_hashes'][a['id']] == baseline
    assert {'source_updated', 'asset_missing'} <= {r['kind'] for r in p.state()['health']['nodes'][b['id']]['reasons']}
    print('PASS: real multi-file/multi-scene render nodes, selective per-scene and shared settings, isolated version directories, unchanged inputs and saved-source output freshness', flush=True)
