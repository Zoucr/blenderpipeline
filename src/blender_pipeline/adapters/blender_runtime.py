"""Background Blender execution, injectable independently of project operations."""
import subprocess
from pathlib import Path
from .background_process import background_directory, background_environment


class BlenderRuntime:
    def __init__(self, scripts_directory, runner=subprocess.run):
        self.scripts_directory = Path(scripts_directory).resolve()
        self.runner = runner

    def run(self, executable, script, args, opened=None):
        command = [executable, '--background', '--factory-startup', '--disable-autoexec']
        if opened:
            command.append(str(Path(opened).resolve()))
        command += ['--python-exit-code', '1', '--python', str(self.scripts_directory / script),
                    '--', *map(str, args)]
        with background_directory() as directory:
            result = self.runner(command, capture_output=True, text=True, errors='replace', timeout=180,
                                 cwd=directory, env=background_environment(), creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            raise ValueError('Blender operation failed:\n' + (result.stdout + result.stderr)[-3000:])
