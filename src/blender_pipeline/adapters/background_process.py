"""Disposable working directories for Blender's incidental startup/cache files.

Saved inputs and outputs use absolute paths. A background Blender process must
never inherit the source checkout or a user's project as its working directory.
"""
import atexit
import os
import subprocess
import tempfile
import threading


def background_directory():
    return tempfile.TemporaryDirectory(prefix='pipeline-blender-')


def background_environment(environment=None):
    result = dict(os.environ if environment is None else environment)
    result['PYTHONDONTWRITEBYTECODE'] = '1'
    return result


def start_background_process(command, **options):
    directory = background_directory()
    try:
        options['env'] = background_environment(options.get('env'))
        process = subprocess.Popen(command, cwd=directory.name, **options)
    except BaseException:
        directory.cleanup()
        raise
    process._pipeline_directory = directory
    process._pipeline_directory_lock = threading.Lock()
    process._pipeline_shutdown = lambda: stop_background_process(process)
    atexit.register(process._pipeline_shutdown)
    return process


def cleanup_background_process(process):
    directory = getattr(process, '_pipeline_directory', None)
    if isinstance(directory, tempfile.TemporaryDirectory):
        with process._pipeline_directory_lock:
            directory.cleanup()
            atexit.unregister(process._pipeline_shutdown)


def stop_background_process(process):
    """Interpreter shutdown must release a worker's cwd before removing it."""
    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    cleanup_background_process(process)
