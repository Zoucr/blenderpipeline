"""Conservative image-use observations; unknown consumers always need review."""


def classify_images(images, trees, users):
    """trees contains (owner ID, node tree), users is Blender's ID user map.

    Only unreferenced images and static, disconnected image nodes are proven
    unused. This deliberately does not guess scene visibility or switch values.
    """
    known = {image: [] for image in images}
    for owner, tree in trees:
        if tree is None: continue
        for node in tree.nodes:
            image = getattr(node, 'image', None)
            if image not in known: continue
            known[image].append((owner, tree, node))
    result = {}
    for image in images:
        consumers = users.get(image)
        refs = known[image]
        if consumers is None or getattr(image, 'animation_data', None):
            result[image] = 'unknown'; continue
        if not consumers and image.users <= int(image.use_fake_user):
            result[image] = 'unused'; continue
        covered = {item for owner, tree, _ in refs for item in (owner, tree)}
        if not refs or not consumers.issubset(covered):
            result[image] = 'unknown'; continue
        if any(getattr(owner, 'animation_data', None) or getattr(tree, 'animation_data', None)
               for owner, tree, _ in refs):
            result[image] = 'unknown'; continue
        if any(any(socket.is_linked for socket in node.outputs) for _, _, node in refs):
            result[image] = 'used'; continue
        # Unknown image-owning node types may consume an image without outputs.
        if all(node.bl_idname in {'ShaderNodeTexImage', 'ShaderNodeTexEnvironment', 'CompositorNodeImage'}
               and len(node.outputs) for _, _, node in refs):
            result[image] = 'unused'
        else: result[image] = 'unknown'
    return result
