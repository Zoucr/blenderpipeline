"""Background Blender execution, injectable independently of project operations."""
import subprocess
from pathlib import Path


class BlenderRuntime:
    def __init__(self, scripts_directory, runner=subprocess.run):
        self.scripts_directory = Path(scripts_directory)
        self.runner = runner

    def run(self, executable, script, args, opened=None):
        command = [executable, '--background', '--factory-startup', '--disable-autoexec']
        if opened:
            command.append(str(opened))
        command += ['--python-exit-code', '1', '--python', str(self.scripts_directory / script),
                    '--', *map(str, args)]
        result = self.runner(command, capture_output=True, text=True, errors='replace', timeout=180,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            raise ValueError('Blender operation failed:\n' + (result.stdout + result.stderr)[-3000:])
