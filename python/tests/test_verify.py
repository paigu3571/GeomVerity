# SPDX-License-Identifier: MPL-2.0
import unittest
from types import SimpleNamespace as S
from cst.verify import trace_geometry

class VerifyTests(unittest.TestCase):
    def test_missing_l2_is_broken(self):
        self.assertFalse(trace_geometry("g",{}, {})[0])
    def test_missing_l1_is_broken(self):
        self.assertFalse(trace_geometry("g",{"g":S(source_primitive_ids=["p"])}, {})[0])
    def test_missing_handle_is_broken(self):
        self.assertFalse(trace_geometry("g",{"g":S(source_primitive_ids=["p"])},{"p":S(source=S(handle=""))})[0])
    def test_complete_reference_chain(self):
        self.assertTrue(trace_geometry("g",{"g":S(source_primitive_ids=["p"])},{"p":S(source=S(handle="10"))})[0])

    def test_no_dwg_is_unverified_not_passed(self):
        from cst.verify import verify_source_bytes
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            result=verify_source_bytes(directory,S(file_name="missing.dwg",sha256="0"*64))
            self.assertEqual(result["status"],"unverified")
