# SPDX-License-Identifier: MPL-2.0
import unittest,yaml,copy
from types import SimpleNamespace as S
from cst.light_calc import calculate_room,RULE
class LightCalculationTests(unittest.TestCase):
 def room(self,points):return S(semantic_id='SYNTHETIC',raw_label='合成矩形',status='review',source=S(handle='SYNTHETIC'),geometry=S(is_closed=True,paths=[[S(x=x,y=y) for x,y in points]]))
 def test_lumen_rounding_and_geometry_layout_are_separate(self):
  rule=yaml.safe_load(RULE.read_text(encoding='utf-8'));room=self.room([(0,0),(9000,0),(9000,7000),(0,7000)])
  value=calculate_room(room,'DISTRIBUTION_ROOM',rule,30)
  self.assertEqual(value['calculated_fixture_count'],15);self.assertEqual(value['estimated']['eav_lx'],200);self.assertTrue(value['estimated']['demo_lpd_limit_met']);self.assertFalse(value['existing_layout']['demo_lpd_limit_met']);self.assertIn('无法判定',value['formal_compliance'])
 def test_irregular_not_forced_and_invalid_parameters_rejected(self):
  rule=yaml.safe_load(RULE.read_text(encoding='utf-8'));room=self.room([(0,0),(8000,0),(8000,3000),(3000,3000),(3000,8000),(0,8000)])
  value=calculate_room(room,'SUBSTATION',rule,10)
  self.assertEqual(value['result'],'演示参数回算完成');self.assertAlmostEqual(value['existing_layout']['lpd_w_m2'],200/39);self.assertAlmostEqual(value['room_index'],2*39/(2.4*32),places=5)
  room=self.room([(0,0),(9000,0),(9000,7000),(0,7000)]);rule=copy.deepcopy(rule);rule['parameters']['flux_per_source_lm']=0
  with self.assertRaises(ValueError):calculate_room(room,'SUBSTATION',rule)

 def test_public_hole_area_is_preserved_but_claim_geometry_stays_conservative(self):
  from cst.light_calc import outline_polygon
  rule=yaml.safe_load(RULE.read_text(encoding='utf-8'))
  room=self.room([(0,0),(10000,0),(10000,10000),(0,10000)])
  room.geometry.paths.append([S(x=x,y=y) for x,y in [(4000,4000),(4000,6000),(6000,6000),(6000,4000)]])
  value=calculate_room(room,'SUBSTATION',rule,10)
  self.assertAlmostEqual(value['existing_layout']['lpd_w_m2'],200/96)
  with self.assertRaises(ValueError):outline_polygon(room.geometry)
