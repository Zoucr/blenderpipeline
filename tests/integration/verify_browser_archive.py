"""Real Blender archive recovery and read-only path browsing regression checks."""
import json,tempfile
from pathlib import Path
from blender_pipeline.project.workspace import Pipeline
from blender_pipeline.project.model import digest,atomic_json
from support import ROOT, WORKERS, FIXTURES
from blender_pipeline.adapters.file_browser import browse_directory

with tempfile.TemporaryDirectory() as temp:
    root=Path(temp);p=Pipeline();p.registry=root/'recent.json';p.create(root,'Archive Test')
    p.create_blend('Models');source=p.data['nodes'][-1]
    p.run(str(FIXTURES/'test_fixture.py'),[p.path(source),'populate']);p.refresh()
    p.create_blend('Shot');shot=p.data['nodes'][-1];p.link(source['id'],shot['id'],'Collection',True)
    try:p.archive_blend(source['id'],True);raise AssertionError('Used source archived')
    except ValueError as exc:assert 'used by' in str(exc)
    try:p.archive_blend(shot['id'],False);raise AssertionError('Missing close confirmation accepted')
    except ValueError:pass
    saved_hash=digest(p.path(shot));old_path=p.path(shot);sid=shot['snapshots'][0]['id']
    p.archive_blend(shot['id'],True);record=p.data['archived_files'][0]
    assert not old_path.exists() and digest(p.root/record['path'])==saved_hash
    assert not any(n['id']==shot['id'] for n in p.data['nodes'])
    q=Pipeline();q.registry=p.registry;q.load(p.root);q.restore_archived(record['id'])
    restored=q.node(shot['id']);assert digest(q.path(restored))==saved_hash
    assert restored['snapshots'][0]['id']==sid and restored['scan']['instances']
    q.run(str(FIXTURES/'test_fixture.py'),[q.path(restored),'check','Collection','2'])
    # Restore refuses to overwrite a replacement at the original path.
    q.archive_blend(shot['id'],True);rid=q.data['archived_files'][0]['id'];old_path.write_bytes(b'replacement')
    try:q.restore_archived(rid);raise AssertionError('Occupied path overwritten')
    except ValueError:assert old_path.read_bytes()==b'replacement'
    old_path.unlink();q.restore_archived(rid)
    (root/'ignore.txt').write_text('kept');(root/'Example.BLEND').write_bytes(b'fixture')
    result=browse_directory(str(root),'.blend','example');assert result['entries'][0]['name']=='Example.BLEND'
    assert browse_directory(str(root/'Example.BLEND'),'.blend')['path']==str(root.resolve())
    atomic_json(q.registry,[{'name':f'Project {i}','path':str(root/f'p{i}')} for i in range(30)])
    q.remember();assert len(q.recent())==31
    print('PASS: linked-source guard, close confirmation, archive/reopen/restore, stable history, real linked geometry, overwrite protection, browsing filters, and 31 retained projects.')
