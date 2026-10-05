"""One background Blender process per batch; each setup reloads its frozen file.

Completion belongs to a job, not the lifetime of the reusable process. A crash or
cancellation ends that process; the next queued job starts a fresh worker.
"""
import json
import subprocess
import threading
from blender_pipeline.adapters.background_process import start_background_process, cleanup_background_process


class WorkerJob:
    def __init__(self, session, run_id, log):
        self.session = session
        self.run_id = run_id
        self.stream = log.open('w', encoding='utf-8', buffering=1)
        self.done = threading.Event()
        self.returncode = None
        self.pid = session.process.pid

    def poll(self):
        return self.returncode if self.done.is_set() else None

    def finish(self, code):
        self.returncode = code
        self.stream.close()
        self.done.set()

    def terminate(self):
        self.session.stop()


class RenderWorker:
    def __init__(self, blender, script, batch_id, environment=None):
        self.batch_id = batch_id
        self.current = None
        self.stopped = False
        self.lock = threading.Lock()
        self.process = start_background_process(
            [blender, '--background', '--factory-startup', '--disable-autoexec',
             '--python-exit-code', '1', '--python', str(script)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace', bufsize=1,
            env=environment,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    @property
    def usable(self):
        return not self.stopped and self.process.poll() is None

    def submit(self, run_id, job_path, log):
        with self.lock:
            if not self.usable or self.current:
                raise RuntimeError('Render worker is unavailable or already busy.')
            job = WorkerJob(self, run_id, log)
            self.current = job
            try:
                self.process.stdin.write(json.dumps({'path': str(job_path), 'run_id': run_id}) + '\n')
                self.process.stdin.flush()
            except (OSError, ValueError):
                self.current = None
                job.finish(1)
                raise
            return job

    def _read(self):
        try:
            for line in self.process.stdout:
                with self.lock:
                    job = self.current
                    if not job:
                        continue
                    job.stream.write(line)
                    if line.startswith('PIPELINE_JOB_END '):
                        try:
                            result = json.loads(line[len('PIPELINE_JOB_END '):])
                            if result['run_id'] == job.run_id:
                                self.current = None
                                job.finish(0 if result['ok'] else 1)
                        except (ValueError, KeyError, TypeError):
                            pass
        finally:
            code = self.process.wait()
            with self.lock:
                self.stopped = True
                if self.current:
                    self.current.finish(code or 1)
                    self.current = None
            self.process.stdout.close()
            cleanup_background_process(self.process)

    def stop(self):
        self.stopped = True
        if self.process.poll() is None:
            self.process.terminate()

    def close(self):
        self.stopped = True
        try:
            self.process.stdin.close()
            self.process.wait(timeout=5)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            self.stop()
        self.reader.join(timeout=5)
