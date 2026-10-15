# SPDX-License-Identifier: MPL-2.0
import unittest
from cst.cad_location import cad_location

class CadLocationTests(unittest.TestCase):
    def test_large_wcs_and_inverted_screen_y_recover_original_region(self):
        value = cad_location({'类型': 'space', 'view_bounds': [0., -12., 10., 12.],
                              'source': {'handle': 'ABC'}}, [36370292570., 2939712695.])
        self.assertEqual(value['window_wcs_mm'], [[36370291370., 2939711495., 0.], [36370303770., 2939725895., 0.]])
        self.assertIn('36370291370.0', value['command'])
        self.assertIn('sssetfirst', value['command'])

    def test_nested_text_zooms_room_without_selecting_entire_parent_block(self):
        value = cad_location({'类型': 'space', 'view_bounds': [0, 0, 10, 10],
                              '定位字段': {'cad_target': {'handle': '51631', 'outer_block_handle': '25507'}}}, [0, 0])
        self.assertIn('handent "51631"', value['command'])
        self.assertIn('vla-ZoomWindow', value['command'])
        self.assertNotIn(chr(10), value['command'])
        self.assertNotIn('sssetfirst', value['command'])
        self.assertNotIn('25507', value['command'])

    def test_generated_lamp_is_not_a_source_cad_entity(self):
        value = cad_location({'类型': 'generated_light', 'view_bounds': [0, 0, 1, 1],
                              'source': {'handle': 'ABC'}}, [0, 0])
        self.assertIsNone(value['command'])
        self.assertEqual(value['state'], 'not_in_source')

    def test_bad_coordinates_and_injected_handle_are_not_executed(self):
        self.assertIsNone(cad_location({'view_bounds': [0, float('nan'), 1, 1]}, [0, 0])['command'])
        self.assertIsNone(cad_location({'view_bounds': [0, 0, -1, 1]}, [0, 0])['command'])
        value = cad_location({'view_bounds': [0, 0, 1, 1], 'source': {'handle': 'AAA") (command "ERASE")'}}, [0, 0])
        self.assertNotIn('ERASE', value['command'])
        self.assertIn('CMDACTIVE', value['command'])
        self.assertIn('TILEMODE', value['command'])
