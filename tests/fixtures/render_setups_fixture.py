"""Two scenes, two visually distinct layers, and a compositor requiring both."""
import bpy
import sys

bpy.ops.wm.read_factory_settings(use_empty=False)
scene = bpy.context.scene
scene.name = 'Main'
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = 1
scene.cycles.use_denoising = False
scene.render.resolution_x = scene.render.resolution_y = 16
scene.render.resolution_percentage = 100
scene.frame_start = 1
scene.frame_end = 2
scene.render.image_settings.file_format = 'PNG'
scene.view_settings.view_transform = 'Standard'
scene.render.film_transparent = True
cube = bpy.data.objects['Cube']
original = cube.users_collection[0]
collections = []
for label, color in [('Red', (1, 0, 0, 1)), ('Blue', (0, 0, 1, 1))]:
    collection = bpy.data.collections.new(label)
    scene.collection.children.link(collection)
    collections.append(collection)
    material = bpy.data.materials.new(label)
    material.use_nodes = True
    tree = material.node_tree
    tree.nodes.clear()
    emission = tree.nodes.new('ShaderNodeEmission')
    emission.inputs['Color'].default_value = color
    output = tree.nodes.new('ShaderNodeOutputMaterial')
    tree.links.new(emission.outputs[0], output.inputs[0])
    obj = cube.copy()
    obj.data = cube.data.copy()
    obj.name = label + ' cube'
    obj.data.materials.clear()
    obj.data.materials.append(material)
    collection.objects.link(obj)
bpy.data.objects.remove(cube, do_unlink=True)
red = scene.view_layers[0]
red.name = 'Red'
blue = scene.view_layers.new('Blue')
scene.cycles.use_layer_samples = 'USE'
red.samples = 7
blue.samples = 9
red.layer_collection.children['Blue'].exclude = True
blue.layer_collection.children['Red'].exclude = True
red.use_pass_z = True
blue.use_pass_normal = True
other = scene.copy()
other.name = 'Detail'
other.use_fake_user = True
other.frame_start = other.frame_end = 4
other.render.resolution_x = 24
for current in [scene, other]:
    tree = bpy.data.node_groups.new(current.name + ' compositor', 'CompositorNodeTree')
    current.compositing_node_group = tree
    current.use_nodes = True
    current.render.use_compositing = True
    tree.interface.new_socket(name='Image', in_out='OUTPUT', socket_type='NodeSocketColor')
    a = tree.nodes.new('CompositorNodeRLayers')
    a.layer = 'Red'
    b = tree.nodes.new('CompositorNodeRLayers')
    b.layer = 'Blue'
    inner = bpy.data.node_groups.new(current.name + ' combine layers', 'CompositorNodeTree')
    inner.interface.new_socket(name='A', in_out='INPUT', socket_type='NodeSocketColor')
    inner.interface.new_socket(name='B', in_out='INPUT', socket_type='NodeSocketColor')
    inner.interface.new_socket(name='Image', in_out='OUTPUT', socket_type='NodeSocketColor')
    group = tree.nodes.new('CompositorNodeGroup')
    group.node_tree = inner
    tree.links.new(a.outputs['Image'], group.inputs['A'])
    tree.links.new(b.outputs['Image'], group.inputs['B'])
    inputs = inner.nodes.new('NodeGroupInput')
    mix = inner.nodes.new('ShaderNodeMix')
    mix.data_type = 'RGBA'
    mix.blend_type = 'ADD'
    mix.inputs[0].default_value = 1
    inner.links.new(inputs.outputs['A'], mix.inputs[6])
    inner.links.new(inputs.outputs['B'], mix.inputs[7])
    inner_output = inner.nodes.new('NodeGroupOutput')
    inner.links.new(mix.outputs[2], inner_output.inputs['Image'])
    unused = inner.nodes.new('CompositorNodeRLayers')
    unused.scene = other if current == scene else scene
    unused.layer = 'Red'
    output = tree.nodes.new('NodeGroupOutput')
    tree.links.new(group.outputs['Image'], output.inputs['Image'])
    file = tree.nodes.new('CompositorNodeOutputFile')
    file.directory = 'NEVER_WRITE_HERE'
    file.format.media_type = 'IMAGE'
    file.format.file_format = 'PNG'
    file.file_output_items.new('RGBA', 'Combined')
    tree.links.new(group.outputs['Image'], file.inputs['Combined'])
scene.frame_set(2)
bpy.context.window.scene = scene
bpy.context.window.view_layer = blue
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=sys.argv[sys.argv.index('--') + 1])
