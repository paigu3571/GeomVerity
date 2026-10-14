# SPDX-License-Identifier: MPL-2.0
import unittest
from cst.sanitize import Cleaner
class SanitizeTests(unittest.TestCase):
    def test_names_paths_and_unrelated_text_removed(self):
        synthetic={"objects":[],"drawing":{"file_name":"private.dwg","drawing_id":"old-project"},"profile":{"project_id":"old-company"}}
        c=Cleaner(synthetic,"A")
        self.assertNotIn("private",c.text("private.dwg"))
        self.assertNotIn("old-company",c.text("old-company"))
        self.assertEqual(c.walk({"raw_text":"private title"})["raw_text"],"[REDACTED_ANNOTATION]")
        self.assertEqual(c.text(chr(74)+":"+chr(92)+"secret"),"[REDACTED_PATH]")
