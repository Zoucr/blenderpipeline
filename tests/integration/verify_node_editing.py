"""Real copied libraries, material overrides, nested folders and file renames."""
import json
from pathlib import Path
import tempfile

from blender_pipeline.project.workspace import Pipeline
from blender_pipeline.project.model import digest
from support import FIXTURES


with tempfile.TemporaryDirectory(prefix='pipeline-node-editing-') as temporary:
    base = Path(temporary)
    (base / 'settings').mkdir()
    p = Pipeline(data_directory=base / 'settings')
    p.create(base, 'Clipboard Test')
    p.run(FIXTURES / 'collection_materials_fixture.py', [p.root])
    p.import_blend(p.root / 'Source.blend'); source = p.data['nodes'][-1]
    p.import_blend(p.root / 'override.blend'); shot = p.data['nodes'][-1]
    original = {n['id']: digest(p.path(n)) for n in [source, shot]}
    p.duplicate(shot['id']); lone = p.data['nodes'][-1]
    assert lone['name'] == 'override 01' and digest(p.path(lone)) == original[shot['id']]
    assert any(Path(r['path']).resolve() == p.path(source) for r in lone['scan']['refs'] if r['kind'] == 'Library')
    before = {n['id'] for n in p.data['nodes']}
    p.paste_nodes([source['id'], shot['id']], clipboard_project_id=p.data['id'])
    pair = {n['name']: n for n in p.data['nodes'] if n['id'] not in before}
    assert any(Path(r['path']).resolve() == p.path(pair['Source 01']) for r in pair['override 02']['scan']['refs'] if r['kind'] == 'Library')
    assert all(digest(p.path(p.node(i))) == h for i, h in original.items())
    p.folder('Assets'); folder = p.data['nodes'][-1]
    p.relocate(source['id'], folder['id'], 'Models', closed=True)
    p.relocate(shot['id'], folder['id'], 'Lighting', closed=True)
    p.frame('Work', node_ids=[source['id'], shot['id']], group=folder['id'])
    before = {n['id'] for n in p.data['nodes']}
    p.paste_nodes([folder['id']], clipboard_project_id=p.data['id'], x=800, y=400)
    group = {n['name']: n for n in p.data['nodes'] if n['id'] not in before}
    assert p.path(group['Lighting 01']).is_relative_to(p.path(group['Assets 01']))
    assert any(Path(r['path']).resolve() == p.path(group['Models 01']) for r in group['Lighting 01']['scan']['refs'] if r['kind'] == 'Library')
    assert group['Lighting 01']['group'] == group['Work 01']['id']
    # Node rename keeps the actual folder and visual Frame and repairs existing copies.
    old_path, old_group = p.path(source), source['group']
    p.label(source['id'], 'Model library')
    assert not old_path.exists() and source['name'] == 'Model library'
    assert source['group'] == old_group and p.path(source).parent == old_path.parent
    assert p.path(source).name.endswith('_Clipboard_Test_Model_library-v001.blend')
    assert any(Path(r['path']).resolve() == p.path(source) for r in shot['scan']['refs'] if r['kind'] == 'Library')
    checker = base / 'check.py'
    checker.write_text('''import bpy,json,sys
from pathlib import Path
for entry in json.loads(Path(sys.argv[sys.argv.index('--')+1]).read_text()):
    bpy.ops.wm.open_mainfile(filepath=entry['file'])
    obj=bpy.data.objects['Part_4']
    assert obj.override_library and obj.location.x==7
    assert obj.material_slots[2].link=='OBJECT' and obj.material_slots[2].material.name=='Shot Finish'
    assert not obj.material_slots[2].material.library
    assert bpy.data.objects['Part_2'].material_slots[0].material.name=='Copper Local'
    assert bpy.data.objects['Part_3'].material_slots[2].material.name=='Rubber V2'
    direct=[str(Path(bpy.path.abspath(l.filepath)).resolve()) for l in bpy.data.libraries if not l.parent]
    assert entry['source'] in direct,(entry,direct)
print('COPIED_OVERRIDES_OK')
''', encoding='utf-8')
    manifest = base / 'checks.json'
    manifest.write_text(json.dumps([{'file': str(p.path(n)), 'source': str(p.path(s))} for n, s in
                                   [(shot, source), (lone, source), (pair['override 02'], pair['Source 01']), (group['Lighting 01'], group['Models 01'])]]), encoding='utf-8')
    p.run(checker, [manifest])
    print('PASS: independent saved copies, actual library remapping, nested folder/frame copies, material slots/local overrides and safe node/file rename', flush=True)
