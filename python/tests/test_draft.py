# SPDX-License-Identifier: MPL-2.0
import copy,json,tempfile,unittest,yaml
from pathlib import Path
from unittest.mock import patch
from cst.draft import validate_draft,draft_rule,save_draft
from cst.rules import load_rules,evaluate
ROOT=Path(__file__).resolve().parents[2]
CACHE=ROOT/'ai_cache/draft_8207071988f47e84b2e38bca.json'
class DraftTests(unittest.TestCase):
    def record(self):return json.loads(CACHE.read_bytes())
    def test_unapproved_excluded_then_approved_three_values(self):
        r=self.record();parsed=validate_draft(r['answer'],**r['source'])
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);out=save_draft(parsed,**r['source'],output=root/'drafts')
            self.assertEqual(load_rules(root),[])
            path=Path(out['output']);data=yaml.safe_load(path.read_text(encoding='utf-8'))
            data.update(approved=True,approved_by='SYNTHETIC审批演示')
            path.write_text(yaml.safe_dump(data,allow_unicode=True),encoding='utf-8')
            rule=load_rules(root)[0]
            for shared,result in [([], '通过'),(['ELEVATOR_SHAFT'],'不通过'),(None,'无法判定')]:
                with self.subTest(result=result):
                    item={'id':'synthetic-shaft','origin':'SYNTHETIC','status':'review','use':'ELECTRICAL_SHAFT','shared_uses':shared,'shared_uses_complete':True}
                    out=evaluate(rule,item,True)
                    self.assertEqual(out['result'],result);self.assertEqual(out['origin'],'SYNTHETIC')
            before=path.read_bytes();save_draft(parsed,**r['source'],output=root/'drafts')
            self.assertEqual(path.read_bytes(),before)
    def test_model_cannot_approve_or_invent_predicate_or_rewrite_source(self):
        r=self.record()
        for mutation in ['approval','predicate','source']:
            a=copy.deepcopy(r['answer'])
            if mutation=='approval':a['rule'].update(approved=True,approved_by='AI')
            elif mutation=='predicate':a['rule']['check']['require']['predicate']='short_circuit_current'
            else:a['rule']['clauses'][0]['text']='编造条文'
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):validate_draft(a,**r['source'])
    def test_real_cache_replay_has_no_network(self):
        with tempfile.TemporaryDirectory() as folder,patch('cst.draft.httpx.Client',side_effect=AssertionError('NETWORK_FORBIDDEN')):
            result=draft_rule(cache=CACHE,replay=True,output=folder)
            self.assertFalse(result['network_used']);self.assertFalse(result['approved'])
            result=draft_rule(cache=ROOT/'ai_cache/draft_4b4985074e1ddb72c9558a79.json',replay=True,output=folder)
            self.assertEqual(result['status'],'needs_new_predicate');self.assertIsNone(result['output'])
    def test_bad_numeric_condition_rejected(self):
        r=self.record();a=copy.deepcopy(r['answer'])
        a['rule']['check']={'predicate':'long_side_gt'}
        with self.assertRaises(ValueError):validate_draft(a,**r['source'])
