"""Real layer isolation, compositor safety, stills, versions and unchanged sources."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import time

from blender_pipeline.project.workspace import Pipeline
from blender_pipeline.project.model import digest
from support import FIXTURES


def wait(p):
    deadline = time.monotonic() + 100
    while p.render_busy() and time.monotonic() < deadline:
        time.sleep(.2)
    assert not p.render_busy(), p.data['render_queue']
    assert all(q['status'] == 'Complete' for q in p.data['render_queue']), p.data['render_queue']


with tempfile.TemporaryDirectory(prefix='render-setups-') as temporary:
    base = Path(temporary)
    settings = base / 'settings'
    settings.mkdir()
    p = Pipeline(data_directory=settings)
    p.create(base, 'Layer tests')
    p.folder('Outputs')
    folder = p.data['nodes'][-1]
    p.create_blend('Shot', template_id='')
    source = p.data['nodes'][-1]
    p.runtime.run(p.blender, str(FIXTURES / 'render_setups_fixture.py'), [str(p.path(source))])
    p.refresh(source['id'])
    original = digest(p.path(source))
    assert source['scan']['active_scene'] == 'Main'
    assert source['scan']['active_view_layer'] == 'Blue', source['scan']['active_view_layer']
    main = next(s for s in source['scan']['scenes'] if s['name'] == 'Main')
    assert {d['view_layer'] for d in main['compositor_dependencies']} == {'Red', 'Blue'}
    assert {d['scene'] for d in main['compositor_dependencies']} == {'Main'}  # Ignore unused group nodes.
    p.render_node(source_ids=[source['id']])
    operation = p.data['nodes'][-1]
    assert operation['render_plan']['targets'][0]['view_layer'] == 'Blue'
    plan = copy.deepcopy(operation['render_plan'])
    plan['folder_id'] = folder['id']
    p.render_node_config(operation['id'], plan)
    p.queue_worker = object()
    try:
        p.queue_render_node(operation['id'])
        raise AssertionError('Cross-layer composite was silently accepted')
    except ValueError as error:
        assert 'Compositor needs Main / Red' in str(error), error
    assert not p.data.get('render_queue')
    seed = plan['targets'][0]
    plan['targets'] = [{**seed, 'id': scene+'-'+layer, 'scene': scene, 'view_layer': layer,
                        'compositor': 'OFF', 'overrides': {'width': 20} if scene == 'Main' else {}}
                       for scene in ['Main', 'Detail'] for layer in ['Red', 'Blue']]
    plan['overrides'] = {'samples': 2}
    p.render_node_config(operation['id'], plan)
    p.queue_render_node(operation['id'])
    worker = threading.Thread(target=p._queue_loop, args=(p.data['id'],), daemon=True)
    p.queue_worker = worker
    worker.start()
    wait(p)
    runs = p.data['renders']
    assert len(runs) == 4 and len({r['output'] for r in runs}) == 4
    assert len({r['worker_pid'] for r in runs}) == 1, 'One Blender worker should handle the batch'
    assert all(r.get('timing') for r in runs), 'Each setup reports load and render time'
    for run in runs:
        config, actual = run['config'], run['actual_settings']
        assert actual['view_layers'] == [config['view_layer']], actual
        assert not actual['use_compositing'] and not run['compositor_outputs']
        assert actual['samples'] == 2
        assert actual['layer_samples'] == {config['view_layer']: 2}
        assert actual['width'] == (20 if config['scene'] == 'Main' else 24)
        assert run['number'] == 1
        assert ('use_pass_z' if config['view_layer'] == 'Red' else 'use_pass_normal') in actual['passes']
        output = p.root / run['output']
        assert len(list(output.glob('*.png'))) == (2 if config['scene'] == 'Main' else 1)
        assert not (output / 'compositor').exists()
        assert output.parent.name == config['view_layer']
    # Verify rendered pixels, not just the requested settings in the log.
    checks = base / 'pixels.py'
    checks.write_text('''import bpy,json,sys
from pathlib import Path
for entry in json.loads(Path(sys.argv[sys.argv.index('--')+1]).read_text()):
    image=bpy.data.images.load(entry['path']);pixels=list(image.pixels)
    red=sum(pixels[0::4]);blue=sum(pixels[2::4])
    assert (red>blue*4) if entry['layer']=='Red' else (blue>red*4), (entry,red,blue)
print('PIXELS_OK')
''', encoding='utf-8')
    manifest = base / 'pixels.json'
    manifest.write_text(json.dumps([dict(path=str(next((p.root/r['output']).glob('*.png'))), layer=r['config']['view_layer']) for r in runs]), encoding='utf-8')
    p.runtime.run(p.blender, str(checks), [str(manifest)])
    # Render a single frame from one setup and a whole-scene composite together.
    plan = copy.deepcopy(operation['render_plan'])
    plan['targets'][0].update(mode='STILL', frame=2)
    plan['targets'].append({**seed, 'id': 'composite', 'view_layer': '', 'scene': 'Main', 'mode': 'STILL', 'frame': 2})
    p.render_node_config(operation['id'], plan)
    p.queue_render_node(operation['id'], target_ids=['Main-Red', 'composite'])
    wait(p)
    still, composite = p.data['renders'][-2:]
    assert still['number'] == 2 and composite['number'] == 1
    assert len(list((p.root/still['output']).glob('*.png'))) == 1
    assert next((p.root/still['output']).glob('*.png')).name.endswith('_0002.png')
    assert composite['actual_settings']['view_layers'] == ['Red', 'Blue']
    assert composite['actual_settings']['use_compositing']
    assert list((p.root/composite['output']/'compositor').glob('*.png'))
    assert not (p.root / 'NEVER_WRITE_HERE').exists()
    # Without an override, retain the Blender file's per-layer sampling choice.
    plan = copy.deepcopy(operation['render_plan'])
    plan['overrides'] = {}
    p.render_node_config(operation['id'], plan)
    p.queue_render_node(operation['id'], target_ids=['Main-Red'])
    wait(p)
    assert p.data['renders'][-1]['actual_settings']['layer_samples'] == {'Red': 7}
    # Removal and cleanup retain other versions and never alter the source.
    plan = copy.deepcopy(operation['render_plan'])
    plan['targets'] = [t for t in plan['targets'] if t['id'] != 'composite']
    p.render_node_config(operation['id'], plan)
    assert (p.root/composite['output']).exists()
    p.render_delete(still['id'], confirmed=True)
    assert not (p.root/still['output']).exists() and (p.root/runs[0]['output']).exists()
    assert digest(p.path(source)) == original
    print('PASS: saved active layer, 2 scenes × 2 layers, pixel-verified animation isolation, compositor preflight, still/composite output, per-setup versions, safe cleanup and unchanged Blender source', flush=True)
