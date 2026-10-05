"""Configure worker-local Cycles devices without changing saved preferences."""


def configure(scene, preferences):
    if scene.render.engine != 'CYCLES':
        return {'requested': scene.render.engine, 'effective': scene.render.engine, 'devices': []}
    requested = scene.cycles.device
    result = {'requested': requested, 'effective': 'CPU', 'backend': 'NONE', 'devices': [], 'warnings': []}
    if requested != 'GPU':
        return result
    # Workers use factory startup, which otherwise silently leaves GPU scenes on
    # the CPU. Detect hardware in this process; never write user preferences.
    supported = {entry[0] for entry in preferences.get_device_types(None)}
    configured = preferences.compute_device_type
    automatic = configured in {'NONE', ''}
    backends = [b for b in ('OPTIX', 'CUDA', 'HIP', 'METAL', 'ONEAPI') if b in supported] if automatic else [configured]
    for backend in backends:
        try:
            devices = preferences.get_devices_for_type(backend)
        except Exception:
            continue
        selected = [d for d in devices if d.type == backend and (automatic or d.use)]
        if not selected:
            continue
        preferences.compute_device_type = backend
        if automatic:
            for device in preferences.devices:
                device.use = device in selected
        result.update(effective='GPU', backend=backend, devices=[d.name for d in selected], automatic=automatic)
        return result
    result['warnings'].append('This scene requests GPU rendering, but no usable GPU was found. Cycles will use the CPU.')
    return result
