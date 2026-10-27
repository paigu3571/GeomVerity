# SPDX-License-Identifier: MPL-2.0
from copy import deepcopy
import unittest
from cst.engineering_comparison import comparison_table
from cst.naming import digest


class EngineeringComparisonTests(unittest.TestCase):
    def fixture(self):
        report={'new_hash':'new','review_inheritance':[
            {'room_name':'甲配电房','status':'invalidated','old_decision_id':'one'},
            {'room_name':'乙配电房','status':'pending_identity','old_decision_id':'two'}]}
        rows=[{'claim':{'id':str(i),'text':f'| {name} | sem_internal | 原确认因变化失效，需复核 |',
                        'span':{'start':i*50,'end':i*50+40}},'validity':'有效','conclusion':'支持'}
              for i,name in enumerate(('甲配电房','乙配电房'))]
        checked={'status_basis':'current','drawing_hash':'new','changes_sha256':digest(report),'rows':rows}
        return {'report':checked},{'report':report}

    def test_reference_support_is_not_confirmation_status_support_and_inputs_stay_intact(self):
        workspace,comparison=self.fixture();before=deepcopy((workspace,comparison))
        rows=comparison_table(workspace,comparison)['rows']
        self.assertEqual([r['verdict'] for r in rows],['一致','不一致'])
        self.assertIn('内部编号变了',rows[1]['drawing_fact'])
        self.assertIn('需工程师确认',rows[1]['drawing_fact'])
        self.assertTrue(all('sem_' not in r['ai_excerpt'] and '|' not in r['ai_excerpt'] for r in rows))
        self.assertEqual((workspace,comparison),before)
        self.assertEqual(workspace['report']['rows'][1]['conclusion'],'支持')

    def test_stale_comparison_or_frozen_record_never_gets_current_verdict(self):
        w,c=self.fixture();c['report']['new_hash']='changed'
        self.assertFalse(comparison_table(w,c)['rows'])
        w,c=self.fixture();w['context_stale']=True
        self.assertFalse(comparison_table(w,c)['rows'])
        w,c=self.fixture();w['report']['status_basis']='frozen_record'
        self.assertFalse(comparison_table(w,c)['rows'])

    def test_missing_validator_or_unknown_state_is_not_invented_as_wrong(self):
        w,c=self.fixture();c['report']['review_inheritance'][1]['status']='unavailable'
        w['report']['changes_sha256']=digest(c['report'])
        self.assertEqual(comparison_table(w,c)['rows'][1]['verdict'],'查不了')
        w['report']['rows'][1]['validity']='需复核'
        self.assertEqual(len(comparison_table(w,c)['rows']),1)
        self.assertFalse(comparison_table(None,c)['rows'])

    def test_distinct_room_labels_and_ten_row_limit(self):
        w,c=self.fixture();c['report']['review_inheritance']=[{'room_name':f'配电房{i}','status':'pending_identity'} for i in range(12,0,-1)]
        w['report']['rows']=[{'claim':{'id':str(i),'text':f'| 配电房{i} | 原确认因变化失效 |','span':{'start':0,'end':20}},'validity':'有效'} for i in range(12,0,-1)]
        w['report']['changes_sha256']=digest(c['report'])
        rows=comparison_table(w,c)['rows'];self.assertEqual(len(rows),10)
        self.assertEqual(rows[0]['room_name'],'配电房12')
        self.assertTrue(all(r['room_name']!='配电房1' for r in rows))

    def test_room_change_claim_compares_fields_not_only_reference_existence(self):
        w,c=self.fixture();c['report']['changes']=[{'id':'change_1','kinds':['名称或用途变化','来源对象变化'],'old':{'name':'设备用房','type':'space'},'new':{'name':'水泵房','type':'space'}}]
        claim={'id':'water','text':'| change_1 | 名称或用途变化、来源对象变化 | ABC / 设备用房 / EQUIPMENT_ROOM | DEF / 水泵房 / PUMP_ROOM |','span':{'start':1,'end':2}}
        w['report']['rows'].append({'claim':claim,'validity':'有效','conclusion':'支持'});w['report']['changes_sha256']=digest(c['report'])
        row=comparison_table(w,c)['rows'][-1];self.assertEqual(row['verdict'],'一致');self.assertNotIn('ABC',row['ai_excerpt'])
        claim['text']=claim['text'].replace('水泵房','储藏间')
        self.assertEqual(comparison_table(w,c)['rows'][-1]['verdict'],'不一致')

    def test_review_target_uses_object_and_decision_ids_not_duplicate_names(self):
        from cst.engineering_comparison import review_target
        report={'object_mapping':{'old':'new'},'decision_inheritance':[{'old_decision_id':'d-old','new_decision_id':'d-new'}],
            'new_check':{'findings':[{'id':'wrong','object_ids':['other'],'object_name':'同名房','decision':{'id':'other-decision'}},
                                     {'id':'right','object_ids':['new'],'object_name':'同名房','decision':{'id':'d-new'}}]}}
        target=review_target(report,'old',old_decision_id='d-old')
        self.assertEqual((target['room_id'],target['finding_id']),('new','right'))
        self.assertIsNone(review_target(report,'missing',change_id='change_1')['finding_id'])
