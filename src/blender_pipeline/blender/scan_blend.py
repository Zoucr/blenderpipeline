"""Executed by Blender, never saves the source file."""
import bpy, json, sys, os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from blender_linking import KINDS
from blender_render_settings import catalog

destination = sys.argv[sys.argv.index('--') + 1]
refs = []
def add(raw, kind, library=None, name='', sequence=False):
    if not raw:
        return
    resolved = bpy.path.abspath(raw, library=library)
    refs.append(dict(raw=raw, path=os.path.abspath(resolved), kind=kind,
                     name=name, relative=raw.startswith('//'),
                     exists=os.path.exists(resolved),
                     pattern=(sequence or '<UDIM>' in raw or '#' in raw)))
for lib in bpy.data.libraries:
    # Library.filepath is resolved against the opened main file, including indirect libraries.
    add(lib.filepath, 'Library', None, lib.name)
for image in bpy.data.images:
    if image.source in {'FILE', 'TILED', 'SEQUENCE'} and not image.packed_file:
        add(image.filepath, 'Image', image.library, image.name, image.source in {'TILED', 'SEQUENCE'})
for group, kind in [(bpy.data.movieclips, 'Movie'), (bpy.data.sounds, 'Sound'),
                    (bpy.data.fonts, 'Font'), (bpy.data.cache_files, 'Cache'),
                    (bpy.data.volumes, 'Volume')]:
    for item in group:
        if not getattr(item, 'packed_file', None) and item.filepath != '<builtin>':
            add(item.filepath, kind, item.library, item.name, getattr(item, 'is_sequence', False))
known = {r['path'] for r in refs}
weak_paths={os.path.normcase(os.path.abspath(bpy.path.abspath(item.library_weak_reference.filepath)))
    for item in bpy.data.all_ids if item.library_weak_reference}
for path in bpy.utils.blend_paths(absolute=True, packed=False, local=False):
    if os.path.abspath(path) not in known and os.path.normcase(os.path.abspath(path)) not in weak_paths:
        add(path, 'External')
instances = [dict(collection=o.instance_collection.name,
    source=os.path.abspath(bpy.path.abspath(o.instance_collection.library.filepath)), object=o.name)
    for o in bpy.data.objects if o.instance_type == 'COLLECTION' and o.instance_collection and o.instance_collection.library]
instances += [dict(collection=c.name, source=os.path.abspath(bpy.path.abspath(c.library.filepath)),
    object='', direct=True,mode='collection') for c in bpy.context.scene.collection.children_recursive if c.library]
instances += [dict(collection=c.override_library.reference.name,source=os.path.abspath(bpy.path.abspath(c.override_library.reference.library.filepath)),
    object='',direct=True,mode='override') for c in bpy.context.scene.collection.children_recursive
    if c.override_library and c.override_library.reference.library and c.override_library.hierarchy_root==c]
details = [dict(name=c.name, objects=len(c.all_objects), direct_objects=len(c.objects),
    children=[child.name for child in c.children], members=[o.name for o in c.all_objects], parents=[parent.name for parent in bpy.data.collections if c in list(parent.children)],
    scene_names=[s.name for s in bpy.data.scenes if c in list(s.collection.children_recursive)],
    hidden=c.hide_viewport or c.hide_render,cameras=[o.name for o in c.all_objects if o.type=='CAMERA'],
    override=bool(c.override_library)) for c in bpy.data.collections if not c.library and not c.get('pipeline_reference_holder')]
roots=[]
for scene in bpy.data.scenes:
    objects=[o.name for o in scene.collection.objects if not o.get('pipeline_datablock') and not (o.instance_type=='COLLECTION' and o.instance_collection and o.instance_collection.library)]
    if objects:roots.append(dict(scene=scene.name,objects=objects))
Path(destination).write_text(json.dumps(dict(version=bpy.app.version_string,
    refs=refs, collections=[c['name'] for c in details],
    datablocks=[dict(kind=kind,name=item.name,tree_type=getattr(item,'bl_idname',''),users=item.users,
        object_type=getattr(item,'type','') if kind=='objects' else '',data_name=getattr(getattr(item,'data',None),'name','') if kind=='objects' else '',
        material_slot_count=len(item.material_slots) if kind=='objects' else None)
        for kind in KINDS for item in getattr(bpy.data,kind,[]) if not item.library and not (kind=='objects' and item.get('pipeline_datablock'))],
    data_links=[dict(kind=o['pipeline_kind'],name=r.name,source=os.path.abspath(bpy.path.abspath(r.library.filepath)),usage=o.get('pipeline_usage','keep'))
        for o in bpy.data.objects if (d:=o.get('pipeline_datablock')) and (r:=d.override_library.reference if d.override_library else d).library],
    objects=[dict(name=o.name,type=o.type,editable=not bool(o.library),scenes=[s.name for s in bpy.data.scenes if o in list(s.objects)],
        source=os.path.abspath(bpy.path.abspath(o.library.filepath)) if o.library else '',
        reference=o.override_library.reference.name if o.override_library else '',
        reference_slots=len(o.override_library.reference.material_slots) if o.override_library else None,
        material_slots=[dict(link=s.link,material=s.material.name if s.material else '') for s in o.material_slots]) for o in bpy.data.objects if not o.get('pipeline_datablock')],
    collection_details=details, root_objects=roots,
    overrides=[dict(name=o.name,reference=o.override_library.reference.name,
        source=os.path.abspath(bpy.path.abspath(o.override_library.reference.library.filepath)),
        system=o.override_library.is_system_override,properties=[p.rna_path for p in o.override_library.properties],
        action=o.animation_data.action.name if o.animation_data and o.animation_data.action else '')
        for o in bpy.data.objects if o.override_library and o.override_library.reference.library],
    scenes=[dict(name=s.name,linked=bool(s.library),cameras=[o.name for o in s.objects if o.type=='CAMERA'],
        camera=s.camera.name if s.camera else '',start=s.frame_start,end=s.frame_end,
        width=s.render.resolution_x,height=s.render.resolution_y,percentage=s.render.resolution_percentage,engine=s.render.engine,
        samples=s.cycles.samples if s.render.engine=='CYCLES' else getattr(getattr(s,'eevee',None),'taa_render_samples',64),
        denoise=s.cycles.use_denoising,format=s.render.image_settings.file_format,
        fps=s.render.fps/s.render.fps_base,advanced_settings=catalog(s),passes=[p.identifier for p in s.view_layers[0].bl_rna.properties if p.identifier.startswith('use_pass_') and getattr(s.view_layers[0],p.identifier,False)]) for s in bpy.data.scenes],
    instances=instances, file=bpy.data.filepath), indent=2), encoding='utf-8')
