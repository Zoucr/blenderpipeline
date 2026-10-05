"""Portable export option contracts shared by the app and Blender workers."""
import copy


def toggle(key, label, default, group='Geometry', **extra):
    return dict(key=key, label=label, type='boolean', default=default, group=group, **extra)


def number(key, label, default, minimum, maximum, group='Geometry', integer=False, **extra):
    return dict(key=key, label=label, type='integer' if integer else 'number', default=default,
                min=minimum, max=maximum, group=group, **extra)


def choice(key, label, default, values, group='Geometry', **extra):
    return dict(key=key, label=label, type='enum', default=default, values=values, group=group, **extra)


AXES = [{'value': v, 'label': v} for v in ('X', 'Y', 'Z', '-X', '-Y', '-Z')]
EVALUATION = [{'value': 'RENDER', 'label': 'Render'}, {'value': 'VIEWPORT', 'label': 'Viewport'}]
EXPORT_SETTINGS = {
    'FBX': [
        number('global_scale', 'Scale', 1, .001, 1000, 'Transform'),
        toggle('apply_unit_scale', 'Apply scene units', True, 'Transform'),
        choice('axis_forward', 'Forward axis', '-Z', AXES, 'Transform'),
        choice('axis_up', 'Up axis', 'Y', AXES, 'Transform'),
        toggle('use_mesh_modifiers', 'Apply mesh modifiers', True),
        choice('mesh_smooth_type', 'Smoothing', 'OFF', [
            {'value': 'OFF', 'label': 'Normals only'}, {'value': 'FACE', 'label': 'Face'},
            {'value': 'EDGE', 'label': 'Edge'}]),
        toggle('use_triangles', 'Triangulate', False),
        toggle('add_leaf_bones', 'Add leaf bones', True, 'Rig'),
        toggle('use_armature_deform_only', 'Deform bones only', False, 'Rig'),
        number('bake_anim_step', 'Sampling step', 1, .01, 100, 'Animation', animation=True),
        number('bake_anim_simplify_factor', 'Simplify curves', 1, 0, 100, 'Animation', animation=True),
    ],
    'GLB': [
        toggle('export_apply', 'Apply modifiers', False, help='Applying modifiers can prevent shape-key export.'),
        toggle('export_texcoords', 'UV coordinates', True),
        toggle('export_normals', 'Normals', True),
        toggle('export_tangents', 'Tangents', False),
        toggle('export_morph', 'Shape keys', True),
        toggle('export_skins', 'Skinning', True, 'Rig'),
        choice('export_materials', 'Materials', 'EXPORT', [
            {'value': 'EXPORT', 'label': 'Export'}, {'value': 'PLACEHOLDER', 'label': 'Placeholders'},
            {'value': 'VIEWPORT', 'label': 'Viewport colors'}, {'value': 'NONE', 'label': 'None'}], 'Materials'),
        choice('export_image_format', 'Images', 'AUTO', [
            {'value': 'AUTO', 'label': 'Automatic'}, {'value': 'JPEG', 'label': 'JPEG'},
            {'value': 'WEBP', 'label': 'WebP'}, {'value': 'NONE', 'label': 'None'}], 'Materials'),
        number('export_frame_step', 'Sampling step', 1, 1, 120, 'Animation', integer=True, animation=True),
        toggle('export_force_sampling', 'Sample animation', True, 'Animation', animation=True),
    ],
    'USD': [
        toggle('export_uvmaps', 'UV maps', True),
        toggle('export_normals', 'Normals', True),
        toggle('triangulate_meshes', 'Triangulate', False),
        toggle('use_instancing', 'Use instancing', False),
        choice('evaluation_mode', 'Evaluate modifiers', 'RENDER', EVALUATION),
        toggle('export_materials', 'Materials and textures', True, 'Materials'),
    ],
    'ALEMBIC': [
        number('global_scale', 'Scale', 1, .0001, 1000, 'Transform'),
        toggle('flatten', 'Flatten hierarchy', False, 'Transform'),
        choice('evaluation_mode', 'Evaluate modifiers', 'RENDER', EVALUATION),
        toggle('uvs', 'UV coordinates', True),
        toggle('packuv', 'Merge UVs', True),
        toggle('normals', 'Normals', True),
        toggle('vcolors', 'Color attributes', False),
        toggle('face_sets', 'Face sets', False, help='Store material assignment groups, without shader graphs.'),
        toggle('curves_as_mesh', 'Curves as mesh', False),
        toggle('use_instancing', 'Use instancing', True),
        toggle('apply_subdiv', 'Apply subdivision', False),
        toggle('subdiv_schema', 'Store subdivision schema', False),
        number('xsamples', 'Transform samples', 1, 1, 128, 'Sampling', integer=True, animation=True),
        number('gsamples', 'Geometry samples', 1, 1, 128, 'Sampling', integer=True, animation=True),
        number('sh_open', 'Shutter open', 0, -1, 1, 'Sampling', animation=True),
        number('sh_close', 'Shutter close', 1, -1, 1, 'Sampling', animation=True),
    ],
}


def checked_options(options):
    """Keep separate presets per format; never pass arbitrary operator arguments."""
    if not isinstance(options, dict) or set(options) - EXPORT_SETTINGS.keys():
        raise ValueError('Invalid export format options.')
    result = copy.deepcopy(options)
    for mode, values in result.items():
        schema = {setting['key']: setting for setting in EXPORT_SETTINGS[mode]}
        if not isinstance(values, dict) or set(values) - schema.keys():
            raise ValueError('Unknown ' + mode + ' export option.')
        for key, value in values.items():
            setting = schema[key]
            kind = setting['type']
            if kind == 'boolean' and type(value) is not bool:
                raise ValueError(setting['label'] + ' must be enabled or disabled.')
            if kind == 'enum' and value not in [v['value'] for v in setting['values']]:
                raise ValueError('Choose a supported ' + setting['label'].lower() + '.')
            if kind in {'integer', 'number'}:
                if type(value) not in ({int} if kind == 'integer' else {int, float}):
                    raise ValueError('Use a valid number for ' + setting['label'].lower() + '.')
                if not setting['min'] <= value <= setting['max']:
                    raise ValueError(setting['label'] + f" must be between {setting['min']} and {setting['max']}.")
        effective = option_values(mode, {mode: values}, validate=False)
        if mode == 'FBX' and effective['axis_forward'].strip('-') == effective['axis_up'].strip('-'):
            raise ValueError('Forward and up axes must use different dimensions.')
        if mode == 'ALEMBIC' and effective['sh_close'] < effective['sh_open']:
            raise ValueError('Shutter close must not precede shutter open.')
    return result


def option_values(mode, options=None, validate=True, animation=None):
    options = checked_options(options or {}) if validate else options or {}
    result = {**{s['key']: s['default'] for s in EXPORT_SETTINGS[mode]}, **options.get(mode, {})}
    if animation is False:
        for setting in EXPORT_SETTINGS[mode]:
            if setting.get('animation'):
                result[setting['key']] = setting['default']
    return result


def export_timing(config, scene):
    """Resolve blank limits against the saved scene, without changing the preset."""
    animation = config['animation']
    if animation:
        first = scene.get('start') if config.get('start') is None else config['start']
        last = scene.get('end') if config.get('end') is None else config['end']
    else:
        first = last = scene.get('current_frame')
    if any(type(v) is not int or not -1048574 <= v <= 1048574 for v in (first, last)):
        raise ValueError('Refresh the source to read its saved frame range.')
    if last < first:
        raise ValueError('Last frame must not precede first frame, including the saved scene limits.')
    return {'mode': 'ANIMATION' if animation else 'FRAME', 'start': first, 'end': last,
            'frames': last - first + 1, 'fps': scene['fps']}
