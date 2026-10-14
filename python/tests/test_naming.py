# SPDX-License-Identifier: MPL-2.0
import unittest
from unittest.mock import patch
from tempfile import TemporaryDirectory
from pathlib import Path
import yaml
from cst.naming import validate,digest
from cst.uses import classify_name
class NamingTests(unittest.TestCase):
 def test_reject_unapproved_model_authority_and_missing_names(self):
  row={'name':'新房名','category':'UNKNOWN','reason':'资料不足','confidence':.2,'needs_review':True}
  self.assertEqual(validate({'rows':[row]},['新房名'],{'UNKNOWN':'未知'})[0],row)
  for changed in [dict(row,needs_review=False),dict(row,category='INVENTED')]:
   with self.assertRaises(ValueError):validate({'rows':[changed]},['新房名'],{'UNKNOWN':'未知'})
  with self.assertRaises(ValueError):validate({'rows':[]},['新房名'],{'UNKNOWN':'未知'})
 def test_approval_gate_and_confirmed_name_precedence(self):
  table={'classes':[{'code':'ARCHITECTURAL_ROOM','label':'建筑房间'}],'confirmed_names':{'已确认房间':{'category':'ARCHITECTURAL_ROOM','secondary_label':'原用途'}}}
  with TemporaryDirectory() as temp:
   path=Path(temp)/'table.yaml';proposals=path.parent/'naming_proposals.yaml'
   item={'name':'新房间','category':'ARCHITECTURAL_ROOM','approved':False,'approved_by':None}
   with patch('cst.uses.DEFAULT_TABLE',path):
    proposals.write_text(yaml.safe_dump({'entries':[item]}),encoding='utf-8');self.assertEqual(classify_name('新房间',table)['category'],'NOT_INCLUDED')
    item.update(approved=True,approved_by='工程师');proposals.write_text(yaml.safe_dump({'entries':[item]}),encoding='utf-8');self.assertEqual(classify_name('新房间',table)['category'],'ARCHITECTURAL_ROOM')
    self.assertEqual(classify_name('已确认房间',table)['secondary_label'],'原用途')
 def test_cache_identity_changes_with_prompt(self):
  self.assertNotEqual(digest({'prompt':'旧','names':['机房']}),digest({'prompt':'新','names':['机房']}))
