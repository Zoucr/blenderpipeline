"""Local desktop operations; kept separate from background Blender workers."""
import getpass
import os
import subprocess
import uuid
from pathlib import Path


class DesktopIntegration:
    @staticmethod
    def available():
        account = getpass.getuser()
        if os.name == 'nt':
            import ctypes
            buffer = ctypes.create_unicode_buffer(256)
            length = ctypes.c_ulong(len(buffer))
            if ctypes.windll.advapi32.GetUserNameW(buffer, ctypes.byref(length)):
                account = buffer.value
        return not (os.name == 'nt' and account.lower().startswith('codexsandbox'))

    def require(self, available=None):
        if not (self.available() if available is None else available):
            raise ValueError('Cannot open desktop applications from the Codex sandbox account. Double-click Launch.cmd in File Explorer, then use the NEW browser tab it opens. Your project files do not need permission changes.')

    def start_blender(self, executable, path, logs, available=None):
        self.require(available)
        path, logs = Path(path), Path(logs)
        if not path.is_file():
            raise ValueError('Blender file not found: ' + str(path))
        if not Path(executable).is_file():
            raise ValueError('Blender executable not found. Update Blender Settings.')
        logs.mkdir(parents=True, exist_ok=True)
        log_path = logs / ('launch-' + uuid.uuid4().hex + '.log')
        with log_path.open('wb') as log:
            process = subprocess.Popen([executable, '--disable-autoexec', str(path)],
                                       stdout=log, stderr=subprocess.STDOUT, cwd=str(path.parent))
        try:
            code = process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            return process
        details = log_path.read_text(encoding='utf-8', errors='replace')[-2000:]
        raise ValueError(f'Blender exited during startup (code {code}).\n{details}\nLaunch log: {log_path}')

    def open_folder(self, path, available=None):
        self.require(available)
        path = Path(path)
        if not path.is_dir():
            raise ValueError('Folder not found: ' + str(path))
        try:
            os.startfile(str(path), 'open')
        except OSError as exc:
            raise ValueError('Windows could not open this folder. Run Launch.cmd from your own File Explorer session.\n' + str(exc)) from exc
