# SPDX-License-Identifier: MPL-2.0
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from cst import api
from cst.inventory import inspect_scan, inventory
from cst.model import L1, L2, L3

SAMPLE = Path(__file__).resolve().parents[2] / 'samples/A'


class InventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.models = {model: api.load(SAMPLE, model) for model in (L1, L2, L3)}

    def inspect_with(self, models):
        with patch('cst.inventory.api.load', side_effect=lambda directory, model: models[model]):
            return inspect_scan('SYNTHETIC')

    def test_public_compressed_sample_loads_and_remains_review(self):
        value = inspect_scan(SAMPLE)
        self.assertTrue(value['load_ok'])
        self.assertEqual(value['room_count'], 73)
        self.assertEqual(value['status'], 'review')
        self.assertEqual(value['unreadable_proxy_count'], 25)
        self.assertEqual(value['unresolved_space_label_count'], 35)
        self.assertIn('不代表专业通过', value['conclusion'])
        self.assertEqual(value['objects_by_type'].get('door',0),0)
        self.assertEqual(value['display_metrics'][2],{'label':'门窗洞口','count':941})
        self.assertIn('天正门可能记为opening',value['opening_count_note'])

    def test_failed_layer_is_not_usable_even_when_all_layers_load(self):
        models = dict(self.models)
        models[L1] = models[L1].model_copy(update={'status': 'failed', 'reason_codes': ['T20_INTERPRETER_REQUIRED']})
        value = self.inspect_with(models)
        self.assertTrue(value['load_ok'])
        self.assertIn('不能用于分析', value['conclusion'])
        self.assertEqual(value['tone'], 'failed')
        self.assertIn('天正解释器', value['conclusion'])

    def test_no_rooms_requires_review(self):
        models = dict(self.models)
        models[L3] = models[L3].model_copy(update={'objects': []})
        value = self.inspect_with(models)
        self.assertEqual(value['room_count'], 0)
        self.assertEqual(value['tone'], 'warning')
        self.assertIn('不能视为通过', value['conclusion'])

    def test_missing_files_are_unknown_not_zero(self):
        with tempfile.TemporaryDirectory() as folder:
            value = inspect_scan(folder)
        self.assertFalse(value['load_ok'])
        self.assertIsNone(value['room_count'])
        self.assertTrue(all(m['count'] is None for m in value['display_metrics']))
        self.assertEqual(value['tone'], 'unknown')
        self.assertIsNone(value['gap_record_count'])
        self.assertIsNone(value['objects_by_type'])
        self.assertIsNone(value['unreadable_proxy_count'])
        self.assertIn('缺少文件', value['layers']['L3']['error'])

    def test_schema_failure_does_not_dump_input_or_abort_other_layers(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'building-semantics.v1.json'
            path.write_text(json.dumps({'unexpected': 'SYNTHETIC_PRIVATE_SENTINEL'}), encoding='utf-8')
            value = inspect_scan(folder)
        error = value['layers']['L3']['error']
        self.assertIn('字段不兼容', error)
        self.assertNotIn('SYNTHETIC_PRIVATE_SENTINEL', error)
        self.assertFalse(value['load_ok'])

    def test_discovery_includes_incomplete_and_compressed_but_not_raw_copies(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'incomplete').mkdir()
            (root / 'incomplete/cad-primitives.v1.json').write_text('{}')
            (root / 'compressed').mkdir()
            (root / 'compressed/building-semantics.v1.json.gz').write_bytes(gzip.compress(b'{}'))
            (root / 'compressed/building-semantics.v1.json.raw').write_text('{}')
            (root / 'raw-only').mkdir()
            (root / 'raw-only/building-semantics.v1.json.raw').write_text('{}')
            rows = inventory(root)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(not row['load_ok'] for row in rows))

    def test_missing_root_is_explicit(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, '根目录不存在'):
                inventory(Path(folder) / 'missing')
