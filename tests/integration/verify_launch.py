"""Exercise launch error handling without spawning additional Blender windows."""
import subprocess, tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from blender_pipeline.project.model import Pipeline

with tempfile.TemporaryDirectory() as directory:
    p=Pipeline(); p.registry=Path(directory)/'recent.json';p.create(directory,'Test')
    p.folder('Shots'); folder=p.data['nodes'][-1]
    with patch.object(p,'desktop_available',return_value=False):
        try: p.launch(folder['id'])
        except ValueError as exc: assert 'Launch.cmd' in str(exc)
        else: raise AssertionError('Restricted desktop launch must be rejected')
        assert p.state()['desktop_warning']
    with patch.object(p,'desktop_available',return_value=True), patch('os.startfile') as opener:
        p.launch(folder['id']);opener.assert_called_once_with(str(p.path(folder)),'open')
    executable=Path(directory)/'blender.exe';executable.touch();p.blender=str(executable)
    blend=Path(directory)/'file.blend';blend.touch()
    process=MagicMock();process.wait.return_value=7
    with patch.object(p,'desktop_available',return_value=True),patch('subprocess.Popen',return_value=process):
        try:p.start_blender(blend)
        except ValueError as exc:assert 'code 7' in str(exc) and 'Launch log' in str(exc)
        else:raise AssertionError('Immediate Blender exit must be reported')
    process.wait.side_effect=subprocess.TimeoutExpired('blender',2)
    with patch.object(p,'desktop_available',return_value=True),patch('subprocess.Popen',return_value=process):
        assert p.start_blender(blend)==process
print('PASS: restricted-account message, folder request, Blender early exit and successful startup checks.')
