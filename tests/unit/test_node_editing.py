"""Clipboard identity, independent state, naming and failure recovery."""
import copy
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from blender_pipeline.project.workspace import Pipeline
from blender_pipeline.project.model import digest


class NodeEditingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        (self.base / 'settings').mkdir()
        self.p = Pipeline(data_directory=self.base / 'settings')
        self.p.create(self.base, 'My Project')
        self.inspect = patch.object(self.p, 'inspect', side_effect=lambda n: n.update(scan={'hash': digest(self.p.path(n)), 'refs': [], 'scenes': []}))
        self.inspect.start()
        self.transaction = patch.object(self.p, 'transaction', side_effect=self.fake_transaction)
        self.transaction.start()

    def fake_transaction(self, node, job, new=False):
        target = self.p.path(node)
        if job['action'] == 'copy': shutil.copyfile(job['source'], target)
        elif job['action'] == 'create': target.write_bytes(b'saved blend with linked materials and local overrides')

    def tearDown(self):
        self.inspect.stop(); self.transaction.stop(); self.temp.cleanup()

    def blend(self, title='Shot', folder=None):
        self.p.create_blend(title, folder_id=folder, template_id='')
        return self.p.data['nodes'][-1]

    def test_saved_copies_keep_properties_connections_and_unique_names(self):
        p = self.p
        source = self.blend()
        source.update(color='purple', notes='My lighting', pinned_collections=['Asset'])
        original = digest(p.path(source))
        p.duplicate(source['id']); first = p.data['nodes'][-1]
        p.duplicate(source['id']); second = p.data['nodes'][-1]
        self.assertEqual((first['name'], second['name']), ('Shot 01', 'Shot 02'))
        self.assertEqual(first['color'], 'purple'); self.assertEqual(first['notes'], 'My lighting')
        self.assertEqual(first['pinned_collections'], ['Asset']); self.assertEqual(first['snapshots'], [])
        self.assertRegex(p.path(first).name, r'^\d{6}_My_Project_Shot_01-v001\.blend$')
        self.assertEqual(digest(p.path(first)), original)
        p.path(first).write_bytes(b'editing the pasted file')
        self.assertEqual(digest(p.path(source)), original)

    def test_folder_members_and_operation_references_are_remapped(self):
        p = self.p
        p.folder('Assets'); folder = p.data['nodes'][-1]
        a = self.blend('A', folder['id']); b = self.blend('B', folder['id'])
        p.frame('Group', node_ids=[a['id'], b['id']], group=folder['id']); frame = p.data['nodes'][-1]
        p.folder('Images'); output = p.data['nodes'][-1]
        p.render_node(source_ids=[b['id']], group=folder['id']); render = p.data['nodes'][-1]
        render['render_plan']['folder_id'] = output['id']
        p.export_node(source_id=a['id'], group=folder['id']); export = p.data['nodes'][-1]
        old_ids = {n['id'] for n in p.data['nodes']}
        p.paste_nodes([folder['id'], output['id']], clipboard_project_id=p.data['id'], x=900, y=300)
        added = {n['name']: n for n in p.data['nodes'] if n['id'] not in old_ids}
        self.assertEqual(added['A 01']['group'], added['Group 01']['id'])
        self.assertEqual(added['Group 01']['group'], added['Assets 01']['id'])
        self.assertTrue(p.path(added['A 01']).is_relative_to(p.path(added['Assets 01'])))
        self.assertEqual(added['Render 01']['render_plan']['source_ids'], [added['B 01']['id']])
        self.assertEqual(added['Render 01']['render_plan']['folder_id'], added['Images 01']['id'])
        self.assertEqual(added['Export 01']['export_config']['source_id'], added['A 01']['id'])
        self.assertEqual(render['render_plan']['source_ids'], [b['id']])
        self.assertFalse(any(n.get('snapshots') for n in added.values()))

    def test_copy_failures_leave_no_partial_nodes_or_files(self):
        p = self.p; source = self.blend()
        before = copy.deepcopy(p.data)
        files = {f.relative_to(p.root) for f in p.root.rglob('*')}
        with patch.object(p, 'save', side_effect=RuntimeError('disk failed')):
            with self.assertRaisesRegex(RuntimeError, 'disk failed'):
                p.paste_nodes([source['id']], clipboard_project_id=p.data['id'])
        self.assertEqual(p.data, before)
        self.assertEqual({f.relative_to(p.root) for f in p.root.rglob('*')}, files)
        with self.assertRaisesRegex(ValueError, 'different project'):
            p.paste_nodes([source['id']], clipboard_project_id='another-project')

    def test_rename_preserves_identity_parent_and_stable_naming_date(self):
        p = self.p
        p.folder('Models'); folder = p.data['nodes'][-1]
        source = self.blend('Shot', folder['id']); original_path = p.path(source)
        naming = dict(source['file_naming'])
        p.frame('Organize', node_ids=[source['id']]); frame = p.data['nodes'][-1]
        p.label(source['id'], 'Camera final')
        source = p.node(source['id'])
        self.assertEqual(source['name'], 'Camera final'); self.assertEqual(source['file_naming'], naming)
        self.assertEqual(source['group'], frame['id']); self.assertEqual(p.path(source).parent, original_path.parent)
        self.assertFalse(original_path.exists()); self.assertTrue(p.path(source).exists())
        self.assertTrue(p.path(source).name.endswith('_Camera_final-v001.blend'))
        self.assertEqual(p.data['path_aliases'][original_path.relative_to(p.root).as_posix()], source['path'])
        self.assertTrue(source['snapshots'])

    def test_open_files_cannot_be_renamed_and_colors_do_not_regroup(self):
        p = self.p; source = self.blend()
        p.frame('Frame', node_ids=[source['id']]); group = source['group']
        with patch.object(p, 'ensure_closed', side_effect=ValueError('open in Blender')):
            with self.assertRaisesRegex(ValueError, 'open in Blender'): p.label(source['id'], 'New name')
        self.assertEqual(source['name'], 'Shot')
        p.node_colors([source['id']], 'red')
        self.assertEqual(source['group'], group); self.assertEqual(source['color'], 'red')

    def test_rejected_rename_preserves_a_concurrent_source_save(self):
        p = self.p; source = self.blend()
        original = p.path(source)
        def changed_source(node, job, new=False):
            original.write_bytes(b'newer Blender save')
            raise ValueError('Source changed during operation')
        with patch.object(p, 'transaction', side_effect=changed_source):
            with self.assertRaisesRegex(ValueError, 'Source changed'):
                p.label(source['id'], 'New name')
        self.assertEqual(original.read_bytes(), b'newer Blender save')
        self.assertEqual(p.node(source['id'])['name'], 'Shot')
        self.assertFalse(original.with_name(p.blend_filename('New name')).exists())

    def test_rejected_rename_does_not_delete_a_destination_created_elsewhere(self):
        p = self.p; source = self.blend()
        destination = p.path(source).with_name(p.blend_filename('New name'))
        def destination_appeared(node, job, new=False):
            destination.write_bytes(b'another process created this file')
            raise ValueError('Destination appeared during operation')
        with patch.object(p, 'transaction', side_effect=destination_appeared):
            with self.assertRaisesRegex(ValueError, 'Destination appeared'):
                p.label(source['id'], 'New name')
        self.assertEqual(destination.read_bytes(), b'another process created this file')
        self.assertEqual(p.node(source['id'])['name'], 'Shot')
        self.assertTrue(p.path(p.node(source['id'])).is_file())


if __name__ == '__main__': unittest.main()
