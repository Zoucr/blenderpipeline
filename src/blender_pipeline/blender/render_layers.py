"""Saved layer/compositor observations, shared by scanning and frozen render jobs."""
import json


def compositor_tree(scene):
    return getattr(scene, 'compositing_node_group', None) or getattr(scene, 'node_tree', None)


def compositor_dependencies(tree, scene):
    """Trace connected outputs, including group boundaries and muted-node bypasses.

    Both sides of switches are inspected conservatively: animated switches can
    require either input later in a sequence. Unconnected nodes are ignored.
    """
    result, seen = [], set()

    def incoming(socket, current, stack):
        for link in socket.links:
            if getattr(link, 'is_valid', True):
                visit(link.from_node, link.from_socket, current, stack)

    def matching(sockets, socket):
        return next((s for s in sockets if s.identifier == socket.identifier), None) or next((s for s in sockets if s.name == socket.name), None)

    def visit(node, output, current, stack):
        key = (node.as_pointer(), output.identifier if output else '', tuple(n.as_pointer() for n, _ in stack))
        if key in seen:
            return
        seen.add(key)
        if node.mute:
            for link in node.internal_links:
                if output is None or link.to_socket == output:
                    incoming(link.from_socket, current, stack)
        elif node.type == 'R_LAYERS':
            source = node.scene or scene
            layer = node.layer or (source.view_layers[0].name if source.view_layers else '')
            entry = dict(scene=source.name, view_layer=layer, node=node.label or node.name)
            if entry not in result:
                result.append(entry)
        elif node.type == 'GROUP_INPUT' and stack:
            parent, outer = stack[-1]
            socket = matching(parent.inputs, output)
            if socket:
                incoming(socket, outer, stack[:-1])
        elif node.type == 'GROUP' and node.node_tree:
            if any(parent == node for parent, _ in stack):
                return
            for group_output in node.node_tree.nodes:
                if group_output.type == 'GROUP_OUTPUT' and getattr(group_output, 'is_active_output', True):
                    socket = matching(group_output.inputs, output)
                    if socket:
                        incoming(socket, node.node_tree, stack + [(node, current)])
        else:
            for socket in node.inputs:
                incoming(socket, current, stack)

    if tree:
        for node in tree.nodes:
            if node.type in {'COMPOSITE', 'GROUP_OUTPUT', 'OUTPUT_FILE'} and not node.mute and getattr(node, 'is_active_output', True):
                visit(node, None, tree, [])
    return result


def layer_metadata(scene):
    return [dict(name=layer.name, enabled=bool(layer.use), samples=getattr(layer, 'samples', 0),
                 passes=[p.identifier for p in layer.bl_rna.properties
                         if p.identifier.startswith('use_pass_') and getattr(layer, p.identifier, False)])
            for layer in scene.view_layers]


def selection(scene, scenes, view_layer='', compositor='BLENDER', advanced=None):
    """Validate metadata before submission and again against the frozen file."""
    if compositor not in {'BLENDER', 'OFF'}:
        raise ValueError('Choose the saved Blender compositor setting or Bypass compositor.')
    layers = scene.get('view_layers', [])
    if view_layer and not any(layer['name'] == view_layer for layer in layers):
        raise ValueError('View layer missing: ' + view_layer + '. Refresh and choose a saved view layer.')
    enabled = {layer['name'] for layer in layers if layer['enabled']}
    compositing = bool(scene.get('use_compositing', True))
    for key, value in (advanced or {}).items():
        scope, prop = json.loads(key)
        if scope == 'render' and prop == 'use_compositing':
            compositing = value
        if scope.startswith('layer:') and prop == 'use':
            if view_layer:
                raise ValueError('Use the View layers selector instead of advanced Use for Rendering overrides.')
            (enabled.add if value else enabled.discard)(scope[6:])
    if view_layer:
        enabled = {view_layer}
    if layers and not enabled:
        raise ValueError('No view layers enabled in ' + scene['name'] + '.')
    compositing = compositor != 'OFF' and compositing
    errors = []
    if compositing:
        for dependency in scene.get('compositor_dependencies', []):
            other = next((s for s in scenes if s['name'] == dependency['scene']), None)
            layer = dependency['view_layer']
            if not other or not any(l['name'] == layer for l in other.get('view_layers', [])):
                errors.append(dependency['scene'] + ' / ' + layer + ' is missing')
            elif other['name'] == scene['name'] and layer not in enabled:
                errors.append(other['name'] + ' / ' + layer + ' is not selected')
            elif other['name'] != scene['name'] and not any(l['name'] == layer and l['enabled'] for l in other['view_layers']):
                errors.append(other['name'] + ' / ' + layer + ' is disabled')
        if errors:
            raise ValueError('Compositor needs ' + '; '.join(dict.fromkeys(errors)) + '. Choose All enabled view layers, adjust the compositor in Blender, or Bypass compositor for a raw layer render.')
    return dict(view_layers=[l['name'] for l in layers if l['name'] in enabled], use_compositing=compositing)
