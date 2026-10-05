"""Verify real Blender material inheritance without selecting materials separately."""
from pathlib import Path
import tempfile

from blender_pipeline.bootstrap import create_application
from support import FIXTURES


with tempfile.TemporaryDirectory(prefix='collection-materials-') as directory:
    root = Path(directory)
    app = create_application(root / 'settings')
    try:
        model = app.model
        model.create(root, 'Materials Test')
        model.run(FIXTURES / 'collection_materials_fixture.py', [model.root])
        model.import_blend(model.root / 'Source.blend')
        source = model.data['nodes'][-1]
        asset = next(c for c in source['scan']['collection_details'] if c['name'] == 'Asset')
        assert asset['direct_members'] == ['Root Empty']
        assert next(o for o in source['scan']['objects'] if o['name'] == 'Part_1')['parent'] == 'Child Empty'
        model.create_blend('Pipeline Shot')
        shot = model.data['nodes'][-1]
        model.link_batch(source['id'], shot['id'], [{'kind': 'collections', 'name': 'Asset'}],
                         closed=True, mode='override')
        # The graph command inspects the saved result in another Blender process.
        meshes = [obj for obj in shot['scan']['objects'] if obj.get('reference', '').startswith('Part_')]
        assert len(meshes) == 24, meshes
        for obj in meshes:
            index = int(obj['reference'].split('_')[-1])
            expected = ['Clear' if index % 3 == 0 else 'Copper', '', 'Rubber V2']
            assert [slot['material'] for slot in obj['material_slots']] == expected, obj
        assert len(shot['snapshots']) == 1 and not source['snapshots']
        assert any(c['linked'] for c in shot['scan']['content_collections'])
        print('PASS: collection/object materials survive save, reopen, source updates and local replacements; actual graph command includes materials automatically with one destination snapshot and no source edits')
    finally:
        app.tasks.pool.shutdown()
