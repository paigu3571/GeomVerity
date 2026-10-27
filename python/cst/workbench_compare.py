# SPDX-License-Identifier: MPL-2.0
"""工作台比较任务：复用CLI同一核心，不在页面重新判断影响或继承。"""
import json
import hashlib
import yaml
from pathlib import Path
from . import api
from .inventory import inspect_scan
from .model import snapshot_session


def known_public_lineage(directory):
    path=Path(directory)/'building-semantics.v1.json'
    if not path.is_file():path=path.with_name(path.name+'.gz')
    if not path.is_file():return None
    signature=hashlib.sha256(path.read_bytes()).hexdigest()
    registry=yaml.safe_load(Path(__file__).with_name('sample-lineage.yaml').read_text(encoding='utf-8'))
    return next((row for row in registry['samples'] if row['sha256']==signature),None)


def compare_versions(project, old_id, new_id, output, same_drawing=False, progress=None, review_records=None):
    with snapshot_session():
        return _compare_versions(project,old_id,new_id,output,same_drawing,progress,review_records)


def _compare_versions(project, old_id, new_id, output, same_drawing, progress, review_records):
    emit=progress or (lambda message:None)
    if same_drawing is not True:raise ValueError('请先确认这是同一图纸的两个版本；工具不自动证明同图关系')
    versions={v.id:v for v in project.versions}
    if old_id not in versions or new_id not in versions:raise ValueError('所选版本不在当前项目')
    old,new=versions[old_id],versions[new_id]
    if old_id==new_id or Path(old.scan_directory).resolve()==Path(new.scan_directory).resolve():
        raise ValueError('请选择不同扫描目录的旧版和新版')
    emit('核对所选图纸关系')
    known_old,known_new=known_public_lineage(old.scan_directory),known_public_lineage(new.scan_directory)
    if known_old and known_new and known_old['group']!=known_new['group']:
        raise ValueError('所选公开样例来自不同图纸：'+known_old['label']+'和'+known_new['label']+'；请用A与A-change体验换版，B是另一张图')
    health={}
    for label,version in [('旧版',old),('新版',new)]:
        emit('严格体检'+label+'扫描')
        health[label]=inspect_scan(version.scan_directory)
    for label,report in health.items():
        if not report['load_ok'] or report['tone']=='failed':
            raise ValueError(label+'不可比较：'+report['conclusion'])
    summary=api.diff(old.scan_directory,new.scan_directory,output,progress=emit,review_records=review_records)
    emit('整理比较列表')
    report=json.loads((Path(output)/'diff.json').read_bytes())
    display=display_report(report,old,new,health)
    return {'summary':summary,'report':report,'display':display,'path':str(Path(output)/'diff.json')}


def review_context(report):
    """展示已有决策对应的房名与规则；不重算继承结论或增加专业判断。"""
    def finding_index(side):
        return {f['decision']['id']:f for f in report.get(side+'_check',{}).get('findings',[]) if f.get('decision',{}).get('id')}
    old,new=finding_index('old'),finding_index('new')
    rows=[]
    for row in report.get('decision_inheritance',[]):
        before=old.get(row.get('old_decision_id'),{});after=new.get(row.get('new_decision_id'),{})
        def compact(f):
            return {k:f.get(k) for k in ('object_name','object_ids','rule_title','result','reason','scope','source_handles','clauses','values')}
        rows.append({'old_decision_id':row.get('old_decision_id'),'old':compact(before),'new':compact(after),
                     'engineer':before.get('decision',{}).get('engineer',{}),
                     'room_review':next((r for r in report.get('review_inheritance',[]) if r.get('old_room') in (before.get('object_ids') or [])),None) if row.get('rule_id')=='R1' else None})
    return rows


def display_report(report,old,new,health):
    display={key:report.get(key) for key in ('old_hash','new_hash','lineage_assumption','change_count','change_types','impact_counts','matched','unchanged','matching_warnings','mapping_approved','decision_inheritance','review_inheritance')}
    display['scan_health']={label:row['conclusion'] for label,row in health.items()}
    display['review_context']=review_context(report)
    display['old_version']={'id':old.id,'name':old.name}
    display['new_version']={'id':new.id,'name':new.name}
    display['changes']=[{key:row.get(key) for key in ('id','old','new','kinds','basis','impact','suggested_work','match_method')} |
                        {'can_locate':any(bool((row.get(side+'_geometry') or {}).get('bounds',{}).get('is_valid')) for side in ('old','new'))} for row in report['changes']]
    from .engineering import room_tasks
    display['engineering_rooms']=room_tasks(report)
    reference=json.loads((Path(__file__).with_name('assets')/'demo/manual-edit-reference.json').read_bytes())
    if (report['old_hash'],report['new_hash'])==(reference['old_hash'],reference['new_hash']):
        display['manual_edit_reference']=reference
    return display


def refresh_reviews(project,comparison,output,records):
    """输入指纹已在工作台核对；只复核规则，不重复匹配/影响/布灯。"""
    from copy import deepcopy
    from .changes import inherit_reviews,conclusion_changes,finalize_review_decisions
    from .l4 import read_r1_confirmations,check
    from .reviews import apply_reviews
    old=next(v for v in project.versions if v.id==comparison['display']['old_version']['id'])
    new=next(v for v in project.versions if v.id==comparison['display']['new_version']['id'])
    report=deepcopy(comparison['report'])
    apply_reviews(report['old_check']['findings'],report['old_hash'],records)
    confirmations,_=read_r1_confirmations(old.scan_directory,report['old_hash'])
    inherited,reviews=inherit_reviews(report['old_check']['findings'],report['new_check']['findings'],report['object_mapping'],set(),confirmations,records)
    report['new_check']=refresh_r1_conditions(report['new_check'],inherited)
    for f in report['new_check']['findings']:
        if f['object_ids'] and f['object_ids'][0] in inherited and f['rule_id']=='R1':
            f['engineer_reviewed']['record_file']='旧版/l4_confirmations.yaml'
            f['values']['confirmation_inherited']=True
            f['reason']='继承未变化对象的原人工核对；'+f['reason']
    apply_reviews(report['new_check']['findings'],report['new_hash'],records)
    report['review_inheritance']=reviews
    report['conclusion_changes']=conclusion_changes(report['old_check']['findings'],report['new_check']['findings'],report['object_mapping'])
    finalize_review_decisions(report)
    return store_review_report(project,comparison,report,output)


def store_review_report(project,comparison,report,output):
    """每次复核产生新派生报告；旧报告保留供冻结原文证据重放。"""
    import shutil
    from .changes import write_impact_report
    old=next(v for v in project.versions if v.id==comparison['display']['old_version']['id'])
    new=next(v for v in project.versions if v.id==comparison['display']['new_version']['id'])
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    for name in ('lighting_candidates.json','lighting_candidates.dxf'):
        src=Path(comparison['path']).parent/name
        if src.is_file():shutil.copy2(src,output/name)
    (output/'diff.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    write_impact_report(report,output/'impact_report.html')
    health={k:{'conclusion':v} for k,v in comparison['display']['scan_health'].items()}
    return {'summary':comparison['summary'],'report':report,'display':display_report(report,old,new,health),'path':str(output/'diff.json')}


def refresh_r1_conditions(check_report,inherited):
    """已通过工作台内容守卫时，只用原固定谓词重算新增的R1确认；几何/邻房证据复用。

    对比测试必须与完整check的逐字段输出一致。不会把意见文字解析成净长或出口。
    """
    from copy import deepcopy
    from collections import Counter
    from .rules import load_rule,evaluate
    from .l4 import enrich_finding
    from .priority import finding_rank
    from .naming import digest
    from .resources import rules_directory
    rule=load_rule(rules_directory()/'R1.yaml');result=deepcopy(check_report)
    for f in result['findings']:
        if f['rule_id']!='R1' or not f['object_ids'] or f['object_ids'][0] not in inherited:continue
        confirmed,review=inherited[f['object_ids'][0]]
        if confirmed.name!=f['object_name']:raise ValueError('人工条件对应房名不一致')
        if not rule.approved:raise ValueError('R1规则未批准，不能复用条件重算')
        m={'origin':review.origin,'reviewed_by':review.reviewed_by,'reviewed_date':review.reviewed_date,
            'net_length_gt_7':confirmed.net_length_gt_7,'entrance_count':confirmed.entrance_count,
            'snapshot_sha256':review.snapshot_sha256,'screenshot_sha256':review.screenshot_sha256,
            'note':'工程师确认净长阈值与总出入口数量；具体候选Handle映射仍为自动待复核'}
        item={'id':f['object_ids'][0],'use':rule.applies_to[0],'status':'accepted' if f['input_confidence']=='输入已确认' else 'review',
            'source_handles':f['source_handles'],'length_threshold_confirmation':{'threshold':7.0,'value':confirmed.net_length_gt_7},
            'opening_count':confirmed.entrance_count,'opening_complete':True}
        evaluated=evaluate(rule,item);f['result']=evaluated['result'];f['level']=evaluated['level']
        f['values'].update(evaluated['values']);f['values']['manual_confirmation']=m
        f['reason']=f"依据{m['reviewed_by']}人工核对：净长超过7米={m['net_length_gt_7']}，出入口{m['entrance_count']}处；"+evaluated['reason']+'；仅本条数量辅助初查，原识别与候选Handle仍待复核'
        f['engineer_reviewed']={'reviewed_by':m['reviewed_by'],'reviewed_date':m['reviewed_date'],'record_file':'旧版/l4_confirmations.yaml'}
        f.pop('manual_review',None);enrich_finding(f)
        priority={'rank':finding_rank(f),'title':f['rule_title'],'action':f.get('request_question') or '核对本项结果与输入条件','boundary':f['scope']}
        f['priority_rank']=priority['rank'];d=f['decision'];d['result']=f['result'];d['priority']=priority;d.pop('priority_evidence',None)
        d['engineer']={'confirmed_by':m['reviewed_by'],'date':m['reviewed_date'],'state':'输入条件已复核','scope':'本条输入条件，不是整间房设计签字','confirmation_record_sha256':digest(m)}
        d['sign_off_state']='条件已复核，结论待签字'
    result['summary']=dict(Counter(f['result'] for f in result['findings']))
    return result
