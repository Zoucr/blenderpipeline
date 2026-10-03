"""Local foundations: conflicts, identity, request recovery, and portable locations."""
import copy
import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from blender_pipeline.application.commands import Application
from blender_pipeline.adapters.companion_bridge import Bridge
from blender_pipeline.project.workspace import Pipeline
from blender_pipeline.storage.file_references import FileResolver
from blender_pipeline.application.operations import OperationJournal
from blender_pipeline.storage.projects import JsonProjectRepository, RevisionConflict
from blender_pipeline.application.tasks import Tasks


class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory=Path(self.temporary.name)
        self.settings=self.directory/'settings'
        self.p=Pipeline(resolver=FileResolver(self.settings))
        self.p.registry=self.directory/'recent.json'
        self.p.global_template_config=self.directory/'startup.json'
        self.p.create(self.directory,'Project')
        self.tasks=Tasks(self.p)
        self.addCleanup(self.tasks.pool.shutdown)
        self.bridge=Bridge(self.p);self.bridge.tasks=self.tasks
        self.app=Application(self.p,self.tasks,self.bridge,self.settings)

    def envelope(self,request_id,**args):
        return {'project_id':self.p.data['id'],'expected_revision':self.p.data['revision'],'request_id':request_id,**args}

    def wait(self):
        self.tasks.pool.submit(lambda:None).result(timeout=10)

    def test_missing_and_wrong_project_are_rejected_before_side_effects(self):
        for args in ({'title':'Nope'},self.envelope('wrong',title='Nope',project_id='other')):
            with self.assertRaises(ValueError):self.app.dispatch('folder',args)
        self.assertFalse((self.p.root/'Nope').exists())
        with self.assertRaisesRegex(ValueError,'revision'):
            self.app.dispatch('folder',{'project_id':self.p.data['id'],'request_id':'missing-revision','title':'Nope'})

    def test_stale_direct_write_never_clobbers_or_bumps_revision(self):
        self.p.folder('Folder');node=self.p.data['nodes'][0]
        old=self.envelope('stale',node_id=node['id'],title='Old')
        self.app.dispatch('label',self.envelope('first',node_id=node['id'],title='New'))
        original=(self.p.root/'.pipeline/project.json').read_bytes()
        with self.assertRaises(RevisionConflict):self.app.dispatch('label',old)
        self.assertEqual((self.p.root/'.pipeline/project.json').read_bytes(),original)
        self.assertEqual(self.p.node(node['id'])['name'],'New')

    def test_repository_compare_and_save_has_one_winner(self):
        a=copy.deepcopy(self.p.data);b=copy.deepcopy(a)
        a['name']='A';b['name']='B'
        barrier=threading.Barrier(2)
        def write(data):
            barrier.wait()
            try:JsonProjectRepository().save(self.p.root,data);return True
            except RevisionConflict:return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(write,(a,b)))
        self.assertEqual(sorted(results),[False,True])
        self.assertEqual(JsonProjectRepository().load(self.p.root)['revision'],self.p.data['revision']+1)

    def test_disk_conflict_is_checked_before_creating_folder(self):
        other=copy.deepcopy(self.p.data);other['name']='Edited elsewhere'
        JsonProjectRepository().save(self.p.root,other)
        with self.assertRaises(RevisionConflict):self.app.dispatch('folder',self.envelope('disk',title='Never created'))
        self.assertFalse((self.p.root/'Never created').exists())

    def test_conflict_keeps_active_render_record_identity(self):
        run={'id':'run','project_id':self.p.data['id'],'status':'Rendering'}
        item={'id':'item','status':'Rendering','run_id':'run'}
        self.p.data['renders']=[run];self.p.data['render_queue']=[item];self.p.save()
        request=self.envelope('render-conflict',title='Never created')
        self.p.save()
        with self.assertRaises(RevisionConflict):self.app.dispatch('folder',request)
        self.assertIs(self.p.data['renders'][0],run);self.assertIs(self.p.data['render_queue'][0],item)
        run['status']='Complete';item['status']='Complete';self.p.save()
        self.assertEqual(JsonProjectRepository().load(self.p.root)['renders'][0]['status'],'Complete')

    def test_queued_retry_returns_same_job_even_after_completion_and_restart(self):
        request=self.envelope('same-request',action='folder',title='Only once')
        first=self.app.dispatch('async',request)
        self.wait()
        self.assertEqual(self.tasks.jobs[first['job']]['status'],'Complete')
        second=self.app.dispatch('async',request)
        self.assertEqual(first['job'],second['job'])
        self.assertEqual(len(self.p.data['nodes']),1)
        other_tasks=Tasks(self.p);self.addCleanup(other_tasks.pool.shutdown)
        other=Application(self.p,other_tasks,self.bridge,self.settings)
        third=other.dispatch('async',request)
        self.assertEqual(third['job'],first['job'])
        with self.assertRaisesRegex(ValueError,'different arguments'):
            other.dispatch('async',{**request,'title':'Different'})
        self.assertFalse((self.p.root/'Different').exists())

    def test_simultaneous_request_registration_has_one_owner(self):
        journal=OperationJournal(self.settings/'race')
        barrier=threading.Barrier(2)
        def submit(number):
            barrier.wait()
            return journal.reserve({'id':str(number),'project_id':'p','request_id':'r','fingerprint':'same','status':'Queued'})
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(submit,(1,2)))
        self.assertEqual(sum(created for _,created in results),1)
        self.assertEqual(results[0][0]['id'],results[1][0]['id'])

    def test_queued_job_revalidates_context_at_execution(self):
        gate=threading.Event();self.tasks.pool.submit(lambda:gate.wait(5))
        original=self.p.data['id'];response=self.app.dispatch('async',self.envelope('context',action='folder',title='Wrong target'))
        self.p.create(self.directory,'Other')
        gate.set();self.wait()
        job=self.tasks.jobs[response['job']]
        self.assertEqual(job['status'],'Failed');self.assertEqual(job['project_id'],original)
        self.assertEqual(job['error_code'],'project_context_changed')
        self.assertFalse((self.p.root/'Wrong target').exists());self.assertEqual(self.p.data['nodes'],[])

    def test_restart_marks_uncertain_jobs_without_replaying(self):
        self.app.journal.reserve({'id':'uncertain','project_id':self.p.data['id'],'request_id':'u','fingerprint':'f','action':'folder','args':{'title':'No replay'},'status':'Running','error':''})
        self.tasks.configure_journal(self.app.journal)
        self.assertEqual(self.tasks.jobs['uncertain']['status'],'Interrupted')
        self.assertFalse((self.p.root/'No replay').exists())

    def test_personal_views_are_separate_and_do_not_change_shared_revision(self):
        self.p.folder('Folder');node=self.p.data['nodes'][0];revision=self.p.data['revision']
        self.app.dispatch('layout',self.envelope('layout-a',client_id='a',nodes=[{'id':node['id'],'x':node['x'],'y':node['y']}],view={'x':40,'y':50,'zoom':2}))
        self.app.dispatch('project_view',{'project_id':self.p.data['id'],'client_id':'a','selected':node['id'],'tab':'history'})
        a=self.app.dispatch('state',{'client_id':'a'});b=self.app.dispatch('state',{'client_id':'b'})
        self.assertEqual(a['project']['view'],{'x':40,'y':50,'zoom':2})
        self.assertEqual(b['project']['view'],{'x':0,'y':0,'zoom':1})
        self.assertEqual(a['view_state']['selected'],node['id']);self.assertNotIn('selected',b['view_state'])
        self.assertEqual(self.p.data['revision'],revision)
        disk=json.loads((self.p.root/'.pipeline/project.json').read_text())
        self.assertEqual(disk['view'],{'x':0,'y':0,'zoom':1});self.assertNotIn('selected',disk)

    def test_panel_preferences_are_per_client_and_preserve_project_view(self):
        self.app.dispatch('project_view',{'project_id':self.p.data['id'],'client_id':'a','selected':'file','tab':'history'})
        self.app.dispatch('ui_preferences',{'client_id':'a','navigator':True,'inspector':False,'width':400})
        self.assertEqual(self.app.dispatch('ui_preferences',{'client_id':'a','read':True})['width'],400)
        self.assertEqual(self.app.dispatch('ui_preferences',{'client_id':'b','read':True}),{})
        self.assertEqual(self.app.dispatch('state',{'client_id':'a'})['view_state']['tab'],'history')

    def test_personal_navigation_does_not_wait_on_worker_lock(self):
        with self.p.lock:
            with ThreadPoolExecutor(max_workers=1) as pool:
                response=pool.submit(self.app.dispatch,'project_view',{'project_id':self.p.data['id'],'client_id':'a','selected':'file'})
                self.assertEqual(response.result(timeout=1)['selected'],'file')

    def test_http_etag_and_stale_if_match(self):
        import urllib.request
        import urllib.error
        from blender_pipeline.http.server import create_server
        self.p.folder('Folder');node=self.p.data['nodes'][0]
        http=create_server(self.app,'test-token')
        thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
        def call(action,args,tag=None):
            headers={'X-Pipeline-Token':'test-token','Content-Type':'application/json'}
            if tag:headers['If-Match']=tag
            req=urllib.request.Request(f'http://127.0.0.1:{http.server_port}/{action}',data=json.dumps(args).encode(),headers=headers)
            return urllib.request.urlopen(req,timeout=10)
        try:
            with call('state',{}) as response:tag=response.headers['ETag']
            with call('label',{'project_id':self.p.data['id'],'request_id':'http-a','node_id':node['id'],'title':'New'},tag) as response:
                self.assertNotEqual(response.headers['ETag'],tag)
            with self.assertRaises(urllib.error.HTTPError) as caught:
                call('label',{'project_id':self.p.data['id'],'request_id':'http-b','node_id':node['id'],'title':'Old'},tag)
            self.assertEqual(caught.exception.code,412)
            self.assertEqual(json.loads(caught.exception.read())['code'],'revision_conflict')
            self.assertEqual(self.p.node(node['id'])['name'],'New')
        finally:http.shutdown();http.server_close();thread.join(5)

    def test_managed_identity_survives_a_different_root(self):
        self.p.folder('Assets');node=self.p.data['nodes'][0];ref=self.p.resolver.reference(node)
        other=self.directory/'Moved';other.mkdir()
        self.assertEqual(self.p.resolver.resolve(other,self.p.data['id'],node),other/'Assets')
        self.assertEqual(ref['file_id'],node['id']);self.assertEqual(ref['relative_path'],'Assets')
        for raw in ('../outside','C:\\outside','/outside','.pipeline/history/file.blend'):
            with self.assertRaises(ValueError):self.p.resolver.resolve(self.p.root,self.p.data['id'],{**node,'path':raw})

    def test_external_locations_are_local_and_can_be_remapped(self):
        external=self.directory/'Outside';external.mkdir();(external/'Asset.blend').write_bytes(b'fixture')
        node={'id':'external-file','external':True,'type':'blend','name':'Asset','path':str(external/'Asset.blend'),'x':0,'y':0,'scan':{'refs':[]}}
        self.p.data['nodes'].append(node);self.p.save()
        self.assertEqual(node['path'],'Asset.blend')
        self.assertEqual(self.p.path(node),external/'Asset.blend')
        shared=json.loads((self.p.root/'.pipeline/project.json').read_text())
        self.assertNotIn(str(external),json.dumps(shared))
        missing=FileResolver(self.directory/'another-machine')
        with self.assertRaisesRegex(ValueError,'location unavailable'):missing.resolve(self.p.root,self.p.data['id'],node)
        original=self.p.resolver;self.p.resolver=missing
        self.assertTrue(self.p.state()['files'][node['id']]['missing'])
        moved=self.directory/'Elsewhere';moved.mkdir();(moved/'Asset.blend').write_bytes(b'fixture')
        missing.map_location(self.p.data['id'],node['storage_id'],moved)
        self.assertEqual(missing.resolve(self.p.root,self.p.data['id'],node),moved/'Asset.blend')
        self.p.resolver=original

    def test_render_manifest_detects_input_changes_before_launch(self):
        self.p.folder('Outputs');folder=self.p.data['nodes'][0]
        file=self.p.root/'Shot.blend';file.write_bytes(b'first')
        node={'id':'shot','type':'blend','name':'Shot','path':'Shot.blend','scan':{'refs':[],'scenes':[{'name':'Scene','camera':'Camera','cameras':['Camera'],'start':1,'end':1,'engine':'CYCLES'}]},'render_config':{'folder_id':folder['id'],'scene':'Scene','camera':'Camera','start':1,'end':1},'x':0,'y':0}
        self.p.data['nodes'].append(node);self.p.save()
        with patch.object(self.p,'refresh',return_value=self.p.state()),patch('blender_pipeline.rendering.queue.threading.Thread'):
            self.p.queue_render('shot',overrides={'samples':8})
        item=self.p.data['render_queue'][0]
        self.assertEqual(item['effective_settings']['samples'],8)
        self.assertEqual(item['file_ref']['file_id'],'shot')
        file.write_bytes(b'changed')
        with patch.object(self.p,'render_start') as launch:
            self.p._queue_loop(self.p.data['id'])
            launch.assert_not_called()
        self.assertEqual(item['status'],'Failed');self.assertIn('input changed',item['error'])

    def test_render_input_changed_since_scan_is_not_captured_as_old_settings(self):
        file=self.p.root/'Shot.blend';file.write_bytes(b'new saved state')
        node={'id':'shot','type':'blend','name':'Shot','path':'Shot.blend','scan':{'refs':[],'signature':[0,0]},'x':0,'y':0}
        self.p.data['nodes'].append(node);self.p.save()
        with self.assertRaisesRegex(ValueError,'changed after scanning'):self.p.capture_render_inputs(node)


if __name__=='__main__':unittest.main()
