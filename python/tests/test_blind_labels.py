# SPDX-License-Identifier: MPL-2.0
import csv,json,tempfile,unittest
from pathlib import Path
from cst.blind_labels import prepare,summarize,HEADER
from test_claims import document
class BlindTemplateTests(unittest.TestCase):
 def test_blind_template_contains_no_tool_results_and_rejects_changed_sentence(self):
  with tempfile.TemporaryDirectory() as folder:
   out=Path(folder);doc=document('SYNTHETIC句子',['sem_syn'])
   result=prepare(doc,out);self.assertFalse(result['contains_tool_results'])
   with (out/'盲标表.csv').open(encoding='utf-8-sig',newline='') as f:rows=list(csv.reader(f))
   self.assertEqual(rows[0],HEADER);self.assertEqual(rows[1][2:],['','','',''])
   rows[1][1]='修改后的句子'
   with (out/'盲标表.csv').open('w',encoding='utf-8-sig',newline='') as f:csv.writer(f).writerows(rows)
   with self.assertRaisesRegex(ValueError,'原文变化'):summarize(out,out/'冻结主张.json',out/'盲标表.csv',out/'report')
