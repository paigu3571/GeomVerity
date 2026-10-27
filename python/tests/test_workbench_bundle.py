# SPDX-License-Identifier: MPL-2.0
import json,tempfile,unittest
from pathlib import Path
import test_claims as fixtures
from test_claims import document
from cst.workbench_claims import save_claims
from cst.workbench_bundle import export_review_bundle,open_review_bundle
from cst.reviews import make_review,append_review
from cst.l4 import check
from cst.claims import check_claims,recheck_claims

class WorkspaceBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.ClaimsTests.setUpClass();cls.templates=fixtures.ClaimsTests.templates
    make_scan=fixtures.ClaimsTests.make_scan
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.directory=Path(self.temp.name)/'SYNTHETIC';self.make_scan(self.directory)
    def tearDown(self):self.temp.cleanup()
    def test_export_reopen_contains_original_history_and_tamper_is_rejected(self):
        root=Path(self.temp.name)
        workspace=save_claims(self.directory,document('SYNTHETIC引用存在',['sem_syn']),root/'claims',run_check=True)
        output=root/'export';result=export_review_bundle(self.directory,output,'SYNTHETIC项目','版本一',workspace=workspace)
        self.assertEqual(result['verification']['status'],'verified')
        opened=open_review_bundle(output)
        self.assertEqual(opened['claims_report']['document']['original_text'],'SYNTHETIC引用存在')
        self.assertEqual(len(opened['history']['events']),1)
        manifest=json.loads((output/'bundle-manifest.json').read_bytes())
        for name in ('review-checklist.html','review-checklist.csv','workbench-context.json','claims-edit-history.json'):self.assertIn(name,manifest['files'])
        (output/'review-checklist.csv').write_text('TAMPER')
        bad=open_review_bundle(output);self.assertEqual(bad['verification']['status'],'failed');self.assertNotIn('claims_report',bad)
        with self.assertRaisesRegex(ValueError,'已有内容'):export_review_bundle(self.directory,output,'x','x')
    def test_manual_review_and_rejection_are_frozen_in_claim_context(self):
        finding=check(self.directory)['findings'][0];path=Path(self.temp.name)/'reviews.json'
        events=append_review(path,make_review('confirm','SYNTHETIC复核','核对缺资料输出','本条工具结果',finding=finding,drawing_hash='a'*64,synthetic=True))
        doc=document('该项工具结果已确认',[finding['id']],kind='status')
        first=check_claims(self.directory,doc,review_records=events)
        self.assertEqual(first['rows'][0]['conclusion'],'支持')
        events=append_review(path,make_review('reject','SYNTHETIC复核','撤回本条核对','本条工具结果',finding=finding,drawing_hash='a'*64,synthetic=True))
        second=recheck_claims(self.directory,first,review_records=events)
        self.assertEqual(second['rows'][0]['conclusion'],'矛盾');self.assertEqual(second['rows'][0]['validity'],'需复核')
        root=Path(self.temp.name);output=root/'with-reviews'
        export_review_bundle(self.directory,output,'SYNTHETIC','v',review_records=events)
        opened=open_review_bundle(output)
        self.assertEqual(opened['review_records']['events'][-1]['action'],'reject')
