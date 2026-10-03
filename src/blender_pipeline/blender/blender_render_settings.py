"""Discover and apply render RNA values without evaluating arbitrary RNA paths."""
import ast, json, math, re

COMMON={('render','resolution_x'):'width',('render','resolution_y'):'height',('render','resolution_percentage'):'percentage',('render','engine'):'engine',('cycles','samples'):'samples',('cycles','use_denoising'):'denoise',('eevee','taa_render_samples'):'samples',('scene','frame_start'):'start',('scene','frame_end'):'end',('image','file_format'):'format'}
MANAGED={'filepath','file_extension','use_file_extension','use_placeholder','use_render_cache','media_type'}

def enum_options(obj,prop,value):
    options=[dict(value=i.identifier,label=i.name) for i in prop.enum_items if i.identifier]
    current=set(value) if prop.is_enum_flag else {value}
    if current.issubset({i['value'] for i in options}) and options:return options
    # Dynamic OCIO enums expose placeholder RNA items. Blender's enum validation
    # reports the real choices before assigning anything; the file is never saved.
    try:setattr(obj,prop.identifier,{'__PIPELINE_INVALID_ENUM__'} if prop.is_enum_flag else '__PIPELINE_INVALID_ENUM__')
    except (TypeError,ValueError) as exc:
        match=re.search(r'not found in (\(.*\))',str(exc))
        if match:
            choices=ast.literal_eval(match.group(1));labels={i['value']:i['label'] for i in options}
            return [dict(value=v,label=labels.get(v,v.replace('_',' '))) for v in choices if isinstance(v,str)]
    finally:
        got=getattr(obj,prop.identifier)
        if (sorted(got) if prop.is_enum_flag else got)!=value:setattr(obj,prop.identifier,set(value) if prop.is_enum_flag else value)
    return options if current.issubset({i['value'] for i in options}) else []

def sources(scene):
    result=[('scene','Timing',scene),('render','Output / performance',scene.render)]
    for scope,group,obj in [('cycles','Cycles',getattr(scene,'cycles',None)),('eevee','EEVEE',getattr(scene,'eevee',None)),('image','Image format',scene.render.image_settings),('encoding','Video encoding',getattr(scene.render,'ffmpeg',None)),('color','Color management',scene.view_settings),('display','Display',scene.display_settings),('sequencer_color','Sequencer color',scene.sequencer_colorspace_settings),('image_color','Image color management',getattr(scene.render.image_settings,'view_settings',None)),('image_display','Image display',getattr(scene.render.image_settings,'display_settings',None)),('image_space','Image color space',getattr(scene.render.image_settings,'linear_colorspace_settings',None)),('stereo','Stereo output',getattr(scene.render.image_settings,'stereo_3d_format',None))]:
        if obj is not None:result.append((scope,group,obj))
    for layer in scene.view_layers:
        result.append(('layer:'+layer.name,'View layer · '+layer.name,layer))
        if getattr(layer,'cycles',None):result.append(('layer_cycles:'+layer.name,'View layer Cycles · '+layer.name,layer.cycles))
    return result

def catalog(scene):
    entries=[]
    for scope,group,obj in sources(scene):
        for prop in obj.bl_rna.properties:
            key=prop.identifier
            if key=='rna_type' or key.startswith('bl_') or key=='name' and scope not in {'sequencer_color','image_space'}:continue
            if scope=='scene' and key not in {'frame_start','frame_end','frame_step'}:continue
            try:
                value=getattr(obj,key)
                if prop.type in {'POINTER','COLLECTION'}:continue
                if getattr(prop,'is_array',False):value=list(value)
                elif prop.type=='ENUM' and prop.is_enum_flag:value=sorted(value)
                if not isinstance(value,(bool,int,float,str,list)):continue
                if isinstance(value,float) and not math.isfinite(value):continue
                json.dumps(value,allow_nan=False)
                common=COMMON.get((scope,key))
                reason='Use the common render controls.' if common else 'Managed by the pipeline output/version system.' if key in MANAGED else 'Edit this path in Blender.' if prop.type=='STRING' and prop.subtype in {'FILE_PATH','DIR_PATH','PASSWORD'} else 'Read-only in Blender.' if prop.is_readonly or obj.is_property_readonly(key) else ''
                entry=dict(key=json.dumps([scope,key],separators=(',',':')),scope=scope,property=key,category=group,label=prop.name,description=prop.description,type=prop.type,value=value,editable=not bool(reason),reason=reason,common=common,array=getattr(prop,'array_length',0),flags=bool(getattr(prop,'is_enum_flag',False)),unit=getattr(prop,'unit','NONE'))
                if prop.type in {'INT','FLOAT'}:entry.update(min=prop.hard_min,max=prop.hard_max)
                if prop.type=='ENUM':entry['options']=enum_options(obj,prop,value) if not reason else [dict(value=i.identifier,label=i.name) for i in prop.enum_items if i.identifier]
                entries.append(entry)
            except (AttributeError,TypeError,ValueError,RuntimeError):continue
    return entries

def checked_value(entry,value):
    if not entry.get('editable'):raise ValueError(entry['label']+': '+entry.get('reason','Edit in Blender.'))
    def scalar(v):
        kind=entry['type']
        if kind=='BOOLEAN':
            if type(v) is not bool:raise ValueError(entry['label']+': use true or false.')
        elif kind in {'INT','FLOAT'}:
            if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or kind=='INT' and int(v)!=v:raise ValueError(entry['label']+': use a valid number.')
            if not entry['min']<=v<=entry['max']:raise ValueError(entry['label']+': outside Blender’s allowed range.')
        elif kind in {'ENUM','STRING'}:
            if not isinstance(v,str) or len(v)>512 or '\x00' in v:raise ValueError(entry['label']+': invalid text.')
            choices={i['value'] for i in entry.get('options',[])}
            if kind=='ENUM' and choices and v not in choices:raise ValueError(entry['label']+': unsupported option.')
        else:raise ValueError('Unsupported setting type.')
        return v
    if entry.get('array'):
        if not isinstance(value,list) or len(value)!=entry['array']:raise ValueError(entry['label']+': wrong number of components.')
        return [scalar(v) for v in value]
    if entry.get('flags'):
        if not isinstance(value,list) or len(value)>64:raise ValueError(entry['label']+': choose valid options.')
        return [scalar(v) for v in value]
    return scalar(value)

def validate(values,entries):
    if not isinstance(values,dict) or len(values)>1000:raise ValueError('Invalid advanced render settings.')
    lookup={e['key']:e for e in entries};checked={}
    for key,value in values.items():
        if key not in lookup:raise ValueError('Render setting unavailable in this saved scene. Refresh the file and review its advanced settings: '+str(key))
        checked[key]=checked_value(lookup[key],value)
    return checked

def apply(scene,values):
    values=validate(values,catalog(scene));lookup={scope:obj for scope,_,obj in sources(scene)};actual={}
    # Dependent color options and encoding choices are applied after their parent selection.
    rank={'view_transform':0,'format':0,'codec':1,'look':2,'color_mode':3,'color_depth':4}
    for key,value in sorted(values.items(),key=lambda item:rank.get(json.loads(item[0])[1],5)):
        scope,prop=json.loads(key);obj=lookup[scope];rna=obj.bl_rna.properties[prop]
        try:setattr(obj,prop,set(value) if getattr(rna,'is_enum_flag',False) else value)
        except (TypeError,ValueError,RuntimeError,AttributeError) as exc:raise ValueError(f'Cannot apply {rna.name}: {exc}') from exc
        got=getattr(obj,prop);got=sorted(got) if getattr(rna,'is_enum_flag',False) else list(got) if getattr(rna,'is_array',False) else got
        if isinstance(got,(int,float)) and not isinstance(got,bool):
            if not math.isclose(got,value,rel_tol=1e-6,abs_tol=1e-6):raise ValueError(rna.name+': Blender changed the requested value.')
        elif isinstance(got,list) and rna.type in {'INT','FLOAT'}:
            if any(not math.isclose(a,b,rel_tol=1e-6,abs_tol=1e-6) for a,b in zip(got,value)):raise ValueError(rna.name+': Blender changed the requested components.')
        elif got!=(sorted(value) if getattr(rna,'is_enum_flag',False) else value):raise ValueError(rna.name+': Blender changed the requested value.')
        actual[key]=got
    return actual

def read(scene,keys):
    lookup={scope:obj for scope,_,obj in sources(scene)};values={}
    for key in keys:
        scope,prop=json.loads(key);obj=lookup[scope];rna=obj.bl_rna.properties[prop];value=getattr(obj,prop)
        values[key]=sorted(value) if getattr(rna,'is_enum_flag',False) else list(value) if getattr(rna,'is_array',False) else value
    return values
