"""Read-only Blend-to-file export worker. The working file is never saved."""
import json
import sys
from pathlib import Path
import bpy
sys.path.insert(0, str(Path(__file__).parent))
from export_settings import option_values, export_timing


def export(config, destination):
    scene = bpy.data.scenes.get(config['scene'])
    if not scene or scene.library:
        raise ValueError('The selected scene no longer exists in this file.')
    bpy.context.window.scene = scene
    objects = set(scene.objects)
    if config['scope'] == 'COLLECTIONS':
        selected = set()
        available = set()
        def visit(collection):
            available.add(collection)
            for child in collection.children:
                visit(child)
        visit(scene.collection)
        for collection_name in config['collections']:
            collection = bpy.data.collections.get(collection_name)
            if collection not in available:
                raise ValueError('Collection is not in the selected scene: ' + collection_name)
            selected.update(collection.all_objects)
        objects &= selected
    if not objects:
        raise ValueError('The selected content has no objects to export.')
    # Excluded/hidden collection objects still belong to the saved scene.
    layer = scene.view_layers.new('Pipeline Export')
    bpy.context.window.view_layer = layer
    def reveal(collection):
        collection.exclude = False
        collection.hide_viewport = False
        collection.collection.hide_viewport = False
        for child in collection.children:
            reveal(child)
    reveal(layer.layer_collection)
    for obj in scene.objects:
        obj.hide_viewport = False
        obj.hide_set(False, view_layer=layer)
        obj.select_set(obj in objects, view_layer=layer)
    layer.objects.active = next(iter(objects))
    animation = config['animation']
    timing = export_timing(config, {'start': scene.frame_start, 'end': scene.frame_end,
                                   'current_frame': scene.frame_current, 'fps': scene.render.fps / scene.render.fps_base})
    first, last = timing['start'], timing['end']
    if animation:
        scene.frame_start, scene.frame_end = first, last
    filepath = str(destination)
    mode = config['format']
    options = option_values(mode, config.get('options', {}), animation=animation)
    if mode == 'FBX':
        result = bpy.ops.export_scene.fbx(filepath=filepath, use_selection=True, bake_anim=animation,
                                        bake_anim_use_all_actions=False, bake_anim_use_nla_strips=False,
                                        path_mode='COPY', embed_textures=True, **options)
    elif mode == 'GLB':
        result = bpy.ops.export_scene.gltf(filepath=filepath, export_format='GLB', use_selection=True,
                                         export_animations=animation, export_frame_range=True, **options)
    elif mode == 'USD':
        scene.frame_start, scene.frame_end = first, last
        properties = bpy.ops.wm.usd_export.get_rna_type().properties
        textures = ({'export_textures_mode': 'NEW'} if 'export_textures_mode' in properties else {'export_textures': True}) if options['export_materials'] else {}
        result = bpy.ops.wm.usd_export(filepath=filepath, selected_objects_only=True,
                                       export_animation=animation, **textures, **options)
    elif mode == 'ALEMBIC':
        result = bpy.ops.wm.alembic_export(filepath=filepath, selected=True, start=first, end=last,
                                           as_background_job=False, init_scene_frame_range=False, **options)
    else:
        raise ValueError('Unsupported export format.')
    if 'FINISHED' not in result:
        raise ValueError('Blender cancelled the export.')
    print('PIPELINE_EXPORT_TIMING', json.dumps(timing), flush=True)
    print('PIPELINE_EXPORT_COMPLETE', filepath, flush=True)


if __name__ == '__main__':
    settings, destination = sys.argv[sys.argv.index('--') + 1:]
    export(json.loads(Path(settings).read_text(encoding='utf-8')), Path(destination))
