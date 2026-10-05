"""Headless GPU selection and terminal queue states must be explicit."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from blender_pipeline.blender.render_devices import configure
from blender_pipeline.project.workspace import Pipeline
from blender_pipeline.rendering.progress import read_markers


class Devices:
    def __init__(self, backend='NONE', available=None):
        self.compute_device_type=backend
        self.available=available or {}
        self.devices=[d for devices in self.available.values() for d in devices]
    def get_device_types(self, context):return [(b,) for b in self.available]
    def get_devices_for_type(self, backend):return self.available[backend]


class RenderExecutionTests(unittest.TestCase):
    def scene(self, device='GPU', engine='CYCLES'):
        return SimpleNamespace(render=SimpleNamespace(engine=engine),cycles=SimpleNamespace(device=device))

    def test_factory_worker_uses_available_gpu_and_leaves_cpu_scene_alone(self):
        cpu=SimpleNamespace(name='CPU',type='CPU',use=True)
        gpu=SimpleNamespace(name='RTX',type='OPTIX',use=False)
        prefs=Devices(available={'OPTIX':[gpu,cpu]})
        result=configure(self.scene(),prefs)
        self.assertEqual(result['effective'],'GPU');self.assertEqual(result['devices'],['RTX'])
        self.assertEqual(prefs.compute_device_type,'OPTIX');self.assertTrue(gpu.use);self.assertFalse(cpu.use)
        before=copy.deepcopy(result)
        result=configure(self.scene('CPU'),prefs)
        self.assertEqual(result['effective'],'CPU');self.assertEqual(prefs.compute_device_type,'OPTIX')
        self.assertEqual(before['requested'],'GPU')

    def test_unavailable_backend_uses_next_supported_gpu(self):
        cuda=SimpleNamespace(name='CUDA GPU',type='CUDA',use=False)
        prefs=Devices(available={'OPTIX':[],'CUDA':[cuda]})
        self.assertEqual(configure(self.scene(),prefs)['backend'],'CUDA')

    def test_no_gpu_and_disabled_existing_selection_report_cpu_fallback(self):
        scene=self.scene();result=configure(scene,Devices())
        self.assertEqual(result['effective'],'CPU');self.assertTrue(result['warnings'])
        self.assertEqual(scene.cycles.device,'GPU','Never change the saved scene device setting.')
        gpu=SimpleNamespace(name='Disabled',type='CUDA',use=False)
        prefs=Devices('CUDA',{'CUDA':[gpu]})
        self.assertEqual(configure(scene,prefs)['effective'],'CPU');self.assertFalse(gpu.use)
        self.assertEqual(configure(self.scene(engine='BLENDER_EEVEE'),prefs)['effective'],'BLENDER_EEVEE')

    def test_stage_device_and_stepped_frame_progress_survive_malformed_log_lines(self):
        run={'config':{'start':1,'end':5,'step':2}}
        read_markers(['PIPELINE_STAGE {"phase":"Rendering","frame":3}',
                      'PIPELINE_DEVICE {"effective":"GPU","backend":"OPTIX"}',
                      'PIPELINE_FRAME {"frame":1}', 'PIPELINE_FRAME {"frame":1}',
                      'PIPELINE_FRAME not-json', 'PIPELINE_FRAME {"frame":3}'],run)
        self.assertEqual(run['phase'],'Rendering');self.assertEqual(run['current_frame'],3)
        self.assertEqual(run['render_device']['backend'],'OPTIX');self.assertEqual(run['progress'],66)
        self.assertEqual(run['written_frames'],[1,3])

    def test_worker_exit_without_output_is_failed_and_releases_its_process(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory)/'settings').mkdir()
            p=Pipeline(data_directory=Path(directory)/'settings');p.create(directory,'Test');p.folder('Outputs')
            run={'id':'run','project_id':p.data['id'],'node_id':'file','status':'Rendering','output':'Outputs',
                 'inputs':'.pipeline/inputs','config':{'start':1,'end':1}}
            p.data['renders']=[run];log=p.root/'Outputs'/'render.log';log.write_text('PIPELINE_STAGE {"phase":"Rendering"}\n')
            process=SimpleNamespace(returncode=0,poll=lambda:0);p.render_processes['run']=process
            p.monitor_render(run,process,log)
            self.assertEqual(run['status'],'Failed');self.assertIn('without saving',run['error'])
            self.assertNotIn('run',p.render_processes);self.assertFalse(p.render_busy())
            self.assertEqual(json.loads((p.root/'.pipeline/project.json').read_text())['renders'][0]['status'],'Failed')
            # A missing log must not strand a crashed worker as Rendering.
            run.update(status='Rendering');process.returncode=7;log.unlink();p.monitor_render(run,process,log)
            self.assertEqual(run['status'],'Failed');self.assertIn('code 7',run['error'])

    def test_queue_attempts_each_setup_once_even_when_first_render_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory)/'settings').mkdir()
            p=Pipeline(data_directory=Path(directory)/'settings');p.create(directory,'Queue')
            p.data['render_queue']=[{'id':str(i),'node_id':'file','project_id':p.data['id'],'expected_inputs':{},'status':'Queued'} for i in range(2)]
            calls=[]
            def execute(*args,**kwargs):
                calls.append(args[0]);p.data.setdefault('renders',[]).append({'id':str(len(calls)), 'status':'Failed' if len(calls)==1 else 'Complete','error':'test failure' if len(calls)==1 else ''})
            p.render_start=execute;p._queue_loop(p.data['id'])
            self.assertEqual(len(calls),2);self.assertEqual([q['status'] for q in p.data['render_queue']],['Failed','Complete'])
            self.assertIsNone(p.queue_worker);self.assertFalse(p.render_busy())
