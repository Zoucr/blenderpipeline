"""Retain normal GPU caches; use a local fallback when their location is unwritable."""
import os
from pathlib import Path
import tempfile


def writable_cache(path, database=None):
    try:
        if not path.is_dir():
            return False
        if database and (path / database).exists():
            with (path / database).open('r+b'):
                pass  # Check access without changing the driver's database.
        with tempfile.TemporaryFile(dir=path):
            pass
        return True
    except OSError:
        return False


def render_environment(settings_directory):
    environment = dict(os.environ)
    if os.name != 'nt':
        return environment
    defaults = {'OPTIX_CACHE_PATH': ('LOCALAPPDATA', 'NVIDIA/OptixCache', 'optix7cache.db', 'optix'),
                'CUDA_CACHE_PATH': ('APPDATA', 'NVIDIA/ComputeCache', None, 'cuda')}
    for key, (variable, relative, database, directory) in defaults.items():
        if key in environment:
            continue  # Respect an explicitly configured cache location.
        base = environment.get(variable)
        if base and writable_cache(Path(base) / relative, database):
            continue
        fallback = Path(settings_directory) / 'render-cache' / directory
        try:
            fallback.mkdir(parents=True, exist_ok=True)
            if writable_cache(fallback):
                environment[key] = str(fallback.resolve())
        except OSError:
            pass  # Rendering remains available if disk caching is unavailable.
    return environment
