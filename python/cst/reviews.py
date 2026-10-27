# SPDX-License-Identifier: MPL-2.0
"""人工复核旁挂履历。姓名是本机自报，不是身份认证或数字签名。"""
from datetime import datetime,timezone
import json,os,tempfile
from pathlib import Path
from .naming import digest
from .decisions import INHERITANCE_VERSION

def transfer_context(old,new,mapping):
    return digest({'old_id':old['id'],'new_id':new['id'],'old_drawing':old.get('drawing_sha256'),'new_drawing':new.get('drawing_sha256'),
        'old_inputs':old['inputs'],'new_inputs':new['inputs'],'old_rule':old['rule'],'new_rule':new['rule'],
        'confirmation':old.get('engineer'),'scope':old.get('confirmation_scope'),
        'mapping':{i['object_id']:mapping.get(i['object_id']) for i in old['inputs']}})

def valid_transfer(record,old,new,mapping):
    return bool(record and record.get('action')=='confirm_identity_transfer' and record.get('policy_version')==INHERITANCE_VERSION
        and all(isinstance(record.get(k),str) and record[k].strip() for k in ('name','comment','scope','at'))
        and record.get('context_sha256')==transfer_context(old,new,mapping))

def finding_context(finding,drawing_hash):
    d=finding['decision']
    return digest({'drawing':drawing_hash,'finding':finding['id'],'result':finding['result'],'inputs':d['inputs'],'rule':d['rule']})

def read_reviews(path):
    path=Path(path)
    if not path.exists():return []
    value=json.loads(path.read_bytes())
    if value.get('schema_version')!='engineer-reviews.v1':raise ValueError('人工复核记录版本不兼容')
    validate_review_events(value['events'])
    return value['events']

def validate_review_events(events):
    previous=None
    for event in events:
        body={k:v for k,v in event.items() if k!='event_sha256'}
        if body.get('previous_sha256')!=previous or digest(body)!=event.get('event_sha256'):raise ValueError('人工复核履历校验失败')
        previous=event['event_sha256']
    return events

def append_review(path,record):
    path=Path(path);events=read_reviews(path);record=dict(record,previous_sha256=events[-1]['event_sha256'] if events else None)
    record['event_sha256']=digest(record);events.append(record);path.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix='.gv-review-',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as stream:json.dump({'schema_version':'engineer-reviews.v1','boundary':'本机自报记录，非身份认证或数字签名','events':events},stream,ensure_ascii=False,indent=2)
        os.replace(temp,path)
    finally:Path(temp).unlink(missing_ok=True)
    return events

def make_review(action,name,comment,scope,*,finding=None,drawing_hash=None,old=None,new=None,mapping=None,synthetic=False,disposition=None):
    if action not in ('confirm','reject','confirm_identity_transfer','reject_identity_transfer'):raise ValueError('不支持的人工复核动作')
    if not all(isinstance(x,str) and x.strip() for x in (name,comment,scope)):raise ValueError('请填写姓名、意见和适用范围')
    record={'action':action,'name':name.strip(),'comment':comment.strip(),'scope':scope.strip(),'at':datetime.now(timezone.utc).isoformat(),
        'policy_version':INHERITANCE_VERSION,'origin':'SYNTHETIC' if synthetic else 'ENGINEER_REVIEW'}
    if disposition is not None:
        if disposition not in ('recorded','needs_data','needs_change'):raise ValueError('复核处理分类无效')
        record['disposition']=disposition
    if action.endswith('identity_transfer'):
        from .decisions import inherit_decision
        if not old or not new or inherit_decision(old,new,mapping)['status']!='pending_identity':raise ValueError('只有内容未变但来源身份变化的原确认可办理来源对应复核')
        record.update(old_decision_id=old['id'],new_decision_id=new['id'],context_sha256=transfer_context(old,new,mapping))
    else:
        if not finding or not drawing_hash:raise ValueError('缺少当前规则结果及扫描上下文')
        record.update(finding_id=finding['id'],drawing_hash=drawing_hash,context_sha256=finding_context(finding,drawing_hash))
    return record

def review_recorded(finding):
    """办理状态：最新驳回重开事项，历史事件和专业结论仍保留。"""
    record=finding.get('manual_review')
    return record.get('action')!='reject' if record else bool(finding.get('values',{}).get('confirmation_inherited'))


def apply_reviews(findings,drawing_hash,records):
    for f in findings:
        context=finding_context(f,drawing_hash)
        candidates=[r for r in records if r.get('finding_id')==f['id'] and r.get('drawing_hash')==drawing_hash and r.get('context_sha256')==context]
        if not candidates:continue
        r=candidates[-1];f['manual_review']=r
        # 确认的是已有工具结果及所填范围；不把未知变通过，不填写净长/出口条件。
        f['decision']['engineer']={'confirmed_by':r['name'] if r['action']=='confirm' else None,'date':r['at'],'state':'工具结果已核对' if r['action']=='confirm' else '工具结果已驳回','scope':r['scope'],'comment':r['comment'],'origin':r['origin'],'review_event_sha256':r['event_sha256']}
        f['decision']['sign_off_state']='本条工具结果已核对，非整图设计签字' if r['action']=='confirm' else '本条工具结果被驳回'
    return findings


def copy_review_ledger(source,target):
    """另存项目时携带复核履历；目标已有不同履历时拒绝覆盖。"""
    source,target=Path(source),Path(target)
    if source.resolve()==target.resolve() or not source.exists():return
    events=read_reviews(source)
    if not events:return
    if target.exists():
        if read_reviews(target)!=events:raise ValueError('目标目录已有其他人工复核履历，请另选文件夹')
        return
    if not target.parent.is_dir():raise ValueError('保存目录不存在，请选择已有文件夹')
    payload=source.read_bytes();created=False
    try:
        with target.open('xb') as stream:
            created=True;stream.write(payload)
    except Exception:
        if created:target.unlink(missing_ok=True)
        raise
