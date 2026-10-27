# SPDX-License-Identifier: MPL-2.0
"""有限、可审计的状态主张；冻结记录读取与当前策略重算分开。"""
import re
from .ai import affirmative
from .naming import digest
from .decisions import INHERITANCE_VERSION, inherit_decision

INHERITANCE_FIELDS={'inherited','inheritance_status','review_inheritance_status'}

def inheritance_records(delta, ref, room=False):
    if room:
        return [r for r in delta.get('review_inheritance',[]) if ref in (r.get('old_room'),r.get('new_room'))]
    findings=delta.get('old_check',{}).get('findings',[])+delta.get('new_check',{}).get('findings',[])
    decisions={f['decision']['id'] for f in findings if f.get('decision') and (ref==f['id'] or ref in f.get('object_ids',[]))}
    return [r for r in delta.get('decision_inheritance',[]) if ref in (r.get('old_decision_id'),r.get('new_decision_id')) or decisions.intersection((r.get('old_decision_id'),r.get('new_decision_id')))]

def recorded_status(record):
    if record.get('status'):return record['status']
    if record.get('inherited'):return 'inherited'
    text=record.get('state','')
    if '无人工确认' in text:return 'unconfirmed'
    if '失效' in text:return 'invalidated'
    return None

def state_checks(claim,resolved,tools,basis,check):
    checks,dependencies=[],[];delta=tools.changes_data or {};handled=False
    assertions=[]
    for key,value in claim.values.items():
        owner,_,field=key.rpartition('.')
        if field in INHERITANCE_FIELDS:assertions.append((owner,field,value))
    match=re.search(r'\binherited\s*:\s*(true|false)\b',claim.text,re.I)
    if not assertions:
        if match: assertions=[(ref,'inherited',match[1].lower()=='true') for ref in resolved]
        elif affirmative(claim.text,'仍有效|仍然有效|可继承|继承原范围确认'):
            assertions=[(ref,'inherited',True) for ref in resolved]
        elif claim.kind=='status' and affirmative(claim.text,'失效'):
            field='review_inheritance_status' if '房间输入复核继承' in claim.text else 'inheritance_status'
            assertions=[(ref,field,'invalidated') for ref in resolved]
        elif claim.kind=='status' and '不能视为新版已确认' in claim.text:
            assertions=[(ref,'inherited',False) for ref in resolved]
    seen=set()
    for ref,field,asserted in assertions:
        handled=True
        if ref not in resolved or not resolved[ref].found:
            checks.append(check('状态比对','未知','状态所属引用未声明或无法解析','无验证器',ref=ref));continue
        room=field=='review_inheritance_status' or (field=='inherited' and not ref.startswith(('decision_','finding_')))
        records=inheritance_records(delta,ref,room=room)
        if len(records)!=1:
            checks.append(check('状态比对','未知','缺少唯一的'+('房间输入复核' if room else '决策')+'继承记录','无验证器',ref=ref));continue
        record=records[0];identity=digest(record)
        if (identity,field,asserted) in seen:continue
        seen.add((identity,field,asserted));status=recorded_status(record);reason=record.get('reason') or record.get('state') or '读取冻结继承记录'
        outcome=None
        if basis=='current':
            if record.get('policy_version')!=INHERITANCE_VERSION:
                checks.append(check('状态比对','未知','旧继承记录需重新比较；仅历史资料忠实度核验可显式选择frozen_record','无验证器',ref=ref));continue
            if not room:
                def decision(side,key):
                    return next((f['decision'] for f in delta.get(side+'_check',{}).get('findings',[]) if f.get('decision',{}).get('id')==record.get(key)),None)
                old,new=decision('old','old_decision_id'),decision('new','new_decision_id')
                if not old or not new:
                    checks.append(check('状态比对','未知','缺少原始决策，无法重算继承','无验证器',ref=ref));continue
                mapping=delta.get('object_mapping')
                if mapping is None:
                    mapping={}
                    for prior in old['inputs']:
                        candidates=[i for i in new['inputs'] if i['object_id']==prior['object_id'] or i['content_fingerprint']==prior['content_fingerprint']]
                        if len(candidates)==1:mapping[prior['object_id']]=candidates[0]['object_id']
                outcome=inherit_decision(old,new,mapping,confirmation_available=record.get('confirmation_available',True),identity_confirmation=record.get('identity_confirmation'))
                if outcome['status']!=status or outcome['inherited']!=record['inherited']:
                    checks.append(check('状态比对','未知','继承记录与重算不一致','执行失败',ref=ref));continue
                reason=outcome['reason']
        observed=(record.get('inherited',status=='inherited' if status else None)) if field=='inherited' else status
        equal=type(asserted)==type(observed) and asserted==observed
        conclusion='支持' if equal else '需复核' if status=='pending_identity' else '矛盾'
        if observed is None:conclusion='未知'
        checks.append(check('冻结状态读取' if basis=='frozen_record' else '状态比对',conclusion,reason,
            ref=ref,field=field,asserted=asserted,observed=observed,basis=basis,
            scope='仅核对给定diff所载原确认范围，不是整间房或整图签字'))
        dependencies.append({'kind':'inheritance','id':ref,'fingerprint':digest({'record':record,'recomputed':outcome,'basis':basis})})
    for pattern,state in [('已确认|确认无误|确定合规','confirmed'),('已通过|判定通过|审查通过','passed')]:
        if not affirmative(claim.text,pattern):continue
        handled=True
        for ref,resolution in resolved.items():
            if not resolution.found:continue
            value=resolution.value or {}
            if state=='confirmed':
                engineer=value.get('engineer') or ((resolution.raw or {}).get('engineer_reviewed',{}) if isinstance(resolution.raw,dict) else {})
                confirmed=engineer.get('confirmed_by') or engineer.get('reviewed_by')
                if resolution.kind not in ('finding','decision'):
                    checks.append(check('状态比对','矛盾' if resolution.kind=='object' and value.get('status')!='accepted' else '未知','对象状态不等于工程师签字，需引用对应决策及确认范围','已执行' if resolution.kind=='object' and value.get('status')!='accepted' else '无验证器',ref=ref))
                else:
                    checks.append(check('状态比对','支持' if confirmed else '矛盾','仅核对记录的输入条件确认范围，不证明整项设计合规',ref=ref))
                if affirmative(claim.text,'确定合规'):checks.append(check('状态比对','未知','输入条件确认不等于设计合规','无验证器',ref=ref))
            elif 'result' not in value:checks.append(check('状态比对','未知','引用没有专业审查结论','无验证器',ref=ref))
            else:checks.append(check('状态比对','支持' if value['result']=='通过' else '矛盾','读取现有审查结论，不作新的专业签字',ref=ref))
    if claim.kind=='status' and not handled and not any(k.endswith(('.status','.result')) for k in claim.values):
        checks.append(check('状态比对','未知','尚不支持此状态措辞；请用引用.inherited或引用.inheritance_status','无验证器'))
    return checks,dependencies
