import bpy, json, sys
from pathlib import Path

job = json.loads(Path(sys.argv[sys.argv.index('--')+1]).read_text(encoding='utf-8'))
action = job['action']
sys.path.insert(0,str(Path(__file__).parent))
from blender_linking import prepare_material_slots
if action == 'create':
    if job.get('template'):
        bpy.ops.wm.open_mainfile(filepath=job['template'])
    else:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        collection = bpy.data.collections.new('Collection')
        bpy.context.scene.collection.children.link(collection)
        bpy.context.view_layer.active_layer_collection = bpy.context.view_layer.layer_collection.children[collection.name]
    prepare_material_slots(strict=False)
elif action=='prepare_materials':
    bpy.ops.wm.open_mainfile(filepath=job['target'])
    if job.get('reload'):
        for library in list(bpy.data.libraries):
            if not library.parent:library.reload()
    prepare_material_slots(job.get('objects'),strict=job.get('strict',True),required_slots=job.get('required_slots'))
elif action == 'organize':
    bpy.ops.wm.open_mainfile(filepath=job['target'])
    for scene in bpy.data.scenes:
        objects=[o for o in scene.collection.objects if not (o.instance_type=='COLLECTION' and o.instance_collection and o.instance_collection.library)]
        if not objects: continue
        collection=bpy.data.collections.new(job['collection'])
        scene.collection.children.link(collection)
        for obj in objects:
            collection.objects.link(obj)
            scene.collection.objects.unlink(obj)
        for layer in scene.view_layers:
            layer.active_layer_collection=layer.layer_collection.children[collection.name]
elif action == 'link_batch':
    import hashlib
    def source_hash():return hashlib.sha256(Path(job['source']).read_bytes()).hexdigest()
    if source_hash()!=job['source_hash']:raise ValueError('Source changed; refresh and select again')
    bpy.ops.wm.open_mainfile(filepath=job['target'])
    sys.path.insert(0,str(Path(__file__).parent))
    from blender_linking import link_batch
    link_batch(job['source'],job['items'],job.get('mode','override'),job.get('scene',''),job.get('camera',''))
    if source_hash()!=job['source_hash']:raise ValueError('Source changed during linking; save it and retry')
elif action == 'link':
    bpy.ops.wm.open_mainfile(filepath=job['target'])
    sys.path.insert(0,str(Path(__file__).parent))
    from blender_linking import link_collection
    link_collection(job['source'],job['collection'],job.get('mode','instance'),job.get('scene',''),job.get('camera',''))
elif action == 'repair_paths':
    import os
    bpy.ops.wm.open_mainfile(filepath=job['target'])
    aliases=job.get('aliases') or {job['old']:job['new']}
    aliases={str(Path(old).resolve()).casefold():new for old,new in aliases.items()}
    for old,new in list(aliases.items()):
        seen={old}
        while str(Path(new).resolve()).casefold() in aliases and str(Path(new).resolve()).casefold() not in seen:
            key=str(Path(new).resolve()).casefold();seen.add(key);new=aliases[key]
        aliases[old]=new
    for library in bpy.data.libraries:
        old=str(Path(bpy.path.abspath(library.filepath)).resolve()).casefold()
        if not library.parent and old in aliases:
            library.filepath='//'+os.path.relpath(aliases[old],str(Path(job['output']).parent))
    if job.get('reload'):
        for library in list(bpy.data.libraries):
            if not library.parent:library.reload()
        for library in bpy.data.libraries:
            absolute=bpy.path.abspath(library.filepath)
            library.filepath='//'+os.path.relpath(absolute,str(Path(job['output']).parent))
elif action == 'reload_libraries':
    bpy.ops.wm.open_mainfile(filepath=job['target'])
    for library in list(bpy.data.libraries):
        if not library.parent:library.reload()
elif action in {'link_data','unlink_data'}:
    bpy.ops.wm.open_mainfile(filepath=job['target'])
    sys.path.insert(0,str(Path(__file__).parent))
    from blender_linking import link_datablock,unlink_datablock
    if action=='unlink_data':unlink_datablock(job['source'],job['kind'],job['item'])
    else:link_datablock(job['source'],job['kind'],job['item'],job.get('apply','keep'),job.get('object_name',''),job.get('scene',''))
elif action == 'unlink':
    bpy.ops.wm.open_mainfile(filepath=job['target'])
    matches = [obj for obj in bpy.data.objects if obj.instance_type == 'COLLECTION'
               and obj.instance_collection and obj.instance_collection.library
               and str(Path(bpy.path.abspath(obj.instance_collection.library.filepath)).resolve()).casefold() == job['source'].casefold()
               and obj.instance_collection.name == job['collection']]
    if not matches: raise ValueError('No simple collection instance found. Edit this link in Blender.')
    for obj in matches: bpy.data.objects.remove(obj, do_unlink=True)
else:
    raise ValueError('Unknown Blender operation')
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=job['output'])
