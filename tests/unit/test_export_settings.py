"""Portable format contracts and saved-scene animation timing."""
import unittest
from blender_pipeline.blender.export_settings import EXPORT_SETTINGS, checked_options, option_values, export_timing


class ExportSettingsTests(unittest.TestCase):
    def test_defaults_and_independent_sparse_presets(self):
        presets = {'FBX': {'global_scale': 2}, 'ALEMBIC': {'face_sets': True, 'xsamples': 4}}
        self.assertEqual(checked_options(presets), presets)
        self.assertTrue(option_values('ALEMBIC', presets)['face_sets'])
        self.assertEqual(option_values('FBX', presets)['global_scale'], 2)
        self.assertEqual(option_values('GLB', presets)['export_image_format'], 'AUTO')
        for mode in EXPORT_SETTINGS:
            self.assertEqual(checked_options({mode: option_values(mode)})[mode], option_values(mode))
        self.assertNotIn('uvs', presets['ALEMBIC'])
        self.assertEqual(option_values('ALEMBIC', presets, animation=False)['xsamples'], 1)
        self.assertTrue(option_values('ALEMBIC', presets, animation=False)['face_sets'])

    def test_rejects_unsafe_operator_keys_types_and_numbers(self):
        cases = [None, [], {'OTHER': {}}, {'FBX': {'filepath': 'elsewhere'}},
                 {'GLB': {'export_apply': 1}}, {'ALEMBIC': {'xsamples': 1.5}},
                 {'USD': {'evaluation_mode': 'UNKNOWN'}}, {'ALEMBIC': {'global_scale': True}},
                 {'FBX': {'global_scale': float('nan')}}, {'FBX': {'global_scale': float('inf')}},
                 {'FBX': {'global_scale': 10**1000}}, {'ALEMBIC': {'gsamples': 129}},
                 {'FBX': {'axis_forward': 'Y'}}, {'ALEMBIC': {'sh_open': .5, 'sh_close': 0}}]
        for options in cases:
            with self.subTest(options=repr(options)[:100]), self.assertRaises(ValueError):
                checked_options(options)

    def test_saved_custom_and_single_frame_timing(self):
        scene = {'start': 1, 'end': 250, 'current_frame': 50, 'fps': 23.976}
        preset = {'animation': True, 'start': None, 'end': None}
        self.assertEqual(export_timing(preset, scene)['frames'], 250)
        custom = export_timing({**preset, 'start': 100, 'end': 120}, scene)
        self.assertEqual((custom['start'], custom['end'], custom['frames'], custom['fps']), (100, 120, 21, 23.976))
        partial = export_timing({**preset, 'end': 10}, scene)
        self.assertEqual((partial['start'], partial['end']), (1, 10))
        single = export_timing({**preset, 'animation': False, 'start': 100, 'end': 120}, scene)
        self.assertEqual((single['start'], single['end'], single['frames'], single['mode']), (50, 50, 1, 'FRAME'))
        with self.assertRaisesRegex(ValueError, 'saved scene limits'):
            export_timing({**preset, 'start': 251}, scene)
        with self.assertRaisesRegex(ValueError, 'Refresh'):
            export_timing({**preset, 'animation': False}, {})


if __name__ == '__main__':
    unittest.main()
