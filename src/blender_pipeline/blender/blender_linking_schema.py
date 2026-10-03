"""Validate external batch input without importing Blender into the local server."""
KINDS={'collections','actions','annotations','armatures','brushes','cache_files','cameras','curves','fonts','grease_pencils','hair_curves','images','lattices','lightprobes','lights','linestyles','masks','materials','meshes','metaballs','movieclips','node_groups','objects','paint_curves','palettes','particles','pointclouds','scenes','sounds','speakers','texts','textures','volumes','worlds'}
USAGES={'materials':{'keep','material'},'node_groups':{'keep','modifier','shader'},'worlds':{'keep','world'},'actions':{'keep','animation'},'objects':{'object'}}
def validate_items(items):
    if not isinstance(items,list) or not 1<=len(items)<=200:raise ValueError('Select between 1 and 200 items per link operation.')
    result=[];seen=set();assignments=set()
    for item in items:
        if not isinstance(item,dict) or item.get('kind') not in KINDS or not isinstance(item.get('name'),str) or not item['name'] or len(item['name'])>1024:raise ValueError('Invalid link selection.')
        kind=item['kind'];usage=item.get('apply','object' if kind=='objects' else 'keep')
        if usage not in USAGES.get(kind,{'keep'}):raise ValueError('Invalid assignment for '+kind)
        object_name=item.get('object_name','')
        if not isinstance(object_name,str) or len(object_name)>1024:raise ValueError('Invalid destination object.')
        key=(kind,item['name'])
        if key in seen:continue
        slot=('material',object_name) if usage in {'material','shader'} else ('animation',object_name) if usage=='animation' else ('world','') if usage=='world' else None
        if slot in assignments:raise ValueError('Multiple items would replace the same assignment. Choose one material per object slot, one action per object, and one scene world.')
        if slot:assignments.add(slot)
        seen.add(key);result.append(dict(kind=kind,name=item['name'],apply=usage,object_name=object_name))
    return result
