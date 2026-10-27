# SPDX-License-Identifier: MPL-2.0
import json,tempfile,unittest
from pathlib import Path
from cst.workbench_claims import save_claims
from unittest.mock import patch

class WorkbenchClaimsTests(unittest.TestCase):
    def test_original_spans_revisions_and_changed_document_clear_old_result(self):
        text='SYNTHETIC 😀原文。第二句。'
        document={'schema_version':'claims.v1','original_text':text,'claims':[{'id':'one','text':text[:14],'span':{'start':0,'end':14},'refs':[],'values':{},'kind':'unsupported','extraction':'manual','generated_by':None}]}
        with tempfile.TemporaryDirectory() as folder:
            first=save_claims(folder,document,Path(folder)/'first')
            self.assertEqual(first['document']['original_text'],text)
            self.assertEqual(len(first['history']),1);self.assertIsNone(first['report'])
            document['claims'][0]['kind']='reference'
            second=save_claims(folder,document,Path(folder)/'second',previous=first)
            self.assertEqual(second['history'][1]['before']['claims'][0]['kind'],'unsupported')
            self.assertEqual(second['history'][1]['after']['claims'][0]['kind'],'reference')
            self.assertTrue((Path(folder)/'second/claims-edit-history.json').is_file())
            document['claims'][0]['text']='篡改原文'
            with self.assertRaises(ValueError):save_claims(folder,document,Path(folder)/'bad')
    def test_empty_claims_cannot_be_claimed_as_completed_check(self):
        with tempfile.TemporaryDirectory() as folder,patch('cst.workbench_claims.check_claims') as check:
            with self.assertRaisesRegex(ValueError,'至少一条'):save_claims(folder,{'original_text':'SYNTHETIC','claims':[]},folder,run_check=True)
            check.assert_not_called()

    def test_export_refuses_unsaved_frontend_edits(self):
        from cst.desktop import Workbench
        with tempfile.TemporaryDirectory() as folder:
            app=Workbench(folder,Path(__file__).resolve().parents[2])
            with self.assertRaisesRegex(ValueError,'未保存或未核验'):app.perform('export',{'path':folder,'claims_dirty':True})
    def test_model_import_keeps_actor_context_and_rejects_changed_basis(self):
        from cst.workbench_claims import import_claims
        from cst.naming import digest
        text='SYNTHETIC辅助划分。'
        document={'schema_version':'claims.v1','original_text':text,'model_name':'SYNTHETIC原文生成方','claims':[{'id':'one','text':text,'span':{'start':0,'end':len(text)},'refs':[],'values':{},'kind':'unsupported','extraction':'model','generated_by':'Codex'}]}
        with tempfile.TemporaryDirectory() as folder,patch('cst.workbench_claims.ReadTools'):
            root=Path(folder);src=root/'source.json';src.write_text(json.dumps(document));delta=root/'diff.json';delta.write_text('{}')
            imported=import_claims(root,src,root/'first',changes=delta,status_basis='frozen_record')
            self.assertEqual(imported['document']['claims'][0]['generated_by'],'Codex')
            self.assertEqual(imported['history'][0]['method'],'model_import');self.assertEqual(imported['history'][0]['actor'],'Codex')
            document['claims'][0]['refs']=['sem_SYNTHETIC']
            edited=save_claims(root,document,root/'second',previous=imported)
            self.assertEqual(edited['history'][-1]['method'],'manual');self.assertEqual(edited['context']['status_basis'],'frozen_record')
            plain=import_claims(root,src,root/'current',previous=imported)
            self.assertFalse(plain['context'])
            delta.write_text('{"changed":true}')
            with self.assertRaisesRegex(ValueError,'依据已变化'):save_claims(root,document,root/'bad',previous=imported)
