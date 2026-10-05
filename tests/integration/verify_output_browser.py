"""Real EXR conversion is bounded, reused and leaves original render data intact."""
import struct
import tempfile
from pathlib import Path

from blender_pipeline.bootstrap import create_application
from blender_pipeline.project.model import digest
from support import FIXTURES


with tempfile.TemporaryDirectory(prefix='pipeline-output-preview-') as temporary:
    base = Path(temporary)
    app = create_application(base / 'settings', package_addon=False)
    p = app.model
    try:
        p.create(base, 'Preview test')
        directory = p.root / 'Outputs' / 'r001' / 'compositor'
        directory.mkdir(parents=True)
        source = directory / '261005_Scene_Mist_0001.exr'
        p.runtime.run(p.blender, str(FIXTURES / 'preview_image_fixture.py'), [str(source)])
        original = digest(source)
        p.data['renders'] = [{'id': 'r1', 'status': 'Complete', 'number': 1, 'output': 'Outputs/r001',
                             'config': {'prefix': '261005_Scene_'}}]
        p.save()
        request = {'project_id': p.data['id'], 'run_id': 'r1', 'path': 'compositor/' + source.name}
        preview = app.dispatch('output_image', request)
        data = preview.path.read_bytes()
        assert data[:8] == b'\x89PNG\r\n\x1a\n'
        assert struct.unpack('>II', data[16:24]) == (1600, 50)
        second = app.dispatch('output_image', request)
        assert second.path == preview.path
        assert digest(source) == original
        assert not preview.path.is_relative_to(p.root)
        assert list(directory.iterdir()) == [source]
        assert not list(p.root.rglob('.thumbnails'))
    finally:
        app.tasks.pool.shutdown()
print('PASS: real EXR preview, bounded dimensions, reusable machine cache and unchanged source/project outputs')
