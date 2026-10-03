"""Fast contracts for boundaries and older project data; Blender is not required."""
import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from blender_pipeline.application.commands import Application, COMMANDS
from blender_pipeline.adapters.blender_runtime import BlenderRuntime
from blender_pipeline.project.workspace import Pipeline
from blender_pipeline.storage.local_settings import LocalSettings
from blender_pipeline.storage.projects import CURRENT_SCHEMA, JsonProjectRepository, atomic_json, validate_document

FIXTURE = Path(__file__).parent.parent / 'fixtures' / 'project_v3.json'


class ProjectStorageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / '.pipeline').mkdir()
        self.path = self.root / '.pipeline' / 'project.json'
        self.path.write_bytes(FIXTURE.read_bytes())
        self.repository = JsonProjectRepository()

    def test_validation_preserves_feature_data_and_does_not_mutate_input(self):
        source = json.loads(FIXTURE.read_text())
        before = copy.deepcopy(source)
        migrated = validate_document(source)
        self.assertEqual(source, before)
        self.assertEqual(migrated['schema'], CURRENT_SCHEMA)
        self.assertEqual(migrated['view'], {'x': 0, 'y': 0, 'zoom': 1})
        for key in ('nodes', 'renders', 'render_queue', 'templates', 'archived_files', 'extension_data'):
            self.assertEqual(migrated[key], before[key])

    def test_load_makes_no_backup_and_save_increments_revision(self):
        original = self.path.read_bytes()
        data = self.repository.load(self.root)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse((self.root / '.pipeline' / 'migrations').exists())
        data['name'] = 'Renamed'
        self.repository.save(self.root, data)
        self.assertEqual(data['revision'], 1)
        self.assertEqual(self.repository.load(self.root)['name'], 'Renamed')

    def test_future_or_invalid_project_never_rewrites_original(self):
        for update in ({'schema': 999}, {'schema': True}, {'nodes': [{}]}, {'nodes': 'invalid'},
                       {'view': {'x': float('nan'), 'y': 0, 'zoom': 1}},
                       {'view': {'x': 0, 'y': 0, 'zoom': 0}}):
            source = json.loads(FIXTURE.read_bytes())
            source.update(update)
            self.path.write_text(json.dumps(source))
            original = self.path.read_bytes()
            with self.assertRaises(ValueError):
                self.repository.load(self.root)
            self.assertEqual(self.path.read_bytes(), original)
            self.assertFalse((self.root / '.pipeline' / 'migrations').exists())

    def test_old_format_is_rejected_without_rewriting_or_backups(self):
        source=json.loads(self.path.read_bytes());source['schema']=2
        self.path.write_text(json.dumps(source));original=self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'new project'):
            self.repository.load(self.root)
        self.assertEqual(self.path.read_bytes(),original)
        self.assertFalse((self.root/'.pipeline'/'migrations').exists())

    def test_failed_save_keeps_previous_json_and_cleans_temporary_file(self):
        original = self.path.read_bytes()
        with patch('blender_pipeline.storage.projects.os.replace', side_effect=OSError('failed')):
            with self.assertRaises(OSError):
                atomic_json(self.path, {'test': 1})
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.path.parent.glob('*.tmp')), [])

    def test_duplicate_node_ids_are_rejected(self):
        source = json.loads(FIXTURE.read_bytes())
        source['nodes'].append(copy.deepcopy(source['nodes'][0]))
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            validate_document(source)

    def test_pipeline_can_receive_repository_and_failed_load_keeps_context(self):
        repository = Mock()
        repository.load.return_value = validate_document(json.loads(FIXTURE.read_bytes()))
        p = Pipeline(repository=repository)
        p.registry = self.root / 'recent.json'
        p.global_template_config = self.root / 'startup.json'
        p.load(self.root)
        self.assertIs(p.repository, repository)
        before = p.root, p.data
        calls_before = repository.save.call_count
        repository.load.side_effect = ValueError('future schema')
        with self.assertRaises(ValueError):
            p.load(self.root / 'other')
        self.assertEqual((p.root, p.data), before)
        self.assertEqual(repository.save.call_count, calls_before)
        repository.save.reset_mock()
        p.save()
        repository.save.assert_called_once_with(p.root, p.data)


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.model = SimpleNamespace(data={'id':'test-project','revision':0},root=self.root,registry=self.root/'recent.json',lock=threading.RLock(),repository=Mock(),label=Mock(return_value={'label': 'updated'}),
                                     render_cancel=Mock(return_value={'cancelled': True}))
        self.tasks = SimpleNamespace(active=Mock(return_value=False), state=Mock(return_value={'project': None}),
                                     submit=Mock(return_value={'job': 'test-job'}))
        self.bridge = SimpleNamespace(heartbeat=Mock(return_value={'session': 'alive'}))
        self.model.repository.load.return_value=self.model.data
        self.app = Application(self.model, self.tasks, self.bridge, self.root)

    def test_queued_command_does_not_mutate_request(self):
        args = {'action': 'label', 'node_id': 'a', 'title': 'New','project_id':'test-project','expected_revision':0,'request_id':'request-a'}
        self.assertEqual(self.app.dispatch('async', args), {'job': 'test-job'})
        self.assertEqual(args['action'], 'label')
        self.assertEqual(self.tasks.submit.call_args.args[:2],('label',{'node_id':'a','title':'New'}))
        self.assertEqual(self.tasks.submit.call_args.kwargs['context']['project_id'],'test-project')

    def test_read_and_cancel_remain_available_during_file_operation(self):
        self.tasks.active.return_value = True
        self.assertEqual(self.app.dispatch('state', {}), {'project': None})
        self.assertEqual(self.app.dispatch('render_cancel', {'project_id':'test-project','expected_revision':0,'request_id':'cancel-a'}), {'cancelled': True})
        with self.assertRaisesRegex(ValueError, 'file operation'):
            self.app.dispatch('label', {'node_id': 'a', 'title': 'New'})
        self.model.label.assert_not_called()

    def test_command_scope_and_invalid_arguments(self):
        for action, args in (('label', []), ('async', {'action': 'layout'}),
                             ('async', {'action': []}), ('nonexistent', {})):
            with self.assertRaises(ValueError):
                self.app.dispatch(action, args)
        self.tasks.submit.assert_not_called()

    def test_preferences_are_isolated_and_invalid_updates_do_not_clobber(self):
        prefs = {'navigator': True, 'inspector': False, 'width': 400}
        self.assertEqual(self.app.dispatch('ui_preferences', prefs), prefs)
        other = Application(self.model, self.tasks, self.bridge, self.root / 'other')
        self.assertEqual(other.dispatch('ui_preferences', {'read': True}), {})
        with self.assertRaises(ValueError):
            self.app.dispatch('ui_preferences', {**prefs, 'width': 10000})
        self.assertEqual(self.app.dispatch('ui_preferences', {'read': True}), prefs)

    def test_catalog_resolves_all_existing_pipeline_methods(self):
        pipeline = Pipeline()
        for command in COMMANDS.values():
            self.assertTrue(callable(getattr(pipeline, command.method)))

    def test_failed_executable_setting_keeps_running_configuration(self):
        executable = self.root / 'blender.exe'
        executable.touch()
        self.model.blender = 'previous.exe'
        with patch('blender_pipeline.storage.local_settings.atomic_json', side_effect=PermissionError('locked')):
            with self.assertRaises(PermissionError):
                LocalSettings(self.root).configure_blender(self.model, executable)
        self.assertEqual(self.model.blender, 'previous.exe')


class BlenderRuntimeTests(unittest.TestCase):
    def test_worker_command_and_errors_without_launching_blender(self):
        runner = Mock(return_value=SimpleNamespace(returncode=0))
        runtime = BlenderRuntime('/scripts', runner=runner)
        runtime.run('blender', 'scan_blend.py', ['scan.json', 4], opened='Shot.blend')
        command = runner.call_args.args[0]
        self.assertEqual(command[:5], ['blender', '--background', '--factory-startup', '--disable-autoexec', 'Shot.blend'])
        self.assertEqual(command[-3:], ['--', 'scan.json', '4'])
        self.assertEqual(runner.call_args.kwargs['timeout'], 180)
        runner.return_value = SimpleNamespace(returncode=1, stdout='failure', stderr='details')
        with self.assertRaisesRegex(ValueError, 'failuredetails'):
            runtime.run('blender', 'scan_blend.py', [])


if __name__ == '__main__':
    unittest.main()
