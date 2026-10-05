"""Flat, readable, collision-safe names on the frozen compositor copy."""
import re
from pathlib import Path
try:
    from .render_resources import blender_file_path
except ImportError:
    from render_resources import blender_file_path

def clean(value):
    value=re.sub(r'[<>:"/\\|?*#{}\x00-\x1f\s]+','_',str(value)).strip(' ._')[:90]
    return value or 'Output'

def route(tree,output,prefix):
    directory=Path(output)/'compositor';prefix=prefix.rstrip('_')+'_';seen=set();used=set();manifest=[]
    def unique(value):
        base=clean(value);label=base;count=2
        while label.casefold() in used:label=f'{base}_{count:02}';count+=1
        used.add(label.casefold());return label
    def label(node,item=None,socket=None):
        generic={'image','rgba','value','vector','color','file output','file_output','output'}
        if item:
            raw=getattr(item,'path',getattr(item,'name',''))
            if clean(raw).lower() not in generic:return raw
        if socket and socket.is_linked:
            raw=socket.links[0].from_socket.name
            if clean(raw).lower() not in generic:return raw
        if node.label:return node.label
        raw=getattr(node,'file_name','')
        if raw and '{' not in raw and clean(raw).lower() not in generic:return raw
        if clean(node.name).lower() not in generic:return node.name
        return 'Output'
    def walk(current):
        if not current or current.as_pointer() in seen:return
        seen.add(current.as_pointer())
        for node in current.nodes:
            if node.type=='OUTPUT_FILE':
                node.use_file_extension=True
                multilayer=node.format.file_format=='OPEN_EXR_MULTILAYER' or getattr(node.format,'media_type','')=='MULTI_LAYER_IMAGE'
                if hasattr(node,'directory'):
                    node.directory=blender_file_path(directory,extra=200)
                    if multilayer:
                        title=unique(label(node));node.file_name=prefix+title+'_'
                        manifest.append(dict(node=node.label or node.name,pass_name=title,prefix=node.file_name,format=node.format.file_format,multilayer=True,layers=[i.name for i in node.file_output_items]))
                    else:
                        node.file_name=prefix
                        for index,item in enumerate(node.file_output_items):
                            socket=node.inputs[index] if index<len(node.inputs) else None
                            title=unique(label(node,item,socket));item.name=title+'_'
                            fmt=item.format if getattr(item,'override_node_format',False) else node.format
                            manifest.append(dict(node=node.label or node.name,pass_name=title,prefix=prefix+title+'_',format=fmt.file_format,multilayer=False))
                else:
                    if multilayer:
                        title=unique(label(node));node.base_path=blender_file_path(directory/(prefix+title+'_'),extra=16)
                        manifest.append(dict(node=node.label or node.name,pass_name=title,prefix=prefix+title+'_',format=node.format.file_format,multilayer=True))
                    else:
                        node.base_path=blender_file_path(directory,extra=200)
                        for index,item in enumerate(node.file_slots):
                            socket=node.inputs[index] if index<len(node.inputs) else None
                            title=unique(label(node,item,socket));item.path=prefix+title+'_'
                            manifest.append(dict(node=node.label or node.name,pass_name=title,prefix=item.path,format=(node.format if item.use_node_format else item.format).file_format,multilayer=False))
            elif getattr(node,'node_tree',None):walk(node.node_tree)
    walk(tree)
    if manifest:directory.mkdir(parents=True,exist_ok=True)
    return manifest
