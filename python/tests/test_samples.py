# SPDX-License-Identifier: MPL-2.0
"""Frozen real benchmark assertions, not a runtime drawing whitelist."""
import hashlib,json,unittest
from pathlib import Path
from cst.l4 import check
ROOT=Path(__file__).resolve().parents[2]
class SampleTests(unittest.TestCase):
    def test_frozen_inputs_and_r1_counts(self):
        freeze=json.loads((ROOT/'eval/sample_freeze.json').read_bytes())
        for name,digest in freeze['files'].items():
            self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),digest,name)
        for name,count in [('A',2),('B',1)]:
            result=check(ROOT/'samples'/name)
            self.assertEqual(sum(f['rule_id']=='R1' and f['result']=='通过' for f in result['findings']),count)
            for f in result['findings']:
                if f['result']=='无法判定':self.assertTrue(f['request_question'])
                if f['rule_id']=='R1' and f['result']=='通过':self.assertEqual(f['engineer_reviewed']['reviewed_by'],'张田')
            coverage={}
            for f in result['findings']:
                for oid in f['object_ids']:coverage.setdefault(oid,set()).add(f['rule_id'])
            for rules in coverage.values():
                if rules.intersection({'R1','R3','R4'}):self.assertTrue({'R1','R3','R4'}.issubset(rules))
