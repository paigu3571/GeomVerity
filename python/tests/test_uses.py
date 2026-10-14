# SPDX-License-Identifier: MPL-2.0
import unittest
import yaml
from cst.uses import classify_name,DEFAULT_TABLE
class UsesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.table=yaml.safe_load(DEFAULT_TABLE.read_text(encoding="utf-8"))
    def test_substation_priority_over_distribution(self):self.assertEqual(classify_name("变配电室",self.table)["category"],"SUBSTATION")
    def test_void_not_actual_room(self):self.assertEqual(classify_name("电气间上空",self.table)["category"],"EXCLUDED")
    def test_nonroom_area_excluded(self):self.assertEqual(classify_name("面积",self.table)["category"],"EXCLUDED")
    def test_new_hierarchy_and_overlap(self):
        for name,category,secondary in [("变配电房","SUBSTATION","变配电房"),("商业配电房","DISTRIBUTION_ROOM","配电房"),("信号覆盖机房","WEAK_CURRENT_ROOM","信号覆盖机房"),("广电机房","WEAK_CURRENT_ROOM","广电机房"),("弱电机房","WEAK_CURRENT_ROOM","弱电机房"),("电信间","WEAK_CURRENT_ROOM","电信间"),("充电桩电表间","SMALL_ELECTRICAL_ROOM","电表间"),("电气间","SMALL_ELECTRICAL_ROOM","电气间"),("配电间","SMALL_ELECTRICAL_ROOM","配电间")]:
            with self.subTest(name=name):
                result=classify_name(name,self.table)
                self.assertEqual((result["category"],result["secondary_label"]),(category,secondary))
        self.assertEqual(classify_name("变配电房上空",self.table)["category"],"EXCLUDED")

    def test_engineer_exact_aliases_and_unseen_names(self):
        for name,category,secondary in [("采光井","EXCLUDED","上空"),("预留设备间","ARCHITECTURAL_ROOM","设备用房"),("电气进线间","SMALL_ELECTRICAL_ROOM","电气间"),("三网合一机房","WEAK_CURRENT_ROOM","三网合一机房"),("加压送风井","HVAC_SHAFT","风井"),("生活水泵房","PLUMBING_ROOM","水泵房")]:
            with self.subTest(name=name):
                result=classify_name(name,self.table)
                self.assertEqual((result["category"],result["secondary_label"]),(category,secondary))
        self.assertEqual(classify_name("未收录的新房名",self.table)["category"],"NOT_INCLUDED")
        self.assertTrue(self.table["water_candidates"]["approved"])
