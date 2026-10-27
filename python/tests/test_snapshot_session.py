# SPDX-License-Identifier: MPL-2.0
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from cst.model import load,L3,snapshot_session

class SnapshotSessionTests(unittest.TestCase):
    def test_reuse_only_inside_operation_and_detect_file_change(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(L3,'model_validate_json',side_effect=lambda data:SimpleNamespace(data=data)) as validate:
            path=Path(folder)/'building-semantics.v1.json';path.write_bytes(b'{}')
            with snapshot_session():
                first=load(folder)
                with snapshot_session():self.assertIs(load(folder),first)
                self.assertEqual(validate.call_count,1)
                path.write_bytes(b'{"changed":true}')
                with self.assertRaisesRegex(ValueError,'发生变化'):load(folder)
            with snapshot_session():self.assertIsNot(load(folder),first)
            self.assertEqual(validate.call_count,2)
            self.assertIsNot(load(folder),load(folder))

    def test_separate_contexts_cannot_reuse_prior_mutated_model(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(L3,'model_validate_json',side_effect=lambda data:SimpleNamespace(data=data)):
            (Path(folder)/'building-semantics.v1.json').write_bytes(b'{}')
            with snapshot_session():value=load(folder);value.data=b'SYNTHETIC_MUTATION'
            with snapshot_session():self.assertEqual(load(folder).data,b'{}')

    def test_switch_from_compressed_to_plain_file_is_not_mixed_in_one_operation(self):
        import gzip
        with tempfile.TemporaryDirectory() as folder,patch.object(L3,'model_validate_json',side_effect=lambda data:SimpleNamespace(data=data)):
            directory=Path(folder);(directory/'building-semantics.v1.json.gz').write_bytes(gzip.compress(b'{}'))
            with snapshot_session():
                load(directory)
                (directory/'building-semantics.v1.json').write_bytes(b'{}')
                with self.assertRaisesRegex(ValueError,'发生变化'):load(directory)

    def test_rule_metadata_copy_and_dependency_change(self):
        from cst.decisions import rule_metadata
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'r.yaml';path.write_text('id: R_SYN\nclauses: [{code: SYN-2026}]\n')
            with snapshot_session():
                first=rule_metadata('R_SYN',folder);first['clauses'][0]['code']='SYNTHETIC_MUTATION'
                self.assertEqual(rule_metadata('R_SYN',folder)['clauses'][0]['code'],'SYN-2026')
                path.write_text('id: R_SYN\nclauses: [{code: SYN-2025}]\n')
                with self.assertRaisesRegex(ValueError,'发生变化'):rule_metadata('R_SYN',folder)
            self.assertEqual(rule_metadata('R_SYN',folder)['clauses'][0]['code'],'SYN-2025')
