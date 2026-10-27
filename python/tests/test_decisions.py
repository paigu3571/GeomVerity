# SPDX-License-Identifier: MPL-2.0
import unittest
from cst.decisions import inherit_decision
class DecisionTests(unittest.TestCase):
 def test_input_and_rule_changes_expire_scope_confirmation(self):
  old={'rule':{'sha256':'R'},'inputs':[{'object_id':'old','content_fingerprint':'A','source_identity_sha256':'same'}],'engineer':{'confirmed_by':'工程师'}}
  new={'rule':{'sha256':'R'},'inputs':[{'object_id':'new','content_fingerprint':'A','source_identity_sha256':'same'}],'engineer':{}}
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

 def test_snapshot_drawing_hash_is_not_itself_source_identity_change(self):
  from pathlib import Path
  from cst.model import load
  from cst.decisions import decision
  obj=load(Path(__file__).resolve().parents[2]/'samples/A').objects[0]
  changed=obj.model_copy(deep=True);changed.source.drawing_hash='a'*64
  kwargs={'kind':'finding','key':'SYNTHETIC','result':'无法判定','ids':[obj.semantic_id],'rule':{'sha256':'R'},'run_id':'SYNTHETIC'}
  first=decision(objects={obj.semantic_id:obj},**kwargs)
  second=decision(objects={obj.semantic_id:changed},**kwargs)
  self.assertEqual(first['inputs'][0]['source_identity_sha256'],second['inputs'][0]['source_identity_sha256'])
  self.assertNotEqual(first['inputs'][0]['snapshot_sha256'],second['inputs'][0]['snapshot_sha256'])
