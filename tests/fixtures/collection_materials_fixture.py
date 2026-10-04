"""Nested assets bring assigned materials and shader dependencies automatically."""
import bpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src/blender_pipeline/blender'))
from blender_linking import link_batch, link_collection, prepare_material_slots

root = Path(sys.argv[sys.argv.index('--') + 1])
root.mkdir(parents=True, exist_ok=True)
bpy.context.preferences.filepaths.save_version = 0


def save(path):
    bpy.ops.wm.save_as_mainfile(filepath=str(path))


def assert_materials(objects, label, rubber='Rubber', replacements=None, count=24):
    meshes = [obj for obj in objects if obj.type == 'MESH']
    assert len(meshes) == count, (label, len(meshes))
    for obj in meshes:
        original = obj.override_library.reference if obj.override_library else obj
        index = int(original.name.split('_')[-1])
        expected = ['Clear' if index % 3 == 0 else 'Copper', None, rubber]
        for slot_index, material in (replacements or {}).get(index, {}).items():
            expected[slot_index] = material
        actual = [slot.material.name if slot.material else None for slot in obj.material_slots]
        assert actual == expected, (label, obj.name, expected, actual)
        for slot in obj.material_slots:
            if slot.material:
                is_local = slot.material.name in {'Copper Local', 'Shot Finish'}
                assert bool(slot.material.library) != is_local, (label, obj.name, slot.material.name)
        assert obj.parent and obj.parent.parent, (label, 'empty parenting lost', obj.name)
    mat = bpy.data.materials['Copper']
    group = next(node for node in mat.node_tree.nodes if node.type == 'GROUP').node_tree
    image = next(node for node in mat.node_tree.nodes if node.type == 'TEX_IMAGE').image
    assert group.library and group.name == 'Surface Detail', label
    assert image.library and image.name == 'Packed Texture', label


bpy.ops.wm.read_factory_settings(use_empty=True)
asset = bpy.data.collections.new('Asset')
bpy.context.scene.collection.children.link(asset)
parts = bpy.data.collections.new('Parts')
asset.children.link(parts)
detail = bpy.data.collections.new('Detail')
parts.children.link(detail)
parent = bpy.data.objects.new('Root Empty', None)
asset.objects.link(parent)
child = bpy.data.objects.new('Child Empty', None)
parts.objects.link(child)
child.parent = parent
materials = {name: bpy.data.materials.new(name) for name in ('Copper', 'Rubber', 'Clear')}
for mat in materials.values():
    mat.use_nodes = True
group = bpy.data.node_groups.new('Surface Detail', 'ShaderNodeTree')
materials['Copper'].node_tree.nodes.new('ShaderNodeGroup').node_tree = group
image = bpy.data.images.new('Packed Texture', width=2, height=2)
image.pack()
materials['Copper'].node_tree.nodes.new('ShaderNodeTexImage').image = image
for index in range(24):
    if index % 2 == 0:
        mesh = bpy.data.meshes.new('Geometry_' + str(index))
        mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
        mesh.materials.append(materials['Copper'])
        mesh.materials.append(None)
        mesh.materials.append(materials['Rubber'])
    obj = bpy.data.objects.new('Part_' + str(index), mesh)
    (parts if index % 2 else detail).objects.link(obj)
    obj.parent = child
    if index % 3 == 0:
        obj.material_slots[0].link = 'OBJECT'
        obj.material_slots[0].material = materials['Clear']
save(root / 'Source.blend')

for mode in ('override', 'collection', 'instance'):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    destination = root / (mode + '.blend')
    save(destination)
    # Select just the parent collection, without any separate materials.
    link_batch(root / 'Source.blend', [{'kind': 'collections', 'name': 'Asset'}], mode)
    objects = bpy.data.collections['Asset'].all_objects
    assert_materials(objects, mode + ' before save')
    save(destination)
    bpy.ops.wm.open_mainfile(filepath=str(destination))
    assert_materials(bpy.data.collections['Asset'].all_objects, mode + ' after reopen')

# The companion calls the single-collection helper directly.
bpy.ops.wm.read_factory_settings(use_empty=True)
save(root / 'Companion.blend')
collection = link_collection(root / 'Source.blend', 'Asset', 'override')
assert_materials(collection.all_objects, 'companion before save')
save(root / 'Companion.blend')
bpy.ops.wm.open_mainfile(filepath=str(root / 'Companion.blend'))
assert_materials(bpy.data.collections['Asset'].all_objects, 'companion after reopen')

# An individual object also brings its materials, without a separate material selection.
bpy.ops.wm.read_factory_settings(use_empty=True)
save(root / 'Object.blend')
link_batch(root / 'Source.blend', [{'kind': 'objects', 'name': 'Part_1'}], 'override')
save(root / 'Object.blend')
bpy.ops.wm.open_mainfile(filepath=str(root / 'Object.blend'))
assert_materials([bpy.context.scene.objects['Part_1']], 'individual object', count=1)

# Replace one binding with another linked material; its shared-mesh neighbour is untouched.
bpy.ops.wm.open_mainfile(filepath=str(root / 'override.blend'))
obj = bpy.context.scene.objects['Part_1']
slot = obj.material_slots[0]
slot.link = 'OBJECT'
slot.material = bpy.data.materials['Clear']
obj = bpy.context.scene.objects['Part_4']
local = bpy.data.materials.new('Shot Finish')
obj.material_slots[2].link = 'OBJECT'
obj.material_slots[2].material = local
obj.location.x = 7

# Execute the real companion operator on an inherited DATA material.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'addon'))
import companion
bpy.utils.register_class(companion.PIPELINE_OT_local_material)
obj = bpy.context.scene.objects['Part_2']
bpy.context.view_layer.objects.active = obj
obj.active_material_index = 0
assert obj.material_slots[0].link == 'DATA'
assert bpy.ops.pipeline.local_material() == {'FINISHED'}
bpy.utils.unregister_class(companion.PIPELINE_OT_local_material)
replacements = {1: {0: 'Clear'}, 2: {0: 'Copper Local'}, 4: {2: 'Shot Finish'}}
# The companion's save preparation must preserve both inherited and explicit bindings.
prepare_material_slots()
save(root / 'override.blend')
bpy.ops.wm.open_mainfile(filepath=str(root / 'override.blend'))
assert_materials(bpy.data.collections['Asset'].all_objects, 'local replacements after reopen', replacements=replacements)

# Source shader edits and a replacement mesh material propagate to inherited slots.
bpy.ops.wm.open_mainfile(filepath=str(root / 'Source.blend'))
bpy.data.materials['Copper'].diffuse_color = (.17, .29, .53, 1)
rubber = bpy.data.materials.new('Rubber V2')
for mesh in bpy.data.meshes:
    mesh.materials[2] = rubber
    mesh.vertices[0].co.z = 3
save(root / 'Source.blend')
for filename in ('override', 'collection', 'instance', 'Companion', 'Object'):
    bpy.ops.wm.open_mainfile(filepath=str(root / (filename + '.blend')))
    objects = [bpy.context.scene.objects['Part_1']] if filename == 'Object' else bpy.data.collections['Asset'].all_objects
    assert_materials(objects, filename + ' source update', rubber='Rubber V2',
                     replacements=replacements if filename == 'override' else None,
                     count=1 if filename == 'Object' else 24)
    assert abs(bpy.data.materials['Copper'].diffuse_color[0] - .17) < .001
    assert all(obj.data.vertices[0].co.z == 3 for obj in objects if obj.type == 'MESH')
    if filename == 'override':
        assert bpy.context.scene.objects['Part_4'].location.x == 7
        for library in list(bpy.data.libraries):
            if not library.parent:
                library.reload()
        prepare_material_slots()
        save(root / 'override.blend')
        bpy.ops.wm.open_mainfile(filepath=str(root / 'override.blend'))
        assert_materials(bpy.data.collections['Asset'].all_objects, 'reload + reopen',
                         rubber='Rubber V2', replacements=replacements)
print('PASS: inherited materials/dependencies, nested empties/shared meshes, all link modes, standalone objects, companion local copy, source shader/material/geometry updates and persistent per-object replacements')
