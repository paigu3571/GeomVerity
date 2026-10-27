# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 张田
"""决策、依赖指纹及可导出的证据包；不把哈希当识别正确证明。"""
import hashlib,json,subprocess
from copy import deepcopy
from pathlib import Path
import yaml
from .model import load,L1,L2,L3,FILENAMES,session_memo
from .naming import digest
from .priority import finding_rank,room_priorities
ROOT=Path(__file__).resolve().parents[2]
ENGINE_VERSION='0.4.0b1'
INHERITANCE_VERSION='inheritance.2'

def object_fingerprint(obj):
    return digest({'type':obj.type,'name':obj.raw_label,'use':obj.use_code,'status':obj.status,'geometry':obj.geometry.model_dump()})

def rule_metadata(rule_id,rules_dir=None):
    from .resources import rules_directory
    directory=Path(rules_dir or rules_directory()).resolve()
    paths=sorted(list(directory.glob('*.yaml'))+list((directory/'drafts').glob('*.yaml')))
    signature=tuple((str(p),p.stat().st_mtime_ns,p.stat().st_size) for p in paths)
    result=session_memo('rule_metadata',(rule_id,str(directory)),signature,lambda:_rule_metadata(rule_id,directory))
    return deepcopy(result)


def _rule_metadata(rule_id,rules_dir=None):
    from .resources import rules_directory
    rules_dir=Path(rules_dir or rules_directory());paths=list(rules_dir.glob('*.yaml'))+list((rules_dir/'drafts').glob('*.yaml'))
    for path in paths:
        row=yaml.safe_load(path.read_text(encoding='utf-8'))
        if not isinstance(row,dict) or row.get('id')!=rule_id:continue
        clauses=row.get('clauses',[])
        for c in clauses:c.setdefault('code_version',c.get('code','').rsplit('-',1)[-1])
        catalog=rules_dir/'provenance.yaml'
        provenance=(yaml.safe_load(catalog.read_text(encoding='utf-8')) or {}).get('rules',{}).get(rule_id,{}) if catalog.is_file() else {}
        return {'drafted_by':provenance.get('drafted_by',{'type':'HISTORICAL_UNRECORDED','name':'未登记'}),'provenance_sha256':hashlib.sha256(catalog.read_bytes()).hexdigest() if catalog.is_file() else None,'id':rule_id,'version':row.get('rule_version',row.get('version','1')),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'clauses':clauses,'approved_by':row.get('approved_by'),'approved':row.get('approved',False)}
    raise ValueError('决策缺少规则文件：'+rule_id)

def decision(kind,key,result,ids,objects,rule,run_id,priority=None,engineer=None,evidence=None,llm=None):
    inputs=[{'object_id':i,'snapshot_sha256':digest(objects[i].model_dump()),'content_fingerprint':object_fingerprint(objects[i]),'source_identity_sha256':digest(objects[i].source.model_dump(exclude={'drawing_hash'})),'status':objects[i].status} for i in sorted(set(ids)) if i in objects]
    if any(i not in objects for i in ids):raise ValueError('决策输入引用缺失')
    engineer=engineer or {'confirmed_by':None,'date':None,'state':'待签字'}
    return {'id':'decision_'+digest([kind,key])[:24],'kind':kind,'result':result,'priority':priority or {'rank':3,'title':'布置候选','action':'工程师核对','boundary':'见输入与规则范围'},'inputs':inputs,'rule':rule,'engine_version':ENGINE_VERSION,'run_id':run_id,'llm':llm or {'used':False,'model':None,'cache_id':None},'engineer':engineer,'sign_off_state':'条件已复核，结论待签字' if engineer.get('confirmed_by') else '待工程师签字','evidence_refs':evidence or []}

def finding_decisions(data,findings,rules_dir=None,run_id=None):
    objects={o.semantic_id:o for o in data.objects}
    run_id=run_id or 'run_'+digest({'input':data.model_dump(),'rules':[rule_metadata(f['rule_id'],rules_dir) for f in findings]})[:24]
    rows=[]
    for f in findings:
        ids=set(f['object_ids'])
        for chain in f.get('evidence',[]):
            if chain.get('object_id'):ids.add(chain['object_id'])
            if chain.get('semantic_id'):ids.add(chain['semantic_id'])
        # Audit input set includes opening/wall/neighbour dependencies, even when only one room is checked.
        for audit in f['values'].get('opening_candidate_audit',[]):ids.update(audit['object_ids'])
        for n in f['values'].get('adjacent_candidates',[]):ids.update(i for i in (n.get('id'),n.get('wall_id')) if i)
        reviewed=f.get('engineer_reviewed',{});m=f['values'].get('manual_confirmation',{})
        engineer={'confirmed_by':reviewed.get('reviewed_by'),'date':reviewed.get('reviewed_date'),'state':'输入条件已复核' if reviewed.get('reviewed_by') else '待签字','scope':'本条输入条件，不是整间房设计签字','confirmation_record_sha256':digest(m) if m else None}
        priority=f.get('decision',{}).get('priority') or {'rank':finding_rank(f),'title':f.get('rule_title',f['rule_id']),'action':f.get('request_question') or '核对本项结果与输入条件','boundary':f.get('scope','')}
        d=decision('finding',f['id'],f['result'],ids,objects,rule_metadata(f['rule_id'],rules_dir),run_id,priority,engineer,f.get('evidence',[]))
        provenance=f['values'].get('naming_provenance',{})
        if provenance.get('model'):d['llm']={'used':True,'model':provenance['model'],'cache_id':provenance.get('cache_id'),'role':'术语提议，经工程师批准'}
        if f.get('decision',{}).get('priority_evidence'):d['priority_evidence']=f['decision']['priority_evidence']
        d['drawing_sha256']=data.drawing.sha256
        if f['rule_id']=='R1':d['confirmation_scope']={'kind':'r1_input_conditions','candidate_opening_ids':sorted(f['values'].get('candidate_opening_ids',[]))}
        d['finding_id']=f['id'];d['dependency_sha256']=digest({'fingerprints':sorted(i['content_fingerprint'] for i in d['inputs']),'rule_sha256':d['rule']['sha256']})
        f['decision']=d;f['priority_rank']=priority['rank'];rows.append(d)
    return rows

def lighting_decisions(data,lights,run_id):
    objects={o.semantic_id:o for o in data.objects};rows=[]
    for g in lights['groups']:
        if not g.get('rule_id'):continue
        ids={g['room_semantic_id']}
        ids|={p['mounting_wall_id'] for p in g['points'] if p.get('mounting_wall_id')}
        excluded=set(g.get('excluded_opening_handles',[]))
        ids|={o.semantic_id for o in data.objects if o.type in ('opening','door','window') and o.source.handle in excluded}
        metadata=rule_metadata(g['rule_id'])
        for point in g['points']:
            d=decision('generated_light',point['id'],'布置候选',ids,objects,metadata,run_id)
            d['generated_object_id']=point['id'];d['output_sha256']=digest({k:v for k,v in point.items() if k!='decision'});point['decision']=d;rows.append(d)
    return rows

def inherit_decision(old,new,mapping,*,confirmation_available=True,identity_confirmation=None):
    """所有确认共用的适用性判断。身份变化只进入待确认，不静默继承。"""
    def outcome(status,state,reason):
        return {'policy_version':INHERITANCE_VERSION,'status':status,'state':state,'reason':reason,
                'inherited':status=='inherited','requires_confirmation':status=='pending_identity',
                'confirmation_available':confirmation_available}
    if not old.get('engineer',{}).get('confirmed_by'):
        return outcome('unconfirmed','原记录无人工确认，不继承签字','无原人工确认记录')
    if not new:return outcome('invalidated','失效','新版无唯一对应决策，匹配不足')
    if not confirmation_available:return outcome('invalidated','失效','原确认记录不可用，不能带入新版检查')
    if old.get('engineer',{}).get('review_event_sha256') and old.get('result')!=new.get('result'):
        return outcome('invalidated','失效','工具结果变化，原人工输出核对不再适用')
    if old['rule']['sha256']!=new['rule']['sha256']:return outcome('invalidated','失效','规则内容变化')
    before=old.get('inputs',[]);after=new.get('inputs',[])
    expected={mapping.get(i['object_id']):i['content_fingerprint'] for i in before}
    actual={i['object_id']:i['content_fingerprint'] for i in after}
    if None in expected or len(expected)!=len(before) or len(actual)!=len(after) or expected!=actual:
        return outcome('invalidated','失效','依赖内容变化、依赖集合变化或匹配不足')
    scope=old.get('confirmation_scope',{})
    if scope.get('kind')=='r1_input_conditions':
        prior=scope.get('candidate_opening_ids',[]);current=new.get('confirmation_scope',{}).get('candidate_opening_ids')
        translated={mapping.get(i) for i in prior}
        if current is None or None in translated or len(translated)!=len(prior) or translated!=set(current):
            return outcome('invalidated','失效','门洞候选集合变化或匹配不足')
    identities={i['object_id']:i.get('source_identity_sha256') for i in after}
    if any(not i.get('source_identity_sha256') or not identities.get(mapping[i['object_id']]) or i['source_identity_sha256']!=identities[mapping[i['object_id']]] for i in before):
        from .reviews import valid_transfer
        if not valid_transfer(identity_confirmation,old,new,mapping):
            return outcome('pending_identity','内容未变但来源身份变化，需工程师确认后继承','来源身份变化或旧决策缺少身份指纹；尚未带入新版检查')
        result=outcome('inherited','继承','工程师已确认本次来源对应关系，原范围确认已带入新版')
        result.update(engineer=deepcopy(old['engineer']),identity_confirmation=deepcopy(identity_confirmation))
        return result
    result=outcome('inherited','继承','依赖内容、来源身份、规则及候选集合均未变化')
    result['engineer']=deepcopy(old['engineer'])
    return result


def bundle(directory,output='dist/bundle',changes=None,claims_check=None,review_records=None,issues=None):
    from .l4 import check
    from .lighting import generate_directory
    output=Path(output)
    review_records=[] if review_records is None else review_records
    from .reviews import validate_review_events,apply_reviews
    validate_review_events(review_records)
    if output.resolve()==Path(directory).resolve():raise ValueError('证据包输出不能覆盖输入快照目录')
    output.mkdir(parents=True,exist_ok=True);data=load(directory)
    delta=json.loads(Path(changes).read_bytes()) if changes else None
    claims_report=None;claims_delta=None
    if claims_check:
        from .claims import validate_report_context
        from .ai import ReadTools
        claims_report=json.loads(Path(claims_check).read_bytes())
        if delta is None and claims_report.get('changes_sha256'):
            delta=ReadTools(directory).changes_data
        validate_report_context(claims_report,directory,delta)
        claims_delta=json.loads(json.dumps(delta)) if delta else None
    elif (output/'claims-check.json').exists():
        raise ValueError('输出目录含旧核验报告，请显式指定报告或使用新的输出目录')
    if delta and delta['new_hash']!=data.drawing.sha256:raise ValueError('变更结果与当前快照不对应')
    checks=delta['new_check'] if delta else check(directory);lamps=generate_directory(directory)
    for finding in checks['findings']:
        if finding['engineer_reviewed']['record_file']:finding['engineer_reviewed']['record_file']='l4_confirmations.yaml'
    run_id='run_'+digest({'drawing':data.drawing.sha256,'input':digest(data.model_dump()),'rules':[rule_metadata(f['rule_id']) for f in checks['findings']],'comparison_old_hash':delta['old_hash'] if delta else None,'review_records_sha256':digest(review_records),'findings_state':[{'id':f['id'],'result':f['result'],'values':f['values'],'priority':f.get('decision',{}).get('priority')} for f in checks['findings']]})[:24]
    decisions=finding_decisions(data,checks['findings'],run_id=run_id)+lighting_decisions(data,lamps,run_id)
    apply_reviews(checks['findings'],data.drawing.sha256,review_records)
    if delta:
        delta['new_check']=checks
        room_alerts={}
        for c in delta['changes']:
            o=c['new'] or c['old'];oid=(c['new'] or {}).get('id')
            if o['type']=='space':room_alerts[c['id']]=room_priorities(oid,o['name'],[f for f in delta['new_check']['findings'] if oid in f['object_ids']],delta,(c['old'] or {}).get('id'))
        delta['priorities']=room_alerts
    def save(name,value):(output/name).write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2),encoding='utf-8')
    if review_records:save('engineer-reviews.json',{'schema_version':'engineer-reviews.v1','events':review_records,'boundary':'本机自报人工记录，非数字签名'})
    if claims_report:
        save('claims-check.json',claims_report)
        if claims_delta:save('claims-context-changes.json',claims_delta)
    for model in (L1,L2,L3):save(FILENAMES[model],load(directory,model).model_dump())
    exported_hash=hashlib.sha256((output/FILENAMES[L3]).read_bytes()).hexdigest()
    lamps['input_sha256']=exported_hash
    for group in lamps['groups']:group['input_sha256']=exported_hash
    from .uses import classify
    from .light_calc import calculate
    classifications=classify(directory)
    calculations=calculate(data,{r['object_id']:r for r in classifications['rows']},lamps)
    decisions.extend(r['decision'] for r in calculations['rows'])
    save('lighting_calculations.json',calculations)
    save('classifications.json',classifications)
    save('findings.json',checks);save('lighting_candidates.json',lamps);save('decisions.json',{'schema_version':'decisions.v1','run_id':run_id,'decisions':decisions})
    if delta:save('changes.json',delta)
    diagnostic_path=Path(issues) if issues else Path(directory)/'room_issues.json'
    if diagnostic_path.is_file():
        diagnostic=json.loads(diagnostic_path.read_bytes())
        source_snapshot=Path(directory)/'building-semantics.v1.json.gz'
        if not source_snapshot.is_file():source_snapshot=source_snapshot.with_suffix('')
        if diagnostic.get('snapshot_sha256')!=hashlib.sha256(source_snapshot.read_bytes()).hexdigest():raise ValueError('图纸问题诊断与源扫描不对应')
        diagnostic['source_snapshot_sha256']=diagnostic['snapshot_sha256']
        diagnostic['snapshot_sha256']=exported_hash
        save('room_issues.json',diagnostic)
    inputs={}
    for name in ('l4_confirmations.yaml','manifest.json'):
        path=Path(directory)/name
        if path.is_file():
            inputs[name]=hashlib.sha256(path.read_bytes()).hexdigest()
            if name=='l4_confirmations.yaml':(output/name).write_bytes(path.read_bytes())
    save('rules.json',{'rules':sorted({d['rule']['id']:d['rule'] for d in decisions}.values(),key=lambda r:r['id'])})
    save('input-records.json',inputs)
    try:commit=subprocess.run(['git','-C',str(ROOT),'rev-parse','HEAD'],capture_output=True,text=True,check=True).stdout.strip()
    except (OSError,subprocess.CalledProcessError):commit=None
    files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file() and p.name!='bundle-manifest.json'}
    save('bundle-manifest.json',{'schema_version':'trace-bundle.v1','claims_check_file':'claims-check.json' if claims_report else None,'claims_context_changes_file':'claims-context-changes.json' if claims_delta else None,'engine_version':ENGINE_VERSION,'engine_commit':commit,'engine_source_sha256':digest({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(__file__).parent.glob('*.py'))}),'run_id':run_id,'drawing_hash':data.drawing.sha256,'l1_drawing_hash':load(directory,L1).drawing.sha256,'files':files,'sign_off_state':'待工程师签字','source_bytes':'公开包未附原图，未核验源文件字节','hash_boundary':'清单可检出文件变化；不等于数字签名、识别正确或第三方可信时间戳。'})
    return {'output':output.as_posix(),'decision_count':len(decisions),'run_id':run_id,'status':'exported'}

def verify_bundle(directory):
    directory=Path(directory);manifest=json.loads((directory/'bundle-manifest.json').read_bytes());failures=[]
    for name,expected in manifest['files'].items():
        path=directory/name
        if path.parent.resolve()!=directory.resolve():raise ValueError('证据包清单路径越界')
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:failures.append(name)
    if 'engineer-reviews.json' in manifest['files']:
        try:
            from .reviews import read_reviews
            read_reviews(directory/'engineer-reviews.json')
        except (ValueError,KeyError,TypeError,OSError):failures.append('engineer-reviews.json:context')
    claims_file=manifest.get('claims_check_file')
    if claims_file or (directory/'claims-check.json').is_file():
        if claims_file!='claims-check.json' or 'claims-check.json' not in manifest['files']:
            failures.append('claims-check.json:unlisted')
        try:
            from .claims import validate_report_context
            context=manifest.get('claims_context_changes_file')
            if context not in (None,'claims-context-changes.json'):raise ValueError('核验上下文路径无效')
            if context and context not in manifest['files']:raise ValueError('核验上下文未列入清单')
            delta=json.loads((directory/context).read_bytes()) if context else None
            validate_report_context(json.loads((directory/'claims-check.json').read_bytes()),directory,delta)
        except (OSError,ValueError,KeyError,TypeError):
            failures.append('claims-check.json:context')
    hashes={load(directory,m).drawing.sha256 for m in (L1,L2,L3)}
    if hashes!={manifest['drawing_hash']} or manifest['l1_drawing_hash']!=manifest['drawing_hash']:failures.append('drawing_hash')
    return {'status':'failed' if failures else 'verified','failure_count':len(failures),'failures':failures,'source_bytes':'公开包未附原图，跳过源字节核验','run_id':manifest['run_id']}

def rule_impact(code,bundle_directory,synthetic=False):
    rows=json.loads((Path(bundle_directory)/'decisions.json').read_bytes())['decisions']
    selected=[d for d in rows if any(c['code']==code for c in d['rule']['clauses'])]
    return {'origin':'SYNTHETIC' if synthetic else 'RULE_REFERENCE_QUERY','code':code,'scenario':'假设该规范已修订，仅展示哪些规则/决策需复核，不声明真实修订' if synthetic else '按规范引用查询，不判断规范是否已修订','rules':sorted({d['rule']['id'] for d in selected}),'decision_ids':[d['id'] for d in selected],'summary_cn':('SYNTHETIC：假设' if synthetic else '引用查询：')+code+('已修订，' if synthetic else '，')+f'涉及{len({d["rule"]["id"] for d in selected})}条规则、{len(selected)}条决策记录。请复核对应依据与原确认；此处不宣布真实规范修订或工程不合格。','affected_rules':[{'id':rid,'title':next(d['rule']['clauses'][0]['text'] for d in selected if d['rule']['id']==rid),'decision_count':sum(d['rule']['id']==rid for d in selected)} for rid in sorted({d['rule']['id'] for d in selected})]}
