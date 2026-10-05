"""Disk sequences, unchanged scan reuse and reusable worker job boundaries."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from blender_pipeline.project.workspace import Pipeline
from blender_pipeline.rendering.inventory import SequenceInventory
from blender_pipeline.rendering.worker import RenderWorker
from blender_pipeline.rendering.environment import render_environment, writable_cache


class RenderOverviewTests(unittest.TestCase):
    def test_local_cache_fallback_preserves_working_and_explicit_locations(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with patch.dict('os.environ',{'LOCALAPPDATA':str(root/'unavailable'),'APPDATA':str(root/'unavailable')},clear=True):
                env=render_environment(root/'settings')
            if sys.platform=='win32':
                self.assertTrue(Path(env['OPTIX_CACHE_PATH']).is_dir())
                self.assertTrue(Path(env['CUDA_CACHE_PATH']).is_dir())
                self.assertTrue(Path(env['OPTIX_CACHE_PATH']).is_relative_to(root/'settings'))
            normal=root/'local'/'NVIDIA'/'OptixCache';normal.mkdir(parents=True)
            (normal/'optix7cache.db').write_bytes(b'unchanged driver data')
            with patch.dict('os.environ',{'LOCALAPPDATA':str(root/'local'),'OPTIX_CACHE_PATH':'explicit-location'},clear=True):
                self.assertEqual(render_environment(root/'settings')['OPTIX_CACHE_PATH'],'explicit-location')
            with patch.dict('os.environ',{'LOCALAPPDATA':str(root/'local')},clear=True):
                self.assertNotIn('OPTIX_CACHE_PATH',render_environment(root/'settings'))
            self.assertEqual((normal/'optix7cache.db').read_bytes(),b'unchanged driver data')
            with patch.object(Path,'is_dir',side_effect=PermissionError('Restricted account')):
                self.assertFalse(writable_cache(normal),'Access failures must not block rendering')

    def test_shutdown_cancels_owned_jobs_without_starting_the_next_setup(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'settings').mkdir()
            p=Pipeline(data_directory=root/'settings');p.create(root,'Shutdown')
            p.data['render_queue']=[dict(id='next',status='Queued')]
            with patch('blender_pipeline.project.workspace.subprocess.Popen') as process:
                process.poll.return_value=None;p.render_processes['owned']=process
                p.stop_render_workers();process.terminate.assert_called_once()
            self.assertEqual(p.data['render_queue'][0]['status'],'Cancelled')
            self.assertIn('owned',p.render_cancelled)
            with patch.object(p,'render_start') as launch:p._queue_loop(p.data['id']);launch.assert_not_called()

    def test_inventory_counts_images_without_logs_and_keeps_gaps_layers_and_passes(self):
        root = Path('project')
        output = root / 'Outputs' / 'Scene' / 'Beauty' / 'Shot_r002'
        run = dict(id='run', output=output.relative_to(root).as_posix(), number=2, status='Cancelled',
                   config=dict(scene='Scene', view_layer='Beauty', start=1, end=5, step=1))
        inventory = SequenceInventory(root / 'Outputs', root, [run])
        for name in ['261004_Scene_Beauty_0001.png', '261004_Scene_Beauty_0002.png',
                     '261004_Scene_Beauty_0004.png', 'render-job.json', 'render.log',
                     'compositor/261004_Scene_Beauty_Mist_0001.exr']:
            inventory.add(output / name)
        groups = inventory.result()
        self.assertEqual(len(groups), 2)
        final = next(g for g in groups if g['kind'] == 'final')
        self.assertEqual(final['images'], 3)
        self.assertEqual(final['ranges'], [[1, 2], [4, 4]])
        self.assertEqual(final['expected_frames'], 5)
        self.assertEqual(final['view_layer'], 'Beauty')
        self.assertEqual(final['version'], 2)
        self.assertEqual(next(g for g in groups if g['kind'] == 'compositor')['images'], 1)
        json.dumps(groups)  # Payload contains compact ranges, no sets or frame-by-frame list.

    def test_large_sequence_is_one_group_and_stepped_range_has_no_false_gaps(self):
        root = Path('project'); output = root / 'Outputs' / 'Shot_r001'
        run = dict(id='run', output='Outputs/Shot_r001', number=1, status='Complete',
                   config=dict(scene='Scene', start=1, end=999, step=2))
        inventory = SequenceInventory(root / 'Outputs', root, [run])
        for frame in range(1, 1000, 2):inventory.add(output / f'scene_{frame:04}.exr')
        result = inventory.result()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['images'], 500)
        self.assertEqual(result[0]['ranges'], [[1, 999]])

    def test_render_refresh_reuses_matching_signature_and_rescans_changed_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'settings').mkdir()
            p = Pipeline(data_directory=root / 'settings'); p.create(root, 'Test')
            file = p.root / 'Shot.blend'; file.write_bytes(b'saved')
            stat = file.stat()
            node = dict(id='shot', type='blend', path='Shot.blend', name='Shot', x=0, y=0,
                        scan=dict(signature=[stat.st_mtime_ns, stat.st_size], refs=[]))
            p.data['nodes'].append(node); p.save()
            with patch.object(p, 'inspect') as scan:
                p.refresh_render_sources(); scan.assert_not_called()
                file.write_bytes(b'changed saved scene')
                p.refresh_render_sources(); scan.assert_called_once_with(node)

    def test_worker_reuses_process_after_success_and_python_failure_and_exits_when_idle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); fake = root / 'worker.py'
            fake.write_text('''import sys,json,os
for line in sys.stdin:
    job=json.loads(line)
    print('PIPELINE_STAGE '+json.dumps({'phase':'Rendering'}),flush=True)
    print('PIPELINE_JOB_END '+json.dumps({'run_id':job['run_id'],'ok':job['run_id']!='failed','pid':os.getpid()}),flush=True)
''')
            popen = subprocess.Popen
            with patch('blender_pipeline.rendering.worker.subprocess.Popen',
                       side_effect=lambda command, **kwargs: popen([sys.executable, '-u', str(fake)], **kwargs)):
                worker = RenderWorker('blender', fake, 'batch')
            try:
                jobs = []
                for identity in ['first', 'failed', 'last']:
                    job = worker.submit(identity, root / 'unused.json', root / (identity + '.log'))
                    self.assertTrue(job.done.wait(5), 'Worker job did not finish')
                    jobs.append(job)
                    self.assertIn('PIPELINE_JOB_END', (root / (identity + '.log')).read_text())
                self.assertEqual([j.poll() for j in jobs], [0, 1, 0])
                self.assertEqual(len({j.pid for j in jobs}), 1)
                self.assertTrue(worker.usable)
            finally:
                worker.close()
            self.assertIsNotNone(worker.process.poll())

    def test_worker_crash_and_cancel_finish_active_job_instead_of_stranding_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); fake = root / 'worker.py'
            fake.write_text('''import sys,json,time
job=json.loads(sys.stdin.readline())
if job['run_id']=='crash':sys.exit(7)
time.sleep(30)
''')
            popen = subprocess.Popen
            for identity in ['crash', 'cancel']:
                with patch('blender_pipeline.rendering.worker.subprocess.Popen',
                           side_effect=lambda command, **kwargs: popen([sys.executable, '-u', str(fake)], **kwargs)):
                    worker = RenderWorker('blender', fake, 'batch')
                try:
                    job = worker.submit(identity, root / 'unused.json', root / (identity + '.log'))
                    if identity == 'cancel':job.terminate()
                    self.assertTrue(job.done.wait(5)); self.assertNotEqual(job.poll(), 0)
                    self.assertFalse(worker.usable)
                finally:worker.close()
