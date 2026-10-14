# SPDX-License-Identifier: MPL-2.0
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from cst.ai import validate,replay,ReadTools
ROOT=Path(__file__).resolve().parents[2]
class AITests(unittest.TestCase):
    def test_grounded_and_fabricated_claims(self):
        fixture=json.loads((ROOT/'ai_cache/SYNTHETIC_validator.json').read_bytes())
        for case in fixture['cases']:
            with self.subTest(case=case['name']):self.assertEqual(validate(case['answer'],fixture['ground_truth'])['valid'],case['expected_valid'])
    def test_replay_never_constructs_network_client(self):
        with patch('cst.ai.httpx.Client',side_effect=AssertionError('NETWORK_FORBIDDEN')):
            result=replay(ROOT/'ai_cache/SYNTHETIC_validator.json')
            self.assertFalse(result['network_used']);self.assertEqual(result['origin'],'SYNTHETIC')
    def test_no_reference_not_accepted(self):
        self.assertFalse(validate({'claims':[{'text':'确定合规','object_ids':[],'values':{}}]}, {'objects':{},'summary':{}})['valid'])

    def test_unknown_finding_cannot_be_promoted_to_pass(self):
        from types import SimpleNamespace
        tools=ReadTools.__new__(ReadTools)
        tools.objects={};tools.data=SimpleNamespace()
        f={'id':'finding_R3_1','rule_id':'R3','result':'无法判定','reason':'缺少上一层语义','input_confidence':'输入待复核','object_ids':['room1'],'source_handles':['A1'],'values':{}}
        tools.findings={f['id']:f}
        tools.summary=lambda: {}
        a={'claims':[{'text':'缺少上一层语义，无法判定','object_ids':[f['id']],'values':{f['id']+'.result':'无法判定'}}]}
        self.assertTrue(validate(a,tools.truth(a))['valid'])
        a['claims'][0]['text']='审查通过'
        self.assertFalse(validate(a,tools.truth(a))['valid'])
        self.assertEqual(tools.list_findings(rule_id='R3')['total'],1)

    def test_negative_pass_phrases_and_contrast(self):
        truth={'objects':{'finding_R3_1':{'status':'review','result':'无法判定'}},'summary':{}}
        for text,valid in [('无法据此判定通过',True),('不能判定通过',True),('不足以说明已通过',True),('未审查通过',True),('尚未通过',True),('无法判定通过，但已通过',False),('审查通过',False)]:
            with self.subTest(text=text):
                a={'claims':[{'text':text,'object_ids':['finding_R3_1'],'values':{'finding_R3_1.result':'无法判定'}}]}
                self.assertEqual(validate(a,truth)['valid'],valid)
    def test_original_real_cache_false_rejection_resolved(self):
        record=json.loads((ROOT/'ai_cache/5f017b849c0d0aa748ed30c0.json').read_bytes())
        answer=json.loads(record['transcript'][1]['response']['choices'][0]['message']['content'])
        tools=ReadTools(ROOT/'samples/A')
        self.assertTrue(validate(answer,tools.truth(answer))['valid'])
