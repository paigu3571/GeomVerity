# SPDX-License-Identifier: MPL-2.0
import unittest
from pydantic import ValidationError
from cst.model import Geometry, Evidence

class ReaderTests(unittest.TestCase):
    def test_unknown_field_is_not_silently_dropped(self):
        with self.assertRaises(ValidationError):
            Evidence.model_validate(dict(code="x",kind="x",value="x",source_handle="1",weight=1.0,unexpected="x"))

    def test_wrong_type_is_not_coerced(self):
        with self.assertRaises(ValidationError):
            Evidence.model_validate(dict(code="x",kind="x",value="x",source_handle="1",weight="0.5"))

    def test_missing_geometry_is_not_invented(self):
        with self.assertRaises(ValidationError):
            Geometry.model_validate({})
