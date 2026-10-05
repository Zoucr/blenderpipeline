"""Actual Blender exports with parenting/materials, hidden content and source integrity."""
import tempfile
from pathlib import Path
from blender_pipeline.project.workspace import Pipeline
from blender_pipeline.project.model import digest
from support import FIXTURES

with tempfile.TemporaryDirectory(prefix='pipeline-export-check-') as temporary:
    base = Path(temporary)
    p = Pipeline()
    p.registry = base / 'recent.json'
    p.global_template_config = base / 'startup.json'
    p.create(base, 'Export Test')
    p.frame('Work')
    frame = p.data['nodes'][-1]
    p.create_blend(folder_id=frame['id'], template_id='__factory__')
    source = p.data['nodes'][-1]
    assert source['group'] == frame['id'] and p.path(source).parent == p.root
    # Run fixtures through the real adapter without touching a user project.
    from blender_pipeline.adapters.blender_runtime import BlenderRuntime
    BlenderRuntime(FIXTURES).run(p.blender, 'export_fixture.py', [p.path(source)])
    p.refresh(source['id'])
    original = digest(p.path(source))
    p.folder('Exports')
    folder = p.data['nodes'][-1]
    p.export_node(source_id=source['id'])
    export = p.data['nodes'][-1]
    presets = {'GLB': {'export_force_sampling': True, 'export_frame_step': 1},
               'FBX': {'global_scale': 2, 'use_triangles': True, 'bake_anim_simplify_factor': 0},
               'USD': {'triangulate_meshes': True},
               'ALEMBIC': {'face_sets': True, 'xsamples': 2, 'gsamples': 2, 'sh_close': .5}}
    for format in ('GLB', 'FBX', 'USD', 'ALEMBIC'):
        p.export_config(export['id'], {**export['export_config'], 'folder_id': folder['id'],
            'scene': source['scan']['scenes'][0]['name'], 'format': format,
            'scope': 'COLLECTIONS', 'collections': ['Product'], 'animation': True, 'start': 2, 'end': 3,
            'options': presets})
        p.export_start(export['id'])
        run = p.data['exports'][-1]
        assert run['status'] == 'Complete' and run['bytes'] > 0, run
        assert digest(p.path(source)) == original
        assert run['timing']['start'] == 2 and run['timing']['end'] == 3 and run['timing']['frames'] == 2, run
        assert all(run['format_options'][k] == v for k, v in presets[format].items())
        if format in ('GLB', 'FBX'):
            script = base / 'read_export.py'
            script.write_text("import bpy,sys\nbpy.ops.object.select_all(action='SELECT')\nbpy.ops.object.delete(use_global=False)\n"
                + ("bpy.ops.import_scene.gltf(filepath=sys.argv[-1])\n" if format == 'GLB' else "bpy.ops.import_scene.fbx(filepath=sys.argv[-1])\n")
                + "objects=list(bpy.context.scene.objects)\nassert any(o.name.startswith('Part 1') for o in objects)\n"
                + "assert not any(o.name.startswith('Outside Product') for o in objects)\n"
                + "assert any(o.type=='MESH' and o.data.materials for o in objects)\n"
                + "assert any(o.parent for o in objects), 'Parent hierarchy missing'\n", encoding='utf-8')
            BlenderRuntime(base).run(p.blender, script.name, [p.root / run['output'] / run['file']])
        elif format == 'ALEMBIC':
            script = base / 'read_cache.py'
            script.write_text("import bpy,sys\nbpy.ops.object.select_all(action='SELECT')\nbpy.ops.object.delete(use_global=False)\n"
                + "bpy.ops.wm.alembic_import(filepath=sys.argv[-1],set_frame_range=True,as_background_job=False)\n"
                + "scene=bpy.context.scene\nassert (scene.frame_start,scene.frame_end)==(2,3), (scene.frame_start,scene.frame_end)\n"
                + "objects=list(scene.objects)\nassert not any(o.name.startswith('Outside Product') for o in objects)\n"
                + "part=next(o for o in objects if o.type=='MESH' and o.name.startswith('Part_1'))\n"
                + "assert part.data.materials, 'Alembic face sets missing'\n"
                + "scene.frame_set(2)\nz2=part.matrix_world.translation.z\nscene.frame_set(3)\nz3=part.matrix_world.translation.z\n"
                + "assert z3>z2+.1, (z2,z3)\n", encoding='utf-8')
            BlenderRuntime(base).run(p.blender, script.name, [p.root / run['output'] / run['file']])
    p.export_config(export['id'], {**export['export_config'], 'animation': False})
    p.export_start(export['id'])
    still = p.data['exports'][-1]
    assert still['timing']['start'] == still['timing']['end'] == 2
    assert still['format_options']['xsamples'] == still['format_options']['gsamples'] == 1
    script.write_text("import bpy,sys\nbpy.ops.wm.alembic_import(filepath=sys.argv[-1],set_frame_range=True,as_background_job=False)\n"
        + "part=next(o for o in bpy.context.scene.objects if o.type=='MESH' and o.name.startswith('Part_1'))\n"
        + "bpy.context.scene.frame_set(2)\nz2=part.matrix_world.translation.z\nassert .1<z2<.9, z2\n"
        + "bpy.context.scene.frame_set(3)\nassert abs(part.matrix_world.translation.z-z2)<.00001\n", encoding='utf-8')
    BlenderRuntime(base).run(p.blender, script.name, [p.root / still['output'] / still['file']])
    assert digest(p.path(source)) == original
    assert len({r['output'] for r in p.data['exports']}) == 5
    assert not list((p.root / '.pipeline').glob('export-*'))
    q = Pipeline()
    q.registry = base / 'second-recent.json'
    q.global_template_config = base / 'startup.json'
    q.load(p.root)
    assert q.node(export['id'])['type'] == 'export' and len(q.data['exports']) == 5
    print('PASS: four export formats with custom options; Alembic reimported range 2-3, animated transforms, face sets and saved-current-frame export; collection scope, hidden nested objects, parenting/materials, versions, cleanup and unchanged source')
