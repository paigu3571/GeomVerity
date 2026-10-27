# SPDX-License-Identifier: MPL-2.0
import json,tempfile,unittest
from copy import deepcopy
from pathlib import Path
from cst.reviews import make_review,append_review,read_reviews,apply_reviews
from cst.decisions import inherit_decision

class ReviewsTests(unittest.TestCase):
    def finding(self):
        return {'id':'finding_SYNTHETIC','result':'无法判定','decision':{'id':'decision_SYNTHETIC','inputs':[{'object_id':'r','content_fingerprint':'A','source_identity_sha256':'old'}],'rule':{'sha256':'rule'},'engineer':{'confirmed_by':None}}}
    def test_review_is_scoped_and_rejection_preserves_unknown_result(self):
        f=self.finding()
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'reviews.json'
            for action in ('confirm','reject'):
                record=make_review(action,'SYNTHETIC测试','只核对工具输出','本条缺资料结论',finding=f,drawing_hash='drawing',synthetic=True)
                events=append_review(p,record);current=deepcopy(f);apply_reviews([current],'drawing',events)
                self.assertEqual(current['result'],'无法判定');self.assertEqual(current['manual_review']['action'],action)
                self.assertEqual(bool(current['decision']['engineer']['confirmed_by']),action=='confirm')
            changed=deepcopy(f);changed['decision']['inputs'][0]['content_fingerprint']='changed'
            apply_reviews([changed],'drawing',events);self.assertNotIn('manual_review',changed)
            bad=json.loads(p.read_bytes());bad['events'][0]['scope']='篡改';p.write_text(json.dumps(bad))
            with self.assertRaisesRegex(ValueError,'校验失败'):read_reviews(p)
    def test_identity_transfer_is_bound_to_exact_dependencies_and_latest_intent(self):
        old=self.finding()['decision'];old['engineer']={'confirmed_by':'SYNTHETIC旧复核人'}
        new=deepcopy(old);new['id']='new';new['inputs'][0]['source_identity_sha256']='new'
        record=make_review('confirm_identity_transfer','SYNTHETIC新复核人','已核对对应','仅原范围',old=old,new=new,mapping={'r':'r'},synthetic=True)
        self.assertTrue(inherit_decision(old,new,{'r':'r'},identity_confirmation=record)['inherited'])
        record['action']='reject_identity_transfer'
        self.assertEqual(inherit_decision(old,new,{'r':'r'},identity_confirmation=record)['status'],'pending_identity')
        record['action']='confirm_identity_transfer';new['inputs'][0]['source_identity_sha256']='third'
        self.assertFalse(inherit_decision(old,new,{'r':'r'},identity_confirmation=record)['inherited'])
        with self.assertRaises(ValueError):make_review('confirm','','x','x',finding=self.finding(),drawing_hash='drawing')

    def test_confirmed_tool_result_cannot_follow_a_different_result(self):
        old=self.finding()['decision'];old.update(result='无法判定');old['engineer']={'confirmed_by':'SYNTHETIC','review_event_sha256':'event'}
        new=deepcopy(old);new['result']='不通过'
        outcome=inherit_decision(old,new,{'r':'r'})
        self.assertEqual(outcome['status'],'invalidated');self.assertFalse(outcome['inherited'])

    def test_save_unsaved_example_carries_review_ledger_and_reopen_preserves_it(self):
        from cst.desktop import Workbench
        root=Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as folder:
            app=Workbench(Path(folder)/'runtime',root);saved=Path(folder)/'saved';saved.mkdir()
            event=make_review('confirm','SYNTHETIC','核对工具输出','本条',finding=self.finding(),drawing_hash='drawing',synthetic=True)
            expected=append_review(app.review_path(),event)
            app.perform('save',{'path':str(saved)})
            other=Workbench(Path(folder)/'another-runtime',root);other.perform('open',{'path':str(saved)})
            self.assertEqual(read_reviews(other.review_path()),expected)
    def test_save_refuses_different_destination_ledger(self):
        from cst.desktop import Workbench
        root=Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as folder:
            app=Workbench(Path(folder)/'runtime',root);saved=Path(folder)/'saved';saved.mkdir()
            event=make_review('confirm','SYNTHETIC','核对工具输出','本条',finding=self.finding(),drawing_hash='drawing',synthetic=True)
            append_review(app.review_path(),event)
            event['name']='SYNTHETIC另一个项目';target=saved/'geomverity-reviews.json';previous=append_review(target,event)
            with self.assertRaisesRegex(ValueError,'已有其他人工'):app.perform('save',{'path':str(saved)})
            self.assertEqual(read_reviews(target),previous)
            self.assertFalse((saved/'geomverity-project.json').exists())
            occupied=Path(folder)/'occupied';occupied.mkdir();(occupied/'geomverity-project.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'已有项目'):app.perform('save',{'path':str(occupied)})
            self.assertFalse((occupied/'geomverity-reviews.json').exists())
