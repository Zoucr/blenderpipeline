"""Blender startup artifacts stay disposable on success, failure and cancellation."""
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from blender_pipeline.adapters.background_process import start_background_process
from blender_pipeline.adapters.blender_runtime import BlenderRuntime
from blender_pipeline.project.workspace import Pipeline
from blender_pipeline.rendering.worker import RenderWorker


class BackgroundProcessTests(unittest.TestCase):
    def test_operations_remove_incidental_files_on_success_failure_and_timeout(self):
        directories = []
        for outcome in ('success', 'failure', 'timeout'):
            def runner(command, **options):
                directory = Path(options['cwd']); directories.append(directory)
                self.assertNotEqual(directory, Path.cwd())
                (directory / 'garbled' / '.thumbnails' / 'large').mkdir(parents=True)
                if outcome == 'timeout':
                    raise subprocess.TimeoutExpired(command, options['timeout'])
                return SimpleNamespace(returncode=int(outcome == 'failure'), stdout='failure', stderr='')
            runtime = BlenderRuntime(Path(__file__).parent, runner=runner)
            if outcome == 'success':
                runtime.run('blender', 'scan.py', [])
            else:
                with self.assertRaises(subprocess.TimeoutExpired if outcome == 'timeout' else ValueError):
                    runtime.run('blender', 'scan.py', [])
            self.assertFalse(directories[-1].exists())

    def test_spawn_failure_also_cleans_its_working_directory(self):
        directories = []
        def fail(command, **options):
            directory = Path(options['cwd']); directories.append(directory)
            (directory / 'startup-cache').mkdir()
            raise FileNotFoundError('Blender missing')
        with patch('blender_pipeline.adapters.background_process.subprocess.Popen', side_effect=fail):
            with self.assertRaises(FileNotFoundError):
                start_background_process(['missing-blender'])
        self.assertFalse(directories[0].exists())

    def test_reused_worker_keeps_its_directory_until_exit_then_cleans_it(self):
        code = """import json,sys
from pathlib import Path
Path('garbled/.thumbnails/large').mkdir(parents=True)
for line in sys.stdin:
    request=json.loads(line)
    print('PIPELINE_JOB_END '+json.dumps({'run_id':request['run_id'],'ok':True}),flush=True)
"""
        def start(command, **options):
            return start_background_process([sys.executable, '-u', '-c', code], **options)
        with tempfile.TemporaryDirectory() as temporary, patch('blender_pipeline.rendering.worker.start_background_process', side_effect=start):
            worker = RenderWorker('blender', 'worker.py', 'batch')
            directory = Path(worker.process._pipeline_directory.name)
            try:
                for index in range(2):
                    job = worker.submit(str(index), Path(temporary) / 'job.json', Path(temporary) / f'{index}.log')
                    self.assertTrue(job.done.wait(5)); self.assertEqual(job.returncode, 0)
                    self.assertTrue(directory.exists(), 'a reused worker owns its directory between setups')
            finally:
                worker.close()
            self.assertFalse(directory.exists())
            cancelled = RenderWorker('blender', 'worker.py', 'cancelled')
            directory = Path(cancelled.process._pipeline_directory.name)
            cancelled.stop(); cancelled.reader.join(timeout=5)
            self.assertFalse(cancelled.reader.is_alive()); self.assertFalse(directory.exists())
            cancelled.close()

    def test_single_render_monitor_cleans_even_when_project_context_changed(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = Path(temporary) / 'settings'; settings.mkdir()
            pipeline = Pipeline(data_directory=settings); pipeline.create(temporary, 'Project')
            log = Path(temporary) / 'render.log'; log.write_text('')
            process = start_background_process([sys.executable, '-c', "from pathlib import Path; Path('garbled/.thumbnails/large').mkdir(parents=True)"])
            directory = Path(process._pipeline_directory.name)
            process.wait(timeout=5)
            pipeline.monitor_render({'project_id':'previous-project'}, process, log)
            self.assertFalse(directory.exists())

    def test_interpreter_exit_stops_an_idle_child_before_tempfile_finalization(self):
        code = """import json,sys
from blender_pipeline.adapters.background_process import start_background_process
p=start_background_process([sys.executable,'-c','import time; time.sleep(60)'])
print(json.dumps({'cwd':p._pipeline_directory.name,'pid':p.pid}),flush=True)
"""
        result = subprocess.run([sys.executable, '-B', '-c', code], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '', 'shutdown must not race Tempfile cleanup against a live Blender worker')
        import json
        directory = Path(json.loads(result.stdout)['cwd'])
        self.assertFalse(directory.exists())


if __name__ == '__main__':
    unittest.main()
