# SPDX-License-Identifier: MPL-2.0
import unittest
from pathlib import Path
from cst.rules import load_rule,evaluate,predicate,Rule
ROOT=Path(__file__).resolve().parents[2]
class RuleTests(unittest.TestCase):
    def fixture(self,**kw):return {"id":"syn-space","origin":"SYNTHETIC","status":"accepted","use":"SUBSTATION",**kw}
    def test_r1_three_values(self):
        rule=load_rule(ROOT/'rules/R1.yaml')
        for item,result in [(self.fixture(use="DISTRIBUTION_ROOM",long_side_m=8,opening_count=2,opening_complete=True),"通过"),(self.fixture(use="DISTRIBUTION_ROOM",long_side_m=8,opening_count=1,opening_complete=True),"不通过"),(self.fixture(use="DISTRIBUTION_ROOM",long_side_m=8),"无法判定")]:
            with self.subTest(result=result):self.assertEqual(evaluate(rule,item,True)["result"],result)
    def test_r3_three_values_and_single_floor(self):
        rule=load_rule(ROOT/'rules/R3.yaml')
        for uses,result in [([],"通过"),(["KITCHEN"],"不通过"),(None,"无法判定")]:
            out=evaluate(rule,self.fixture(above_uses=uses,above_uses_complete=True),True)
            self.assertEqual(out["result"],result)
            if uses is None:self.assertIn("上一层",out["reason"])
    def test_r4_three_values_is_advisory(self):
        rule=load_rule(ROOT/'rules/R4.yaml')
        for uses,result in [([],"通过"),(["KITCHEN"],"不通过"),(None,"无法判定")]:
            out=evaluate(rule,self.fixture(adjacent_uses=uses,adjacent_uses_complete=True),True)
            self.assertEqual(out["result"],result);self.assertEqual(out["level"],"提示")
    def test_review_related_input_propagates(self):
        rule=load_rule(ROOT/'rules/R3.yaml')
        out=evaluate(rule,self.fixture(above_uses=[],above_uses_complete=True,input_statuses=["review"]),True)
        self.assertEqual(out["input_confidence"],"输入待复核")
    def test_missing_relationship_not_absence(self):
        self.assertIsNone(predicate({"predicate":"shaft_shared_with","values":["ELEVATOR_SHAFT"]},{"shared_uses":[]})[0])
    def test_unapproved_real_rule_blocked(self):
        rule=load_rule(ROOT/'rules/R1.yaml').model_copy(update={"approved":False,"approved_by":None})
        with self.assertRaises(ValueError):evaluate(rule,self.fixture(use="DISTRIBUTION_ROOM"))

    def test_r2_three_values_heat_adjacency(self):
        rule=load_rule(ROOT/'rules/R2.yaml')
        for uses,result in [([],"通过"),(["HOT_FLUE"],"不通过"),(None,"无法判定")]:
            with self.subTest(result=result):
                out=evaluate(rule,self.fixture(use="ELECTRICAL_SHAFT",adjacent_uses=uses,adjacent_uses_complete=True),True)
                self.assertEqual(out["result"],result)
                self.assertEqual(out["origin"],"SYNTHETIC")
        out=evaluate(rule,self.fixture(use="ELECTRICAL_SHAFT",adjacent_uses=[],adjacent_uses_complete=False),True)
        self.assertEqual(out["result"],"无法判定")

    def test_engineer_confirms_threshold_without_invented_length(self):
        rule=load_rule(ROOT/'rules/R1.yaml')
        item=self.fixture(use='DISTRIBUTION_ROOM',status='review',length_threshold_confirmation={'threshold':7.0,'value':True},opening_count=2,opening_complete=True)
        out=evaluate(rule,item,True)
        self.assertEqual(out['result'],'通过');self.assertEqual(out['input_confidence'],'输入待复核')
        self.assertNotIn('long_side_m',out['values'])
        item['length_threshold_confirmation']['threshold']=10.0
        self.assertEqual(evaluate(rule,item,True)['result'],'无法判定')

    def test_untriggered_is_not_applicable_and_not_pass(self):
        rule=load_rule(ROOT/'rules/R1.yaml')
        self.assertEqual(evaluate(rule,self.fixture(use='DISTRIBUTION_ROOM',long_side_m=7),True)['result'],'不适用')
    def test_candidate_risk_does_not_require_complete_absence(self):
        for id,use,neighbour in [('R2','ELECTRICAL_SHAFT','HOT_FLUE'),('R4','SUBSTATION','KITCHEN')]:
            rule=load_rule(ROOT/('rules/'+id+'.yaml'))
            out=evaluate(rule,self.fixture(use=use,status='review',adjacent_uses=[neighbour],adjacent_uses_complete=False),True)
            self.assertEqual(out['result'],'不通过');self.assertEqual(out['input_confidence'],'输入待复核')
            out=evaluate(rule,self.fixture(use=use,adjacent_uses=[],adjacent_uses_complete=False),True)
            self.assertEqual(out['result'],'无法判定')

    def test_unknown_use_is_missing_input_not_not_applicable(self):
        rule=load_rule(ROOT/'rules/R1.yaml')
        for use in (None,'','UNKNOWN'):
            with self.subTest(use=use):
                out=evaluate(rule,self.fixture(use=use),True)
                self.assertEqual(out['result'],'无法判定')
                self.assertEqual(out['reason'],'缺少已确认用途')
        self.assertEqual(evaluate(rule,self.fixture(use='TOILET'),True)['result'],'不适用')
