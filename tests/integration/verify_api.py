"""Loopback integration tests run within one Python process."""
import uuid
from blender_pipeline.application.commands import Application
import json, socket, tempfile, threading, urllib.request, urllib.error
from pathlib import Path
from blender_pipeline.http import server
from blender_pipeline.bootstrap import create_application
import secrets
from blender_pipeline.project.model import digest
from support import ROOT, WORKERS, FIXTURES

with tempfile.TemporaryDirectory(prefix='api-test-') as directory:
    app=create_application(Path(directory)/'settings')
    model,tasks,bridge=app.model,app.tasks,app.bridge
    token=secrets.token_urlsafe(32)
    model.registry=Path(directory)/'recent.json'
    model.global_template_config=Path(directory)/'app-startup.json'
    http=server.create_server(app,token)
    threading.Thread(target=http.serve_forever,daemon=True).start()
    url=f'http://127.0.0.1:{http.server_port}'
    def call(action,args):
        if action not in {'state','projects','ui_preferences','settings','browse_directory','choose_system_path','companion_heartbeat','companion_goodbye'}:
            args={**args,'request_id':uuid.uuid4().hex}
            if model.data:args.update(project_id=model.data['id'],expected_revision=model.data['revision'])
        req=urllib.request.Request(url+'/'+action,data=json.dumps(args).encode(),headers={'X-Pipeline-Token':token,'Content-Type':'application/json'})
        return json.loads(urllib.request.urlopen(req,timeout=180).read())
    try:
        idle=socket.create_connection(('127.0.0.1',http.server_port))
        html=urllib.request.urlopen(url+'/').read().decode()
        idle.close()
        js=urllib.request.urlopen(url+'/js/ui.js').read().decode()
        assert '__TOKEN__' not in html and "quickCreate" in js and 'autoRefresh' in html
        assert b'Preserve navigation' in urllib.request.urlopen(url+'/js/usability.js').read()
        # Preferences must persist beyond a launch port, without touching real UI settings.
        prefs={'navigator':True,'inspector':False,'width':420}
        assert call('ui_preferences',prefs)==prefs
        assert call('ui_preferences',{'read':True})==prefs
        try:call('ui_preferences',{**prefs,'width':900})
        except urllib.error.HTTPError as exc:assert exc.code==400
        else:raise AssertionError('Invalid panel width was accepted')
        assert call('ui_preferences',{'read':True})==prefs
        call('create',{'parent':directory,'title':'API Project'})
        result=call('blend',{'x':234,'y':345})
        node=result['project']['nodes'][-1]
        assert all('advanced_settings' not in s for s in node['scan']['scenes'])
        render_settings=call('read_render_settings',{'node_id':node['id']})
        assert any(len(entries)>100 for entries in render_settings['scenes'].values())
        assert b'advancedSettingsEditor' in urllib.request.urlopen(url+'/js/render_settings_ui.js').read()
        assert b'renderWorkspace' in urllib.request.urlopen(url+'/css/render_workspace.css').read()
        assert node['name']=='Untitled 001' and node['x']==234 and node['y']==345
        call('label',{'node_id':node['id'],'title':'Asset display label'})
        result=call('refresh',{'node_id':node['id']})
        assert result['project']['nodes'][0]['scan']['collection_details'][0]['objects']==0
        assert not result['files'][node['id']]['changed']
        listing=call('browse_directory',{'path':str(Path(directory)/'API Project'),'extension':'.blend'})
        assert any(r['name']=='Untitled 001.blend' for r in listing['entries'])
        project=call('projects',{})['projects'][0]
        assert call('projects',{'mode':'pin','path':project['path']})['projects'][0]['pinned']
        assert not call('projects',{'mode':'remove','path':project['path']})['projects']
        assert Path(project['path']).is_dir()
        assert call('projects',{'mode':'restore','entry':project})['projects'][0]['available']
        call('companion_heartbeat',{'session_id':'api-open-file','file':str(Path(project['path'])/node['path']),'dirty':True})
        state=call('state',{})
        assert node['id'] in state['open'] and state['live'][0]['dirty']
        try:model.archive_blend(node['id'],True)
        except ValueError:pass
        else:raise AssertionError('Companion-reported open file was archived')
        call('companion_goodbye',{'session_id':'api-open-file'})
        assert node['id'] not in call('state',{})['open']
        try:
            urllib.request.urlopen(urllib.request.Request(url+'/blend',data=b'{}'),timeout=5)
        except urllib.error.HTTPError as exc:assert exc.code==403
        else:raise AssertionError('Missing request token was accepted')
        print('PASS: HTML/JS serving, one-click create API, placement, labels, single refresh, file-change status and request token.')
    finally:http.shutdown();http.server_close();tasks.pool.shutdown()
