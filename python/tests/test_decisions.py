# SPDX-License-Identifier: MPL-2.0
import unittest
from cst.decisions import inherit_decision
class DecisionTests(unittest.TestCase):
 def test_input_and_rule_changes_expire_scope_confirmation(self):
  old={'rule':{'sha256':'R'},'inputs':[{'object_id':'old','content_fingerprint':'A'}],'engineer':{'confirmed_by':'工程师'}}
  new={'rule':{'sha256':'R'},'inputs':[{'object_id':'new','content_fingerprint':'A'}],'engineer':{}}
  self.assertTrue(inherit_decision(old,new,{'old':'new'})['inherited'])
  new['inputs'][0]['content_fingerprint']='B';self.assertFalse(inherit_decision(old,new,{'old':'new'})['inherited'])
  new['inputs'][0]['content_fingerprint']='A';new['rule']['sha256']='changed';self.assertFalse(inherit_decision(old,new,{'old':'new'})['inherited'])
 def test_unreviewed_record_not_promoted(self):
  record={'rule':{'sha256':'R'},'inputs':[],'engineer':{'confirmed_by':None}}
  self.assertFalse(inherit_decision(record,record,{})['inherited'])

 def test_rule_origin_is_separate_from_approval(self):
  import json
  from pathlib import Path
  from cst.decisions import rule_metadata
  root=Path(__file__).resolve().parents[2]
  shared=rule_metadata('DRAFT_88e437765ce8')
  record=json.loads((root/shared['drafted_by']['cache_file']).read_bytes())
  self.assertEqual(record['origin'],'REAL_API')
  self.assertEqual(shared['drafted_by']['model'],record['model'])
  self.assertEqual(shared['approved_by'],'张田')
  self.assertEqual(rule_metadata('R1')['drafted_by']['type'],'HISTORICAL_UNRECORDED')
  self.assertTrue(all(c.get('article') and c.get('code_version') for c in shared['clauses']))
