"""Run the actual add-on in Blender against a disposable HTTP application."""
import tempfile,threading,subprocess,zipfile,time,json
from pathlib import Path
from blender_pipeline.http import server
from blender_pipeline.bootstrap import create_application
import secrets
from blender_pipeline.application.commands import Application
from blender_pipeline.project.model import digest
from support import ROOT, WORKERS, FIXTURES
with tempfile.TemporaryDirectory(prefix='companion-test-') as directory:
    root=Path(directory);app=create_application(root/'settings');model,tasks,bridge=app.model,app.tasks,app.bridge;token=secrets.token_urlsafe(32)
    model.registry=root/'recent.json';model.global_template_config=root/'app-startup.json'
    addon_archive=app.addon_archive
    fixtures=root/'library-fixtures'
    model.run(str(FIXTURES/'link_workflow_fixture.py'),[fixtures])
    http=server.create_server(app,token)
    thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    connection=bridge.publish(http.server_port,token,root/'connection.json')
    client=root/'client';client.mkdir()
    with zipfile.ZipFile(addon_archive) as archive:archive.extractall(client)
    result=subprocess.run([model.blender,'--background','--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(FIXTURES/'companion_fixture.py'),'--',str(client),str(connection),str(root/'From Blender'),str(fixtures)],capture_output=True,text=True,errors='replace',timeout=180)
    print(result.stdout[-3000:]);print(result.stderr[-1200:])
    assert result.returncode==0,'Companion Blender fixture failed'
    limit=time.monotonic()+60
    while model.render_busy() and time.monotonic()<limit:time.sleep(.2)
    assert model.data['render_queue'][-1]['status']=='Complete',model.data['render_queue']
    assert len(model.data['renders'])==2
    first,second=model.data['renders']
    assert first['output']!=second['output'] and first['number']==1 and second['number']==2
    assert len(list((model.root/first['output']).glob('*.png')))==1
    assert len(list((model.root/second['output']).glob('*.png')))==2
    for run in model.data['renders']:
        assert run['actual_settings']['width']==64 and run['actual_settings']['samples']==1,run['actual_settings']
        assert run['config']['auto_prefix'] and run['config']['prefix'].endswith('_Scene_')
        assert run['config']['percentage'] is None
    working=next(n for n in model.data['nodes'] if n['name']=='Working')
    assert len(working['snapshots'])>=7 and len(working['scan']['instances'])>=2 and working['scan']['data_links']
    http.shutdown();http.server_close();tasks.pool.shutdown()
print('PASS: actual Blender companion end-to-end, checkpointed current-frame and animation CPU renders, isolated versions and inherited saved settings')
