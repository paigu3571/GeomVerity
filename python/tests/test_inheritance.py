# SPDX-License-Identifier: MPL-2.0
import tempfile
import json
import unittest
from pathlib import Path
from copy import deepcopy
from cst.changes import diff
from cst.decisions import inherit_decision

class InheritancePolicyTests(unittest.TestCase):
    def test_source_identity_and_legacy_records_never_silently_inherit(self):
        old={'engineer':{'confirmed_by':'SYNTHETIC'},'rule':{'sha256':'R'},'inputs':[{'object_id':'a','content_fingerprint':'content','source_identity_sha256':'identity'}]}
        new=deepcopy(old);new['inputs'][0]['object_id']='b'
        self.assertEqual(inherit_decision(old,new,{'a':'b'})['status'],'inherited')
        new['inputs'][0]['source_identity_sha256']='other'
        pending=inherit_decision(old,new,{'a':'b'})
        self.assertEqual(pending['status'],'pending_identity');self.assertFalse(pending['inherited'])
        del new['inputs'][0]['source_identity_sha256']
        self.assertEqual(inherit_decision(old,new,{'a':'b'})['status'],'pending_identity')
        self.assertEqual(inherit_decision(old,new,{})['status'],'invalidated')
        self.assertEqual(inherit_decision(old,new,{'a':'b'},confirmation_available=False)['status'],'invalidated')

class PublicInheritanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import json
        root=Path(__file__).resolve().parents[2]
        cls.temp=tempfile.TemporaryDirectory()
        diff(root/'samples/A',root/'samples/A-change',cls.temp.name)
        cls.report=json.loads((Path(cls.temp.name)/'diff.json').read_bytes())
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def check_room(self,name,status):
        r=self.report
        review=next(row for row in r['review_inheritance'] if row['room_name']==name)
        decision=next(row for row in r['decision_inheritance'] if row['old_decision_id']==review['old_decision_id'])
        for key in ('status','state','reason','inherited','requires_confirmation','policy_version'):
            self.assertEqual(review[key],decision[key])
        self.assertEqual(review['status'],status);self.assertFalse(review['inherited'])
        finding=next(f for f in r['new_check']['findings'] if f['rule_id']=='R1' and f['object_name']==name)
        self.assertEqual(finding['result'],'无法判定')
        self.assertFalse(finding['engineer_reviewed']['reviewed_by'])
        return decision,finding
    def test_public_commercial_room_only_identity_change_requires_engineer(self):
        decision,_=self.check_room('商业配电房','pending_identity')
        old=next(f['decision'] for f in self.report['old_check']['findings'] if f['decision']['id']==decision['old_decision_id'])
        new=next(f['decision'] for f in self.report['new_check']['findings'] if f['decision']['id']==decision['new_decision_id'])
        outcome=inherit_decision(old,new,self.report['object_mapping'])
        self.assertEqual(outcome['status'],decision['status'])
    def test_public_charging_room_real_change_invalidates(self):
        self.check_room('预留充电桩配电房','invalidated')

    def test_public_identity_transfer_applies_original_conditions_only_after_explicit_review(self):
        from cst.reviews import make_review
        from cst.changes import inherit_reviews
        from cst.l4 import read_r1_confirmations,check
        r=self.report;root=Path(__file__).resolve().parents[2]
        old=next(f['decision'] for f in r['old_check']['findings'] if f['rule_id']=='R1' and f['object_name']=='商业配电房')
        new=next(f['decision'] for f in r['new_check']['findings'] if f['rule_id']=='R1' and f['object_name']=='商业配电房')
        record=make_review('confirm_identity_transfer','SYNTHETIC验收','已核对旧新来源对应','只沿用原出口条件',old=old,new=new,mapping=r['object_mapping'],synthetic=True)
        confirmations,_=read_r1_confirmations(root/'samples/A',r['old_hash'])
        inherited,rows=inherit_reviews(r['old_check']['findings'],r['new_check']['findings'],r['object_mapping'],set(),confirmations,[record])
        review=next(x for x in rows if x['room_name']=='商业配电房')
        self.assertEqual(review['status'],'inherited');self.assertTrue(review['inherited'])
        actual=check(root/'samples/A-change',inherited_confirmations=inherited)
        finding=next(f for f in actual['findings'] if f['rule_id']=='R1' and f['object_name']=='商业配电房')
        self.assertEqual(finding['result'],'通过');self.assertTrue(finding['engineer_reviewed']['reviewed_by'])
        reserved=next(x for x in rows if x['room_name']=='预留充电桩配电房')
        self.assertEqual(reserved['status'],'invalidated')

    def _workbench_for_report(self,directory):
        from cst.desktop import Workbench
        from cst.workbench_compare import display_report
        b=Workbench(directory,root=Path(__file__).resolve().parents[2],development=True)
        a,_,c=b.project.versions;b.project.select(c.id)
        report=deepcopy(self.report)
        b.comparison={'summary':{},'report':report,'path':str(Path(self.temp.name)/'diff.json'),'display':display_report(report,a,c,{'旧版':{'conclusion':'测试'},'新版':{'conclusion':'测试'}})}
        b.comparison['input_guard']=tuple(b._claims_cache()._guard(v.scan_directory,None,None,'current') for v in (a,c))
        return b

    def test_room_grouping_keeps_source_evidence_and_does_not_turn_unknown_to_pass(self):
        from cst.engineering import room_tasks
        rooms=room_tasks(self.report)
        self.assertGreater(len(rooms),7)
        source_ids={i for r in rooms for i in r['change_ids']}
        impacted={c['id'] for c in self.report['changes'] if c.get('impact',{}).get('rooms')}
        spaces={c['id'] for c in self.report['changes'] if (c['new'] or c['old'])['type']=='space'}
        self.assertEqual(source_ids,impacted|spaces)
        self.assertEqual(sum(r['requires_decision'] for r in rooms),2)
        charge=next(r for r in rooms if r['name']=='预留充电桩配电房')
        self.assertEqual(next(c for c in charge['checks'] if c['rule_id']=='R1')['result'],'无法判定')
        self.assertTrue(all(len(r['change_ids'])==len(set(r['change_ids'])) for r in rooms))

    def test_review_save_reuses_findings_and_moves_room_item_to_recorded_without_passing(self):
        from unittest.mock import patch
        from cst.reviews import read_reviews
        with tempfile.TemporaryDirectory() as t:
            b=self._workbench_for_report(t)
            with patch('cst.ai.ReadTools',side_effect=AssertionError('已比较事项不应重新加载模型')):
                b.perform('review_load',{})
                f=next(f for f in b.review_findings['findings'] if f['rule_id']=='R1' and f.get('object_name')=='预留充电桩配电房')
                b.perform('review_write',{'finding_id':f['id'],'name':'SYNTHETIC','comment':'资料未齐，测试待补资料流转','scope':f['object_name'],'action':'confirm','synthetic':True})
            updated=next(row for row in b.review_findings['findings'] if row['id']==f['id'])
            self.assertEqual(updated['result'],'无法判定')
            self.assertEqual(updated['manual_review']['scope'],'预留充电桩配电房')
            self.assertIn('已保存',b.message)
            self.assertNotEqual(b.comparison['path'],str(Path(self.temp.name)/'diff.json'))
            stored=json.loads(Path(b.comparison['path']).read_bytes())
            self.assertEqual(next(row for row in stored['new_check']['findings'] if row['id']==f['id'])['manual_review']['origin'],'SYNTHETIC')
            self.assertTrue(next(r for r in b.comparison['display']['engineering_rooms'] if r['name']=='预留充电桩配电房')['confirmation_recorded'])
            self.assertEqual(read_reviews(b.review_path())[0]['origin'],'SYNTHETIC')
            b.perform('review_write',{'finding_id':f['id'],'name':'SYNTHETIC','comment':'驳回后重新核对','scope':f['object_name'],'action':'reject','synthetic':True,'disposition':'needs_data'})
            reopened=next(r for r in b.comparison['display']['engineering_rooms'] if r['name']=='预留充电桩配电房')
            self.assertFalse(reopened['confirmation_recorded']);self.assertTrue(reopened['requires_decision'])
            self.assertIn('回到待处理',b.message)
            self.assertEqual(next(row for row in b.review_findings['findings'] if row['id']==f['id'])['result'],'无法判定')

            with patch.object(b._claims_cache(),'_guard',return_value=('changed',)):
                with self.assertRaisesRegex(ValueError,'重新比较'):
                    b.perform('review_write',{'finding_id':f['id'],'name':'SYNTHETIC','comment':'不能保存过时确认','scope':f['object_name'],'action':'confirm','synthetic':True})
            self.assertEqual(len(read_reviews(b.review_path())),2)

    def test_transfer_refresh_matches_full_compare_without_geometry_matching(self):
        from unittest.mock import patch
        from cst.reviews import read_reviews
        import json,time
        with tempfile.TemporaryDirectory() as t:
            b=self._workbench_for_report(t)
            row=next(r for r in b.comparison['report']['review_inheritance'] if r['room_name']=='商业配电房')
            start=time.perf_counter()
            with patch('cst.changes.compare_objects',side_effect=AssertionError('不应重新匹配几何')):
                b.perform('review_transfer',{'old_decision_id':row['old_decision_id'],'identity_ack':True,'name':'SYNTHETIC','comment':'测试同房间沿用','scope':'商业配电房','action':'confirm_identity_transfer','synthetic':True})
            fast_seconds=time.perf_counter()-start
            root=Path(__file__).resolve().parents[2]
            diff(root/'samples/A',root/'samples/A-change',Path(t)/'full',review_records=read_reviews(b.review_path()))
            full=json.loads((Path(t)/'full/diff.json').read_bytes())
            for key in ('decision_inheritance','review_inheritance','conclusion_changes','new_check'):
                self.assertEqual(b.comparison['report'][key],full[key],key)
            print('SYNTHETIC refresh seconds',round(fast_seconds,3))
