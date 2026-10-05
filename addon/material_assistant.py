"""Live material-slot diagnostics and edits; never localizes geometry or source data."""
import bpy
from pathlib import Path


def library_path(data):
    if data is None:
        return ''
    reference=data.override_library.reference if data.override_library else data
    return str(Path(bpy.path.abspath(reference.library.filepath)).resolve()) if reference.library else ''


def linked_groups(tree,seen=None):
    if not tree:return False
    seen=set() if seen is None else seen
    if tree in seen:return False
    seen.add(tree)
    return bool(tree.library) or any(linked_groups(getattr(node,'node_tree',None),seen) for node in tree.nodes)


def describe(obj):
    info={'object':obj,'slot':None,'material':None,'blocked':'','can_add_slot':False,
          'object_source':'','shader_source':'','binding':'','shader':'','can_restore':False}
    if not obj:
        info['blocked']='Select an object to inspect its material.'
        return info
    info['object_source']=library_path(obj) or library_path(obj.data)
    if obj.instance_type=='COLLECTION' and obj.instance_collection:
        info['blocked']='Collection instance: use Library overrides to edit individual objects.'
        info['object_source']=library_path(obj.instance_collection)
        return info
    if not hasattr(obj.data,'materials'):
        info['blocked']='This object has no material slots.'
        return info
    if obj.library:
        info['blocked']='Read-only linked object. Link its collection in Library overrides mode.'
    elif obj.override_library and obj.override_library.is_system_override:
        info['blocked']='System override: make the object editable in Blender before assigning materials.'
    elif obj.mode!='OBJECT':
        info['blocked']='Switch to Object Mode before changing material assignments.'
    reference=obj.override_library.reference if obj.override_library else None
    if not obj.material_slots:
        info['can_add_slot']=not info['blocked'] and not reference and not obj.data.library and not obj.data.override_library
        if not info['blocked']:
            info['blocked']='Add a material slot to this object.' if info['can_add_slot'] else 'Add a material slot in the source file, save it, then reload linked assets.'
        return info
    index=obj.active_material_index
    slot=obj.material_slots[index]
    info.update(slot=slot,material=slot.material)
    if reference and index>=len(reference.material_slots):
        info['blocked']='This slot has no source counterpart. Prepare the slot in the source file first.'
    source_slot=reference.material_slots[index] if reference and index<len(reference.material_slots) else None
    info['binding']='Object assignment' if slot.link=='OBJECT' else 'Inherited mesh assignment' if reference or obj.data.library else 'Shared mesh assignment'
    if source_slot and slot.link==source_slot.link and slot.material==source_slot.material:
        info['binding']='Inherited source assignment'
    material=slot.material
    info['shader_source']=library_path(material)
    info['shader']='No material assigned' if not material else 'Linked shader · source updates enabled' if material.library else 'Shader library override' if material.override_library else 'Local shader · linked groups still update' if linked_groups(material.node_tree) else 'Local shader'
    info['can_restore']=not info['blocked'] and (slot.link!='DATA' if not source_slot else slot.link!=source_slot.link or slot.material!=source_slot.material)
    return info


def editable_slot(obj):
    info=describe(obj)
    if info['blocked']:
        raise ValueError(info['blocked'])
    return info['slot']


def assign(obj,material):
    slot=editable_slot(obj)
    if material is None:
        raise ValueError('Choose a replacement material first.')
    # Assigning on the object keeps shared/linked mesh materials untouched.
    previous=(slot.link,slot.material)
    try:
        slot.link='OBJECT'
        slot.material=material
    except Exception:
        slot.link=previous[0]
        if previous[0]=='OBJECT':slot.material=previous[1]
        raise


def local_copy(obj):
    slot=editable_slot(obj)
    if not slot.material:
        raise ValueError('Assign a material before making a local copy.')
    copied=slot.material.copy()
    try:
        assign(obj,copied)
        copied.name+=' Local'
        return copied
    except Exception:
        if not copied.users:bpy.data.materials.remove(copied)
        raise


def restore(obj):
    slot=editable_slot(obj)
    reference=obj.override_library.reference if obj.override_library else None
    source_slot=reference.material_slots[obj.active_material_index] if reference else None
    if source_slot and source_slot.link=='OBJECT':
        assign(obj,source_slot.material) if source_slot.material else _restore_empty_object_slot(slot)
    else:
        slot.link='DATA'


def _restore_empty_object_slot(slot):
    slot.link='OBJECT'
    slot.material=None


def add_slot(obj):
    if not describe(obj)['can_add_slot']:
        raise ValueError('Prepare material slots in the source file instead.')
    obj.data.materials.append(None)


def draw(box,context,settings,source_node):
    info=describe(context.object)
    obj=info['object']
    if obj and hasattr(obj.data,'materials') and obj.material_slots:
        box.label(text=obj.name,icon='OBJECT_DATA')
        box.template_list('MATERIAL_UL_matslots','pipeline',obj,'material_slots',obj,'active_material_index',rows=2,maxrows=4)
        box.label(text=info['binding'],icon='LINKED' if info['binding'].startswith('Inherited') else 'MATERIAL')
        box.label(text=info['shader'])
    if info['blocked']:
        # Split at word boundaries for narrow Blender sidebars.
        words=info['blocked'].split();line=''
        for word in words:
            if len(line)+len(word)>46:box.label(text=line,icon='INFO');line=''
            line=(line+' '+word).strip()
        if line:box.label(text=line,icon='INFO')
    if info['can_add_slot']:box.operator('pipeline.material_add_slot',icon='ADD')
    if info['slot'] and not info['blocked']:
        box.prop_search(settings,'material_choice',bpy.data,'materials',text='Replacement')
        row=box.row();row.enabled=bool(settings.material_choice);row.operator('pipeline.material_assign',text='Assign to active slot',icon='MATERIAL')
        if info['slot'].link=='DATA' and info['material']:
            box.operator('pipeline.material_object_slot',text='Use object assignment',icon='OBJECT_DATA')
        if info['material']:
            box.operator('pipeline.local_material',text='Make shader local copy',icon='DUPLICATE')
            box.label(text='Copies stop source material edits.',icon='INFO')
            box.label(text='Linked node groups remain linked.')
        if info['can_restore']:
            box.operator('pipeline.material_restore',text='Restore source assignment' if obj.override_library else 'Use mesh assignment',icon='LOOP_BACK')
    path=info['object_source'] if info['blocked'] else info['shader_source'] or info['object_source']
    if path:
        box.label(text='Source: '+Path(path).name,icon='FILE_BLEND')
        if source_node(path):box.operator('pipeline.material_source',text='Open source in Blender',icon='FILE_BLEND').path=path
