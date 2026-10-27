# SPDX-License-Identifier: MPL-2.0
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from cst.desktop import Workbench
from cst.workbench_compare import compare_versions, review_context
ROOT=Path(__file__).resolve().parents[2]

class CompareTaskTests(unittest.TestCase):
    def test_requires_same_drawing_and_distinct_project_versions_before_computing(self):
        with tempfile.TemporaryDirectory() as folder,patch('cst.workbench_compare.api.diff') as diff:
            app=Workbench(folder,ROOT);a,b=app.project.versions[:2]
            for old,new,same in [(a.id,b.id,False),(a.id,a.id,True),('missing',b.id,True)]:
                with self.assertRaises(ValueError):compare_versions(app.project,old,new,Path(folder)/'compare',same)
            diff.assert_not_called()

    def test_compare_and_focus_reuse_core_output_and_clear_on_project_change(self):
        change={'id':'change_SYNTHETIC','old':{'id':'sem_old','name':'SYNTHETIC旧房间','type':'space'},'new':{'id':'sem_new','name':'SYNTHETIC新房间','type':'space'},'kinds':['几何变化'],'impact':{'result':'待复核','rooms':[]},'suggested_work':{'approved':False,'items':[]},'new_geometry':{'paths':[],'bounds':{'is_valid':True}}}
        report={'old_hash':'a','new_hash':'b','change_count':1,'changes':[change],'decision_inheritance':[{'state':'原确认因输入变化失效，需复核','inherited':False}],'review_inheritance':[]}
        def diff(old,new,output,**kwargs):
            output.mkdir(parents=True);(output/'diff.json').write_text(json.dumps(report));return {'change_count':1}
        def view(directory,path,**kwargs):path.write_text('SYNTHETIC viewer');return {'output':str(path)}
        with tempfile.TemporaryDirectory() as folder,patch('cst.workbench_compare.inspect_scan',return_value={'load_ok':True,'tone':'warning','conclusion':'SYNTHETIC待复核'}),patch('cst.workbench_compare.api.diff',side_effect=diff) as calculation,patch('cst.view.write_view',side_effect=view) as drawing:
            app=Workbench(folder,ROOT);a,_,b=app.project.versions
            app.perform('compare',{'old_id':a.id,'new_id':b.id,'same_drawing':True})
            self.assertEqual(calculation.call_args.args[:2],(a.scan_directory,b.scan_directory))
            displayed=app.state()['comparison']
            self.assertEqual(displayed['decision_inheritance'],report['decision_inheritance'])
            self.assertNotIn('new_geometry',displayed['changes'][0])
            self.assertTrue(displayed['changes'][0]['can_locate'])
            with self.assertRaisesRegex(ValueError,'轮廓'):app.perform('locate_change',{'change_id':'missing'})
            app.perform('locate_change',{'change_id':change['id']})
            self.assertIn('&room=change_SYNTHETIC',app.state()['viewer'])
            self.assertEqual(app.project.current_version_id,b.id)
            self.assertEqual(drawing.call_args.kwargs['changes'],app.comparison['path'])
            app.perform('example',{})
            self.assertIsNone(app.state()['comparison']);self.assertIsNone(app.state()['viewer'])

    def test_failed_or_incomplete_inputs_do_not_reach_comparison(self):
        with tempfile.TemporaryDirectory() as folder,patch('cst.workbench_compare.api.diff') as diff:
            app=Workbench(folder,ROOT);a,_,b=app.project.versions
            for report in [{'load_ok':True,'tone':'failed','conclusion':'SYNTHETIC扫描失败'}, {'load_ok':False,'tone':'unknown','conclusion':'SYNTHETIC数据不完整'}]:
                with patch('cst.workbench_compare.inspect_scan',return_value=report):
                    with self.assertRaisesRegex(ValueError,'不可比较'):compare_versions(app.project,a.id,b.id,Path(folder)/'compare',True)
            diff.assert_not_called()

    def test_known_public_different_drawings_are_rejected_before_loading(self):
        with tempfile.TemporaryDirectory() as folder,patch('cst.workbench_compare.inspect_scan') as inspect,patch('cst.workbench_compare.api.diff') as diff:
            app=Workbench(folder,ROOT);a,b,_=app.project.versions
            with self.assertRaisesRegex(ValueError,'不同图纸'):compare_versions(app.project,a.id,b.id,Path(folder)/'compare',True)
            inspect.assert_not_called();diff.assert_not_called()

    def test_review_context_links_room_and_rule_without_changing_inheritance(self):
        from copy import deepcopy
        report={'old_check':{'findings':[{'decision':{'id':'old','engineer':{'confirmed_by':'SYNTHETIC复核人','scope':'仅出口条件'}},'object_name':'SYNTHETIC房间','object_ids':['room_old'],'rule_title':'出口数量','result':'通过','reason':'已核对条件','scope':'数量初查','clauses':[{'article':'SYNTHETIC'}]}]},
                'new_check':{'findings':[{'decision':{'id':'new'},'object_name':'SYNTHETIC房间新版','object_ids':['room_new'],'result':'无法判定','reason':'条件变化'}]},
                'review_inheritance':[{'old_room':'room_old','state':'原确认因变化失效，需复核'}],
                'decision_inheritance':[{'old_decision_id':'old','new_decision_id':'new','rule_id':'R1','state':'原确认因输入变化失效，需复核','inherited':False}, {'old_decision_id':'missing','new_decision_id':None,'rule_id':'R2','state':'新版无对应决策，原确认失效','inherited':False}]}
        prior=deepcopy(report);rows=review_context(report)
        self.assertEqual(rows[0]['old']['object_name'],'SYNTHETIC房间')
        self.assertEqual(rows[0]['new']['reason'],'条件变化')
        self.assertEqual(rows[0]['engineer']['scope'],'仅出口条件')
        self.assertIsNone(rows[1]['old']['object_name'])
        self.assertEqual(rows[0]['room_review']['state'],'原确认因变化失效，需复核')
        self.assertIsNone(rows[1]['room_review'])
        self.assertEqual(report,prior)
