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

 def test_derived_fluctuation_not_promoted_to_building_change(self):
  from cst.notify import is_recognition_fluctuation
  self.assertTrue(is_recognition_fluctuation({'basis':'派生围合差异：附近未发现源变化'}))
  self.assertFalse(is_recognition_fluctuation({'basis':'源几何或名称变化候选','related_source_changes':['wall_change']}))

 def test_fluctuation_model_statement_removed_from_formal_notice(self):
  import tempfile
  from pathlib import Path
  from cst.notify import render_notice
  c={'id':'change_1','new':{'id':'space1','name':'光厅','type':'space','handle':'WALL'},'old':None,'basis':'派生围合差异：无源变化','kinds':['几何变化'],'impact':{'rooms':[]}}
  item={'id':'change_1','rank':0,'risk':[]}
  answer={'claims':[{'object_ids':['change_1'],'text':'建筑修改了光厅。'}]}
  versions={k:{'version':k,'scanned_at':'2026-10-14T00:00:00Z'} for k in ['version_old','version_new']}
  with tempfile.TemporaryDirectory() as temp:
   view=render_notice({'changes':[c]},[item],answer,{'valid':True,'errors':[]},versions,{},temp)
   self.assertEqual(len(view['groups']['优先处理']),0);self.assertEqual(len(view['groups']['仅记录']),1)
   text=(Path(temp)/'notice.md').read_text(encoding='utf-8');self.assertNotIn('建筑修改了光厅',text);self.assertIn('程序识别波动',text)
