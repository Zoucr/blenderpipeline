import tempfile
from pathlib import Path
from blender_pipeline.project.workspace import Pipeline
from blender_pipeline.storage.file_references import FileResolver
from blender_pipeline.project.model import digest
from support import ROOT, WORKERS, FIXTURES
with tempfile.TemporaryDirectory() as temp:
    root=Path(temp);p=Pipeline(resolver=FileResolver(root/'settings'));p.registry=root/'recent.json';p.create(root,'Project')
    external=root/'Outside';p.run(str(FIXTURES/'external_fixture.py'),[external])
    hashes={str(f):digest(f) for f in external.glob('*.blend')}
    p.external_register(str(external/'Outer.blend'));outer=next(n for n in p.data['nodes'] if n['name']=='Outer')
    assert len([n for n in p.data['nodes'] if n.get('external')])==2
    assert len(outer['scan']['collection_details'])>=81
    p.graph_edit(outer['id'],pinned_collections=['Outer','Outer']);assert outer['pinned_collections']==['Outer']
    try:p.duplicate(outer['id']);raise AssertionError('external write allowed')
    except ValueError:pass
    p.create_blend('Shot');shot=p.data['nodes'][-1];p.link(outer['id'],shot['id'],'Outer',True)
    assert any(not r['inside'] for r in shot['scan']['refs'])
    assert p.preflight()
    p.localize_external(outer['id'],True)
    assert not any(n.get('external') for n in p.data['nodes'])
    assert not p.preflight(),p.preflight()
    assert all(digest(f)==h for f,h in hashes.items())
    assert all(r['inside'] and r['exists'] and r['relative'] for n in p.data['nodes'] for r in n['scan']['refs'])
    assert shot['snapshots'] and p.data['path_aliases']
    p.run(str(FIXTURES/'test_fixture.py'),[p.path(shot),'check','Outer','1'])
    checkpoint=shot['snapshots'][-1]['id'];p.restore(shot['id'],checkpoint,True)
    assert not p.preflight(),p.preflight()
    q=Pipeline(resolver=FileResolver(root/'settings'));q.registry=root/'reload.json';q.load(p.root)
    assert not q.preflight() and q.node(outer['id'])['pinned_collections']==['Outer']
print('PASS: nested external discovery, read-only guards, many collections, pins, real external links, dependency collection and repaired paths; originals unchanged')
