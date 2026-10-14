# SPDX-License-Identifier: MPL-2.0
import unittest
from types import SimpleNamespace as S
from cst.gold import area_m2
class GoldTests(unittest.TestCase):
    def test_unavailable_area_not_zero(self):
        obj=S(evidence=[S(kind="geometry_fact",value="g")])
        self.assertEqual(area_m2(obj,{"g":S(measurements=S(area_is_available=False))}),"")
    def test_area_unit_conversion(self):
        obj=S(evidence=[S(kind="geometry_fact",value="g")])
        self.assertEqual(area_m2(obj,{"g":S(measurements=S(area_is_available=True,area_square_millimeters=30000000.0))}),30.0)

    def test_group_merge_and_protect_human_work(self):
        import csv,tempfile
        from pathlib import Path
        from unittest.mock import patch
        from cst.gold import group_gold
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/"group.csv"
            with patch("cst.gold.load",return_value=S(objects=[S(type="space",raw_label="配电房"),S(type="space",raw_label="配电房"),S(type="shaft",raw_label="电井")])):
                result=group_gold(["samples/A","samples/B"],output)
            self.assertEqual((result["unique_names"],result["object_count"]),(2,6))
            with output.open(encoding="utf-8-sig",newline="") as f:rows=list(csv.DictReader(f))
            row=next(row for row in rows if row["房名"]=="配电房")
            self.assertEqual((row["数量A"],row["数量B"]),("2","2"))
            rows[0]["你确认的一级"]="电气竖井"
            with output.open("w",encoding="utf-8-sig",newline="") as f:
                writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
            with self.assertRaises(ValueError):group_gold(["samples/A"],output)
