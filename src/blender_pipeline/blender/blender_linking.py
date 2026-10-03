"""Shared Blender-side collection linking, used by background jobs and companion."""
import bpy
from pathlib import Path
KINDS=('actions','annotations','armatures','brushes','cache_files','cameras','curves','fonts','grease_pencils','hair_curves','images','lattices','lightprobes','lights','linestyles','masks','materials','meshes','metaballs','movieclips','node_groups','objects','paint_curves','palettes','particles','pointclouds','scenes','sounds','speakers','texts','textures','volumes','worlds')

def prepare_material_slots(objects=None,strict=True,required_slots=None):
    """A native override needs slots in its reference; store assignments on the object."""
    changed=0;missing=[]
    for obj in list(bpy.data.objects):
        if objects is not None and obj.name not in objects:continue
        if obj.library or not hasattr(obj.data,'materials'):continue
        reference=obj.override_library.reference if obj.override_library else None
        if reference:
            if not obj.material_slots:continue
            if len(obj.material_slots)>len(reference.material_slots) or not reference.material_slots:
                missing.append(obj.name);continue
            if obj.override_library.is_system_override:continue
            for slot in obj.material_slots:
                if slot.link=='OBJECT':continue
                material=slot.material;slot.link='OBJECT';slot.material=material;changed+=1
        elif not obj.data.library and not obj.data.override_library:
            needed=max(1,(required_slots or {}).get(obj.name,1))
            while len(obj.material_slots)<needed:obj.data.materials.append(None);changed+=1
    if missing and strict:raise ValueError('Prepare material slots in the source file before assigning materials to: '+', '.join(missing)+'. The source needs one slot for each destination slot.')
    return changed,missing

def link_datablock(source,kind,item,apply='keep',object_name='',scene_name='',_linked=None):
    source=str(Path(source).resolve())
    if bpy.data.filepath and Path(bpy.data.filepath).resolve()==Path(source):raise ValueError('Cannot link this file into itself')
    if kind not in KINDS:raise ValueError('Unsupported datablock type')
    scene=bpy.data.scenes.get(scene_name) if scene_name else bpy.context.scene
    if not scene:raise ValueError('Destination scene not found')
    if _linked is None:
        with bpy.data.libraries.load(source,link=True,relative=True) as (src,dst):
            if item not in getattr(src,kind,[]):raise ValueError('Datablock not found; refresh source')
            setattr(dst,kind,[item])
        linked=getattr(dst,kind)[0]
    else:linked=_linked
    if not linked:raise ValueError('Blender could not link that datablock')
    target=bpy.data.objects.get(object_name) if object_name else None
    if apply in {'material','modifier','shader','animation'}:
        if not target or target not in list(scene.objects) or target.library:raise ValueError('Choose an editable object in the destination scene')
    if apply=='material':
        if kind!='materials' or not hasattr(target.data,'materials'):raise ValueError('Material assignment requires a material and an object with material slots')
        if target.override_library and not target.override_library.reference.material_slots:raise ValueError('Prepare source material slots first so this assignment survives reopening')
        if not target.material_slots:
            if target.data.library or target.data.override_library:raise ValueError('Linked mesh has no material slot; prepare the source first')
            target.data.materials.append(None)
        target.material_slots[0].link='OBJECT';target.material_slots[0].material=linked
    elif apply=='modifier':
        if kind!='node_groups' or linked.bl_idname!='GeometryNodeTree':raise ValueError('Choose a Geometry Nodes group')
        modifier=target.modifiers.new(item,'NODES');modifier.node_group=linked
    elif apply=='shader':
        if kind!='node_groups' or linked.bl_idname!='ShaderNodeTree':raise ValueError('Choose a shader node group')
        mat=bpy.data.materials.new(item+' Setup');mat.use_nodes=True
        group=mat.node_tree.nodes.new('ShaderNodeGroup');group.node_tree=linked
        output=mat.node_tree.nodes.get('Material Output');shader=next((s for s in group.outputs if s.type=='SHADER'),None)
        if shader:mat.node_tree.links.new(shader,output.inputs['Surface'])
        if not target.material_slots:
            if target.data.library or target.data.override_library:raise ValueError('Prepare a material slot in the source first')
            target.data.materials.append(None)
        target.material_slots[0].link='OBJECT';target.material_slots[0].material=mat
    elif apply=='world':
        if kind!='worlds':raise ValueError('Choose a world datablock')
        scene.world=linked
    elif apply=='animation':
        if kind!='actions':raise ValueError('Choose an action')
        target.animation_data_create();target.animation_data.action=linked
        slots=getattr(linked,'slots',[])
        slot=next((s for s in slots if s.target_id_type==target.id_type),None)
        if slot:target.animation_data.action_slot=slot
    elif apply=='object':
        if kind!='objects':raise ValueError('Choose an object')
        if linked not in list(scene.collection.objects):scene.collection.objects.link(linked)
    elif apply!='keep':raise ValueError('Unknown datablock usage')
    holders=next((c for c in bpy.data.collections if c.get('pipeline_reference_holder')),None)
    if not holders:
        holders=bpy.data.collections.new('Pipeline References');holders['pipeline_reference_holder']=True;scene.collection.children.link(holders)
    anchor=bpy.data.objects.new(kind+': '+item,None);anchor['pipeline_datablock']=linked;anchor['pipeline_kind']=kind;anchor['pipeline_usage']=apply;anchor.hide_render=True;anchor.hide_viewport=True;holders.objects.link(anchor)
    return linked

def unlink_datablock(source,kind,item):
    matches=[o for o in bpy.data.objects if o.get('pipeline_kind')==kind and (d:=o.get('pipeline_datablock')) and d.library and d.name==item and str(Path(bpy.path.abspath(d.library.filepath)).resolve()).casefold()==str(Path(source).resolve()).casefold()]
    if not matches:raise ValueError('No managed datablock reference found')
    data=matches[0]['pipeline_datablock']
    if data.users>len(matches)+int(data.use_fake_user):raise ValueError('This datablock is still assigned in Blender. Remove its usages there before unlinking the reference.')
    for obj in matches:bpy.data.objects.remove(obj,do_unlink=True)
    if data.users==0:bpy.data.batch_remove(ids=[data])

def link_collection(source,collection,mode='instance',scene_name='',camera='',_linked=None):
    if mode not in {'instance','collection','override'}:raise ValueError('Unknown link mode')
    scene=bpy.data.scenes.get(scene_name) if scene_name else bpy.context.scene
    if not scene:raise ValueError('Destination scene not found')
    layer=scene.view_layers[0]
    source=str(Path(source).resolve())
    if bpy.data.filepath and Path(bpy.data.filepath).resolve()==Path(source):raise ValueError('Cannot link this file into itself')
    if _linked is None:
        with bpy.data.libraries.load(source,link=True,relative=True) as (src,dst):
            if collection not in src.collections:raise ValueError('Collection no longer exists; refresh source')
            dst.collections=[collection]
        linked=dst.collections[0]
    else:linked=_linked
    if not linked.all_objects:raise ValueError('Cannot link an empty collection')
    if mode=='instance':
        if camera:raise ValueError('Use a direct collection or override to select a linked camera')
        obj=bpy.data.objects.new(collection,None);obj.instance_type='COLLECTION';obj.instance_collection=linked;scene.collection.objects.link(obj)
        return linked
    if linked not in list(scene.collection.children):scene.collection.children.link(linked)
    if mode=='override':
        local=linked.override_hierarchy_create(scene,layer,do_fully_editable=True)
        if not local or not local.override_library:raise ValueError('Blender did not create an override hierarchy')
        if linked in list(scene.collection.children):scene.collection.children.unlink(linked)
        if local not in list(scene.collection.children):scene.collection.children.link(local)
        linked=local
        prepare_material_slots({o.name for o in linked.all_objects},strict=False)
    if camera:
        match=next((o for o in linked.all_objects if o.type=='CAMERA' and (o.name==camera or (o.override_library and o.override_library.reference.name==camera))),None)
        if not match:raise ValueError('Selected camera is not in that collection')
        scene.camera=match
    prepare_material_slots(strict=False)
    return linked

def link_batch(source,items,mode='override',scene_name='',camera=''):
    """Load once, place top-level collections, and avoid adding their objects twice."""
    if mode not in {'instance','collection','override'}:raise ValueError('Unknown link mode')
    scene=bpy.data.scenes.get(scene_name) if scene_name else bpy.context.scene
    if not scene or scene.library:raise ValueError('Choose a local destination scene')
    source=str(Path(source).resolve())
    if Path(bpy.data.filepath).resolve()==Path(source):raise ValueError('Cannot link this file into itself')
    grouped={}
    for item in items:grouped.setdefault(item['kind'],[]).append(item['name'])
    with bpy.data.libraries.load(source,link=True,relative=True) as (src,dst):
        for kind,names in grouped.items():
            if kind not in KINDS and kind!='collections':raise ValueError('Unsupported datablock type')
            if any(name not in getattr(src,kind,[]) for name in names):raise ValueError('Source changed; refresh and select again')
            setattr(dst,kind,list(names))
    loaded={(kind,name):data for kind,names in grouped.items() for name,data in zip(names,getattr(dst,kind))}
    if any(data is None for data in loaded.values()):raise ValueError('Blender could not load the full selection')
    collections=[data for (kind,_),data in loaded.items() if kind=='collections']
    roots=[c for c in collections if not any(c in list(p.children_recursive) for p in collections if p!=c)]
    if mode=='override':
        seen=set()
        for c in roots:
            objects=set(c.all_objects)
            if seen&objects:raise ValueError('Collections share objects; use a common parent for overrides, or direct linking')
            seen.update(objects)
    covered={o for c in collections for o in c.all_objects}
    placed=[]
    for c in roots:placed.extend(link_collection(source,c.name,mode,scene_name,_linked=c).all_objects)
    for item in items:
        kind,name=item['kind'],item['name'];data=loaded[(kind,name)]
        if kind=='collections' or (kind=='objects' and data in covered):continue
        if kind=='objects':
            if data not in list(scene.objects):scene.collection.objects.link(data)
            if mode=='override':
                local=data.override_hierarchy_create(scene,scene.view_layers[0],do_fully_editable=True)
                if not local or not local.override_library:raise ValueError('Blender did not create an object override')
                if data in list(scene.collection.objects):scene.collection.objects.unlink(data)
                if local not in list(scene.objects):scene.collection.objects.link(local)
                data=local
            placed.append(data)
        link_datablock(source,kind,name,item.get('apply','object' if kind=='objects' else 'keep'),item.get('object_name',''),scene_name,_linked=data)
    if camera:
        match=next((o for o in placed if o.type=='CAMERA' and (o.name==camera or (o.override_library and o.override_library.reference.name==camera))),None)
        if not match or match not in list(scene.objects):raise ValueError('Choose a camera added directly to this scene; instances cannot supply its active camera')
        scene.camera=match
    prepare_material_slots(strict=False)
