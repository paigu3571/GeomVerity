# SPDX-License-Identifier: MPL-2.0
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from cst.demo import run


class DemoQuickTests(unittest.TestCase):
    def test_quick_propagates_reference_failure_without_claiming_success(self):
        with tempfile.TemporaryDirectory() as folder,patch('cst.demo.verify',return_value={'failure_count':1}):
            with self.assertRaisesRegex(ValueError,'快速演示未通过'):run(Path(folder),quick=True)
            self.assertFalse((Path(folder)/'dist/demo-quick/manifest.json').exists())
