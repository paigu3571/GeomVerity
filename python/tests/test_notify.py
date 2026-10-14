# SPDX-License-Identifier: MPL-2.0
import unittest
from cst.notify import validate_notice
class NoticeTests(unittest.TestCase):
 def setUp(self):
  self.truth={'objects':{'change_1':{'id':'change_1','name':'配电房','old_handle':'A','new_handle':'B','status':'review'},'version_old':{'version':'初版','scanned_at':'2026-10-11','status':'review'},'version_new':{'version':'换版','scanned_at':'2026-10-13','status':'review'}},'summary':{}}
  self.claim={'text':'请核对实际出口数量。','object_ids':list(self.truth['objects']),'values':{i+'.'+k:v for i,row in self.truth['objects'].items() for k,v in row.items() if k not in ('id','status')}}
 def test_fact_citation_required_and_body_numbers_cannot_bypass(self):
  self.assertTrue(validate_notice({'claims':[self.claim]},self.truth)['valid'])
  self.claim['text']='面积为9999平方米。';self.assertFalse(validate_notice({'claims':[self.claim]},self.truth)['valid'])
 def test_wrong_handle_and_omitted_change_blocked(self):
  self.claim['values']['change_1.new_handle']='C';self.assertFalse(validate_notice({'claims':[self.claim]},self.truth)['valid'])
  self.assertFalse(validate_notice({'claims':[]},self.truth)['valid'])
