# SPDX-License-Identifier: MPL-2.0
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from cst.model import load,L1,L2,L3,FILENAMES
from cst.claims import check_claims,recheck_claims,parse_document,validate_report_context
from cst.evidence import default_registry,Resolution
from cst.decisions import bundle,verify_bundle

ROOT=Path(__file__).resolve().parents[2]


def document(text,refs,values=None,kind='reference'):
    return {'schema_version':'claims.v1','original_text':text,'claims':[{'id':'c1','text':text,'span':{'start':0,'end':len(text)},'refs':refs,'values':values or {},'kind':kind,'extraction':'manual','generated_by':None}]}


class ClaimsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.templates={m:load(ROOT/'samples/A',m) for m in (L1,L2,L3)}

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.directory=Path(self.temp.name)/'SYNTHETIC';self.directory.mkdir()
        self.make_scan(self.directory)

    def tearDown(self):self.temp.cleanup()

    def make_scan(self,path,*,width=6000,hash_value='a',unrelated=False):
        path.mkdir(exist_ok=True)
        room=next(o for o in self.templates[L3].objects if o.type=='space').model_dump()
        geom=room['geometry'];geom.update(is_closed=True,is_exact=True,extraction_method='SYNTHETIC_rectangle',paths=[[{'x':float(x),'y':float(y),'z':0.0} for x,y in [(0,0),(width,0),(width,5000),(0,5000),(0,0)]]])
        geom['bounds'].update(min_x=0.0,min_y=0.0,min_z=0.0,max_x=float(width),max_y=5000.0,max_z=0.0,is_valid=True)
        source=room['source'];source.update(drawing_hash=hash_value*64,handle='SYN1',stable_path='SYNTHETIC/1',block_path=[],xref_path=[],xref_hashes=[])
        room.update(semantic_id='sem_syn',raw_label='SYNTHETIC房间',classification='SYNTHETIC',use_code='UNKNOWN',status='review',reason_codes=[],evidence=[{'code':'SYNTHETIC','kind':'geometry_fact','value':'geo_syn','source_handle':'SYN1','weight':1.0}])
        fact=self.templates[L2].facts[0].model_dump();fact.update(geometry_id='geo_syn',source_primitive_ids=['prim_syn'],source=source,geometry=geom,evidence=[],reason_codes=[])
        fact['measurements'].update(area_is_available=True,area_square_millimeters=float(width*5000),area_method='SYNTHETIC')
        primitive=self.templates[L1].primitives[0].model_dump();primitive.update(primitive_id='prim_syn',source=source,raw_geometry=geom,evidence=[],reason_codes=[])
        for model in (L1,L2,L3):
            data=self.templates[model].model_dump();data['drawing']['sha256']=hash_value*64;data['drawing']['file_name']='SYNTHETIC_NO_DWG';data.update(status='review',reason_codes=[],provider_diagnostics=[])
            if model==L1:data.update(primitives=[primitive],proxy_ledger=[])
            elif model==L2:data.update(facts=[fact],relations=[])
            else:
                objects=[room]
                if unrelated:
                    other=json.loads(json.dumps(room));other.update(semantic_id='sem_other',raw_label='SYNTHETIC其他房间');other['source']['handle']='SYN2';objects.append(other)
                data.update(objects=objects,relations=[],findings=[],proxy_ledger=[])
            (path/FILENAMES[model]).write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')

    def check(self,doc,**kwargs):
        with patch('httpx.Client',side_effect=AssertionError('NETWORK_FORBIDDEN')):
            return check_claims(self.directory,doc,**kwargs)

    def test_controlled_errors_from_existing_fixture(self):
        fixture=json.loads((ROOT/'ai_cache/SYNTHETIC_validator.json').read_bytes())
        finding={'id':'finding_syn','rule_id':'R3','result':'无法判定','reason':'SYNTHETIC缺资料','input_confidence':'输入待复核','object_ids':['sem_syn'],'source_handles':['SYN1'],'values':{}}
        for case in fixture['cases']:
            answer=json.loads(json.dumps(case['answer']))
            claim=answer['claims'][0]
            claim['object_ids']=['sem_missing' if r=='syn-missing' else 'sem_syn' for r in claim['object_ids']]
            claim['values']={k.replace('syn-room','sem_syn'):v for k,v in claim['values'].items()}
            if case['name']=='无法判定说成通过':claim['object_ids']=['finding_syn']
            with self.subTest(case=case['name']),patch('cst.ai.ReadTools._findings',return_value={'finding_syn':finding}):
                value=self.check(answer)
                self.assertEqual(value['valid'],case['expected_valid'])
                self.assertEqual(value['rows'][0]['conclusion'],'支持' if case['expected_valid'] else '矛盾')
                self.assertFalse(value['full_original_preserved'])

    def test_area_read_and_geometry_are_independent(self):
        path=self.directory/FILENAMES[L2];data=json.loads(path.read_bytes());data['facts'][0]['measurements']['area_square_millimeters']=31000000.0;path.write_text(json.dumps(data))
        result=self.check(document('面积30平方米',['sem_syn'],{'sem_syn.area_m2':30.0},'area'))
        checks=result['rows'][0]['checks']
        self.assertEqual(next(c for c in checks if c['method']=='数值读取')['conclusion'],'矛盾')
        self.assertEqual(next(c for c in checks if c['method']=='几何重算')['conclusion'],'支持')
        self.assertTrue(result['full_original_preserved'])
        self.assertEqual(result['rows'][0]['conclusion'],'需复核')
        self.assertEqual(result['rows'][0]['validity'],'需复核')
        self.assertFalse(result['valid'])
        # 反向分歧：读取与主张一致，但新版轮廓重算不一致，也必须需复核。
        self.make_scan(self.directory,width=6200)
        path=self.directory/FILENAMES[L2];data=json.loads(path.read_bytes());data['facts'][0]['measurements']['area_square_millimeters']=30000000.0;path.write_text(json.dumps(data))
        result=self.check(document('面积30平方米',['sem_syn'],{'sem_syn.area_m2':30.0},'area'))
        self.assertEqual(result['rows'][0]['conclusion'],'需复核')
        self.assertEqual(next(c for c in result['rows'][0]['checks'] if c['method']=='数值读取')['conclusion'],'支持')
        self.assertEqual(next(c for c in result['rows'][0]['checks'] if c['method']=='几何重算')['conclusion'],'矛盾')

    def test_unknown_namespace_is_not_false_and_plugin_errors_are_separate(self):
        result=self.check(document('外部对象存在',['ifc:missing']))
        self.assertEqual((result['rows'][0]['conclusion'],result['rows'][0]['execution']),('未知','无验证器'))
        registry=default_registry()
        registry.register('ifc:',lambda tools,ref:Resolution(ref,'external',True,{'id':ref}),version='SYNTHETIC.1')
        self.assertTrue(self.check(document('外部对象存在',['ifc:1']),registry=registry)['valid'])
        def broken(tools,ref):raise RuntimeError('SYNTHETIC')
        registry.register('broken:',broken)
        self.assertEqual(self.check(document('外部对象存在',['broken:1']),registry=registry)['rows'][0]['execution'],'执行失败')

    def test_span_mismatch_and_nonfinite_values_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'结构化对象'):parse_document([])
        value=document('原文不可替换',['sem_syn']);value['claims'][0]['span']['end']=1
        with self.assertRaises(ValueError):parse_document(value)
        with self.assertRaises(ValueError):self.check(document('面积未知',['sem_syn'],{'sem_syn.area_m2':float('nan')},'area'))

    def test_no_refs_empty_claims_and_unsupported_mean_unknown(self):
        self.assertFalse(self.check(document('没有引用',[]))['valid'])
        self.assertFalse(self.check({'claims':[],'reason':'没有依据'})['valid'])
        self.assertEqual(self.check(document('任意专业判断',['sem_syn'],kind='unsupported'))['rows'][0]['conclusion'],'未知')

    def test_negated_confirmation_and_contrast(self):
        self.assertTrue(self.check(document('尚未确认',['sem_syn'],kind='reference'))['valid'])
        self.assertFalse(self.check(document('尚未确认，但已确认',['sem_syn'],kind='status'))['valid'])
        self.assertEqual(self.check(document('仍有效',['sem_syn'],kind='status'))['rows'][0]['conclusion'],'未知')

    def test_invalid_outline_is_unknown_not_zero_area(self):
        path=self.directory/FILENAMES[L3];data=json.loads(path.read_bytes());data['objects'][0]['geometry']['is_closed']=False;path.write_text(json.dumps(data))
        result=self.check(document('面积30平方米',['sem_syn'],{'sem_syn.area_m2':30.0},'area'))
        self.assertEqual(result['rows'][0]['conclusion'],'未知')
        self.assertEqual(next(c for c in result['rows'][0]['checks'] if c['method']=='几何重算')['execution'],'无验证器')

    def test_dependency_recheck_preserves_unrelated_change_but_reviews_area_change(self):
        original=self.check(document('面积30平方米',['sem_syn'],{'sem_syn.area_m2':30.0},'area'))
        self.make_scan(self.directory,unrelated=True)
        result=recheck_claims(self.directory,original)
        self.assertTrue(result['recheck']['context_updated']);self.assertEqual(result['rows'][0]['validity'],'有效')
        self.make_scan(self.directory,width=7000)
        result=recheck_claims(self.directory,original)
        self.assertEqual(result['rows'][0]['validity'],'需复核');self.assertEqual(result['rows'][0]['conclusion'],'矛盾')

    def test_uncertain_mapping_requires_review_and_lineage_context(self):
        original=self.check(document('对象存在',['sem_syn']))
        newer=Path(self.temp.name)/'new';self.make_scan(newer,hash_value='b')
        with self.assertRaisesRegex(ValueError,'变更结果'):recheck_claims(newer,original)
        path=newer/FILENAMES[L3];data=json.loads(path.read_bytes());data['objects']=[];path.write_text(json.dumps(data))
        delta={'old_hash':'a'*64,'new_hash':'b'*64,'changes':[],'new_check':{'findings':[]},'conclusion_changes':[]}
        changes=Path(self.temp.name)/'diff.json';changes.write_text(json.dumps(delta))
        result=recheck_claims(newer,original,changes)
        self.assertEqual((result['rows'][0]['conclusion'],result['rows'][0]['validity']),('未知','需复核'))

    def test_bundle_explicitly_covers_report_and_detects_tampering(self):
        report=self.check(document('面积30平方米',['sem_syn'],{'sem_syn.area_m2':30.0},'area'),output=Path(self.temp.name)/'report')
        output=Path(self.temp.name)/'bundle'
        bundle(self.directory,output,claims_check=Path(self.temp.name)/'report/claims-check.json')
        self.assertEqual(verify_bundle(output)['failure_count'],0)
        manifest=json.loads((output/'bundle-manifest.json').read_bytes());self.assertIn('claims-check.json',manifest['files'])
        (output/'claims-check.json').write_text('{}')
        self.assertGreater(verify_bundle(output)['failure_count'],0)
        self.make_scan(self.directory,width=7000)
        with self.assertRaisesRegex(ValueError,'不对应'):validate_report_context(report,self.directory)

    def test_failed_snapshot_and_wrong_units_are_unknown(self):
        for field,value in [('status','failed'),('units','m')]:
            self.make_scan(self.directory)
            path=self.directory/FILENAMES[L2];data=json.loads(path.read_bytes())
            if field=='status':data['status']=value
            else:data['drawing']['geometry_units']=value
            path.write_text(json.dumps(data))
            result=self.check(document('面积30平方米',['sem_syn'],{'sem_syn.area_m2':30.0},'area'))
            self.assertEqual(result['rows'][0]['conclusion'],'未知')

    def test_validity_assertion_matches_existing_inheritance_result(self):
        from cst.decisions import inherit_decision
        old={'id':'decision_syn','engineer':{'confirmed_by':'SYNTHETIC工程师'},'rule':{'id':'R3','sha256':'R'},'inputs':[{'object_id':'sem_syn','content_fingerprint':'old'}]}
        new=json.loads(json.dumps(old));new['inputs'][0]['content_fingerprint']='new'
        outcome=inherit_decision(old,new,{'sem_syn':'sem_syn'})
        (self.directory/'decisions.json').write_text(json.dumps({'decisions':[new]}))
        delta={'old_hash':'a'*64,'new_hash':'a'*64,'changes':[],'old_check':{'findings':[{'id':'finding_syn','decision':old}]},'new_check':{'findings':[{'id':'finding_syn','decision':new}]},'decision_inheritance':[{'old_decision_id':'decision_syn','new_decision_id':'decision_syn',**outcome}]}
        (self.directory/'changes.json').write_text(json.dumps(delta))
        result=self.check(document('原确认仍有效',['decision_syn'],kind='status'))
        self.assertEqual(result['rows'][0]['conclusion'],'矛盾')

    def test_changed_resolver_version_requires_review(self):
        first=default_registry();first.register('custom:',lambda tools,ref:Resolution(ref,'external',True,{'id':ref}),version='1')
        prior=self.check(document('外部对象存在',['custom:1']),registry=first)
        second=default_registry();second.register('custom:',lambda tools,ref:Resolution(ref,'external',True,{'id':ref}),version='2')
        self.assertEqual(recheck_claims(self.directory,prior,registry=second)['rows'][0]['validity'],'需复核')


    def test_comparison_pair_resolves_duplicate_source_locator(self):
        original=self.check(document('对象存在',['sem_syn']))
        newer=Path(self.temp.name)/'paired';self.make_scan(newer,hash_value='b',unrelated=True)
        path=newer/FILENAMES[L3];data=json.loads(path.read_bytes());data['objects'][0]['semantic_id']='sem_new';data['objects'][1]['source']['handle']='SYN1';path.write_text(json.dumps(data))
        delta={'old_hash':'a'*64,'new_hash':'b'*64,'changes':[{'old':{'id':'sem_syn'},'new':{'id':'sem_new'}}],'new_check':{'findings':[]},'conclusion_changes':[]}
        changes=Path(self.temp.name)/'paired-diff.json';changes.write_text(json.dumps(delta))
        result=recheck_claims(newer,original,changes)
        self.assertEqual(result['rows'][0]['validity'],'有效')
        self.assertEqual(result['rows'][0]['claim']['refs'],['sem_new'])

    def test_area_tolerance_both_sources_and_configuration(self):
        # 30m²矩形，0.5%=0.15m²；逐侧测试，避免用期望实现值照抄函数。
        for asserted, expected in [(30.14,'支持'),(29.86,'支持'),(30.16,'矛盾'),(29.84,'矛盾')]:
            with self.subTest(asserted=asserted):
                result=self.check(document('面积测试',['sem_syn'],{'sem_syn.area_m2':asserted},'area'))
                self.assertEqual(result['rows'][0]['conclusion'],expected)
                methods=[c for c in result['rows'][0]['checks'] if c.get('area_comparison')]
                self.assertEqual(len(methods),2)
                self.assertTrue(all(c['tolerance_m2']==0.15 for c in methods))
                self.assertAlmostEqual(methods[0]['difference_m2'],asserted-30.0)
        custom={'absolute_m2':0.001,'relative':0.0}
        prior=self.check(document('面积测试',['sem_syn'],{'sem_syn.area_m2':30.1},'area'))
        changed=recheck_claims(self.directory,prior,area_tolerance=custom)
        self.assertEqual(changed['rows'][0]['conclusion'],'矛盾')
        self.assertEqual(changed['rows'][0]['validity'],'需复核')
        self.assertEqual(changed['area_tolerance'],custom)
        for invalid in [[],False,{'relative':-0.1},{'absolute_m2':float('nan')},{'relative':True}]:
            with self.assertRaises(ValueError):self.check(document('对象存在',['sem_syn']),area_tolerance=invalid)

    def test_small_area_absolute_floor_and_missing_reading(self):
        self.make_scan(self.directory,width=100)
        for value,conclusion in [(0.509,'支持'),(0.511,'矛盾')]:
            result=self.check(document('小面积测试',['sem_syn'],{'sem_syn.area_m2':value},'area'))
            self.assertEqual(result['rows'][0]['conclusion'],conclusion)
        path=self.directory/FILENAMES[L2];data=json.loads(path.read_bytes())
        data['facts'][0]['measurements']['area_is_available']=False;path.write_text(json.dumps(data))
        result=self.check(document('小面积测试',['sem_syn'],{'sem_syn.area_m2':0.5},'area'))
        self.assertEqual(result['rows'][0]['conclusion'],'未知')
        self.assertFalse(result['valid'])

    def test_public_area_example_is_supported_without_editing_snapshot(self):
        result=check_claims(ROOT/'samples/A',json.loads((ROOT/'samples/claims/A-area.claims.json').read_bytes()))
        self.assertTrue(result['valid'])
        self.assertEqual(result['validator_version'],'claims-check.4')
        methods=[c for c in result['rows'][0]['checks'] if c.get('area_comparison')]
        self.assertTrue(all(c['conclusion']=='支持' for c in methods))
        self.assertGreater(methods[1]['absolute_difference_m2'],0.002)

    def test_nonfinite_recomputed_area_cannot_pass_via_infinite_tolerance(self):
        from types import SimpleNamespace
        with patch('cst.light_calc.outline_polygon',return_value=SimpleNamespace(area=float('inf'))):
            result=self.check(document('面积30平方米',['sem_syn'],{'sem_syn.area_m2':30.0},'area'))
        self.assertEqual(result['rows'][0]['conclusion'],'未知')
        self.assertFalse(result['valid'])
        json.dumps(result,allow_nan=False)


    def test_pending_identity_does_not_support_still_valid_and_legacy_requires_recheck(self):
        from cst.decisions import inherit_decision
        old={'id':'decision_syn','engineer':{'confirmed_by':'SYNTHETIC'},'rule':{'id':'R1','sha256':'R'},'inputs':[{'object_id':'sem_syn','content_fingerprint':'same','source_identity_sha256':'old'}]}
        new=json.loads(json.dumps(old));new['inputs'][0]['source_identity_sha256']='new'
        outcome=inherit_decision(old,new,{'sem_syn':'sem_syn'})
        self.assertEqual(outcome['status'],'pending_identity')
        (self.directory/'decisions.json').write_text(json.dumps({'decisions':[new]}))
        delta={'old_hash':'a'*64,'new_hash':'a'*64,'object_mapping':{'sem_syn':'sem_syn'},'changes':[],'old_check':{'findings':[{'id':'finding_syn','decision':old}]},'new_check':{'findings':[{'id':'finding_syn','decision':new}]},'decision_inheritance':[{'old_decision_id':'decision_syn','new_decision_id':'decision_syn',**outcome}]}
        path=self.directory/'changes.json';path.write_text(json.dumps(delta))
        result=self.check(document('原确认仍有效',['decision_syn'],kind='status'))
        self.assertEqual(result['rows'][0]['conclusion'],'需复核')
        del delta['decision_inheritance'][0]['policy_version'];path.write_text(json.dumps(delta))
        self.assertEqual(self.check(document('原确认仍有效',['decision_syn'],kind='status'))['rows'][0]['conclusion'],'未知')
    def status_delta(self, inherited=True, modern=False):
        from cst.decisions import inherit_decision
        old={'id':'decision_old','engineer':{'confirmed_by':'SYNTHETIC'},'rule':{'id':'R1','sha256':'R'},'inputs':[{'object_id':'sem_old','content_fingerprint':'same','source_identity_sha256':'old'}]}
        new=json.loads(json.dumps(old));new['id']='decision_new';new['inputs'][0].update(object_id='sem_syn',source_identity_sha256='new')
        outcome=inherit_decision(old,new,{'sem_old':'sem_syn'}) if modern else {'inherited':inherited,'state':'输入与规则未变化，可继承原范围确认' if inherited else '原确认因输入变化失效，需复核'}
        record={'old_decision_id':'decision_old','new_decision_id':'decision_new',**outcome}
        delta={'old_hash':'b'*64,'new_hash':'a'*64,'object_mapping':{'sem_old':'sem_syn'},'changes':[{'id':'change_1','old':{'id':'sem_old','name':'SYNTHETIC旧房间','handle':'SYN0'},'new':{'id':'sem_syn'}}],
            'old_check':{'findings':[{'id':'finding_old','object_ids':['sem_old'],'decision':old}]},'new_check':{'findings':[{'id':'finding_new','object_ids':['sem_syn'],'decision':new}]},
            'decision_inheritance':[record],'review_inheritance':[{'old_room':'sem_old','new_room':'sem_syn','inherited':False,'state':'原确认因变化失效，需复核'}]}
        path=self.directory/'changes.json';path.write_text(json.dumps(delta));return delta

    def test_old_side_ids_exist_but_historical_geometry_is_not_current(self):
        self.status_delta()
        result=self.check(document('旧侧引用存在',['sem_old','decision_old']))
        self.assertEqual(result['rows'][0]['conclusion'],'支持')
        self.assertIn('旧版引用存在',result['rows'][0]['checks'][0]['reason'])
        unavailable=self.check(document('旧房间面积30',['sem_old'],{'sem_old.area_m2':30.0},'area'))
        self.assertEqual(unavailable['rows'][0]['conclusion'],'未知')
        self.assertEqual(self.check(document('不存在',['sem_fabricated']))['rows'][0]['conclusion'],'矛盾')
        from cst.ai import ReadTools
        tools=ReadTools(self.directory)
        self.assertEqual(tools.get_evidence('sem_old')['kind'],'historical_object')
        self.assertEqual(tools.get_evidence('decision_old')['kind'],'decision')
        self.assertEqual(tools.list_decision_inheritance(limit=1)['items'][0]['old_decision_id'],'decision_old')

    def test_external_status_forms_and_explicit_inheritance_values(self):
        self.status_delta()
        forms=[('为 `inherited: true`，状态输入与规则未变化，可继承原范围确认',['decision_old','decision_new'],'支持'),
               ('inherited: false，原确认因输入变化失效，需复核',['decision_old','decision_new'],'矛盾'),
               ('房间输入复核继承中均为原确认因变化失效，需复核',['sem_old','sem_syn'],'支持'),
               ('虽有复核记录，但状态仍为需复核，不能视为新版已确认',['sem_syn'],'支持'),
               ('决策继承中 inherited: true 的条目仅继承本条输入条件范围，不构成整间房设计确认',['decision_new'],'支持')]
        for text,refs,expected in forms:
            with self.subTest(text=text):
                row=self.check(document(text,refs,kind='status'),status_basis='frozen_record')['rows'][0]
                self.assertEqual(row['conclusion'],expected);self.assertEqual(row['execution'],'已执行')
        explicit=document('仅核对继承字段',['decision_old'],{'decision_old.inherited':True},'status')
        self.assertEqual(self.check(explicit,status_basis='frozen_record')['rows'][0]['conclusion'],'支持')
        self.assertEqual(self.check(explicit)['rows'][0]['conclusion'],'未知')
        self.status_delta(modern=True)
        row=self.check(explicit)['rows'][0]
        self.assertEqual(row['conclusion'],'需复核');self.assertEqual(row['validity'],'需复核')
        self.assertEqual(next(c for c in row['checks'] if c['method']=='状态比对')['observed'],False)

    def test_identity_only_change_ids_exist_without_invented_impacts(self):
        delta=self.status_delta()
        delta['identity_changes']=[{'id':'change_4317','old':{'id':'sem_old','name':'SYNTHETIC','type':'wall'},'new':{'id':'sem_syn','name':'SYNTHETIC','type':'wall'},'kinds':['来源对象变化']}]
        (self.directory/'changes.json').write_text(json.dumps(delta))
        self.assertEqual(self.check(document('来源变化引用存在',['change_4317']))['rows'][0]['conclusion'],'支持')
        self.assertEqual(self.check(document('该引用的影响',['impact_change_4317']))['rows'][0]['conclusion'],'未知')

    def test_experimental_lighting_metadata_cannot_change_status_conclusion(self):
        delta=self.status_delta(modern=True)
        claim=document('原确认仍有效',['decision_new'],{'decision_new.inherited':True},'status')
        first=self.check(claim)
        delta.update(lighting_changes=[{'SYNTHETIC':'实验灯组任意变化'}],lighting_calculation_changes=[{'estimated_lux':999999}])
        (self.directory/'changes.json').write_text(json.dumps(delta))
        second=self.check(claim)
        self.assertEqual(first['rows'],second['rows'])
        self.assertNotEqual(first['changes_sha256'],second['changes_sha256'])
        self.assertEqual(self.check(document('实验灯具已通过',['generated_light_SYNTHETIC'],kind='status'))['rows'][0]['conclusion'],'未知')
    def test_warm_input_cache_recomputes_claim_and_protects_report_aliases(self):
        from cst.workbench_claims import ClaimsInputCache
        cache=ClaimsInputCache();doc=document('面积30',['sem_syn'],{'sem_syn.area_m2':30.0},'area')
        with patch.object(L3,'model_validate_json',wraps=L3.model_validate_json) as validate:
            first=cache.check(self.directory,doc);self.assertFalse(cache.info['models_reused'])
            next(d for d in first['rows'][0]['dependencies'] if d['kind']=='object')['locator']['block_path'].append('SYNTHETIC_MUTATION')
            doc['claims'][0]['values']['sem_syn.area_m2']=31.0
            second=cache.check(self.directory,doc)
            self.assertTrue(cache.info['models_reused']);self.assertEqual(validate.call_count,1)
            self.assertEqual(second['rows'][0]['conclusion'],'矛盾')
            self.assertEqual(next(d for d in second['rows'][0]['dependencies'] if d['kind']=='object')['locator']['block_path'],[])
            self.assertEqual(second,check_claims(self.directory,doc))

    def test_input_cache_reloads_same_size_same_timestamp_content_and_clears_failure(self):
        import os
        from cst.workbench_claims import ClaimsInputCache
        cache=ClaimsInputCache();doc=document('面积30',['sem_syn'],{'sem_syn.area_m2':30.0},'area');cache.check(self.directory,doc)
        path=self.directory/FILENAMES[L2];before=path.stat();raw=path.read_bytes();changed=raw.replace(b'30000000.0',b'31000000.0');self.assertNotEqual(raw,changed)
        path.write_bytes(changed);os.utime(path,ns=(before.st_atime_ns,before.st_mtime_ns))
        row=cache.check(self.directory,doc)['rows'][0]
        self.assertFalse(cache.info['models_reused']);self.assertEqual(row['conclusion'],'需复核')
        path.write_bytes(b'not valid JSON')
        with self.assertRaises(ValueError):cache.check(self.directory,doc)
        self.assertEqual(cache.info,{})
        self.assertFalse(cache._models)
