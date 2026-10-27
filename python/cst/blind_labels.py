# SPDX-License-Identifier: MPL-2.0
"""冻结主张的盲标空表与计数对照；不生成或代填人工标签。"""
import csv,json
from collections import Counter
from pathlib import Path
from .claims import parse_document,check_claims
from .ai import ReadTools,validate
from .naming import digest
from .model import snapshot_session

HEADER=['主张编号','原文句子','标注〔支持/矛盾/不可判定〕','依据','标注人','用时（秒）']
def prepare(document,output):
    doc=parse_document(document);output=Path(output);output.mkdir(parents=True,exist_ok=True)
    with (output/'盲标表.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f);writer.writerow(HEADER)
        for claim in doc.claims:writer.writerow([claim.id,claim.text,'','','',''])
    (output/'冻结主张.json').write_text(json.dumps({'schema_version':'blind-label.v1','document_sha256':digest(doc.model_dump()),'document':doc.model_dump(),'contains_tool_results':False},ensure_ascii=False,indent=2),encoding='utf-8')
    return {'claim_count':len(doc.claims),'labels_filled':0,'contains_tool_results':False}

def summarize(directory,frozen,labels,output,changes=None,process_notes=None,status_basis='current'):
    frozen=json.loads(Path(frozen).read_bytes());doc=parse_document(frozen['document'])
    if frozen.get('document_sha256')!=digest(doc.model_dump()):raise ValueError('冻结主张校验失败')
    known={c.id:c for c in doc.claims};seen=set();human={};pending=[]
    with Path(labels).open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f)
        if reader.fieldnames!=HEADER:raise ValueError('盲标表列不匹配')
        for row in reader:
            key=row[HEADER[0]]
            if key not in known or key in seen or row[HEADER[1]]!=known[key].text:raise ValueError('盲标表主张缺失、重复或原文变化')
            seen.add(key);label=row[HEADER[2]].strip()
            if not label:pending.append(key);continue
            if label not in ('支持','矛盾','不可判定') or not row[HEADER[3]].strip() or not row[HEADER[4]].strip():raise ValueError('已标注行须填写有效标签、依据和标注人')
            try:seconds=float(row[HEADER[5]])
            except ValueError:raise ValueError('已标注行须填写用时')
            if not __import__('math').isfinite(seconds) or seconds<0:raise ValueError('用时须为有限非负数')
            human[key]={'label':label,'basis':row[HEADER[3]],'name':row[HEADER[4]],'seconds':seconds}
    if seen!=set(known):raise ValueError('盲标表主张不完整')
    with snapshot_session():
        tools=ReadTools(directory,changes);checked=check_claims(directory,doc,changes=changes,status_basis=status_basis);components=[]
        for claim,new in zip(doc.claims,checked['rows']):
            legacy={'claims':[{'text':claim.text,'object_ids':claim.refs,'values':claim.values}],'reason':None}
            old=validate(legacy,tools.truth(legacy))
            label=new['conclusion'] if new['conclusion'] in ('支持','矛盾') else '不可判定'
            components.append({'claim_id':claim.id,'legacy':old,'claims_check':new,'human':human.get(claim.id),'disagrees':human[claim.id]['label']!=label if claim.id in human else None})
    process={'status':'待人工回填抽取遗漏与修改记录','omitted_claims':None,'manual_edit_count':None}
    if process_notes is not None:
        notes=json.loads(Path(process_notes).read_bytes())
        if not isinstance(notes.get('reviewed_by'),str) or not notes['reviewed_by'].strip() or any(type(notes.get(k)) is not int or notes[k]<0 for k in ('omitted_claims','manual_edit_count')):raise ValueError('完整流程回填须有复核人及非负计数')
        process={**notes,'status':'人工回填，未替代独立盲标','source_sha256':digest(notes)}
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    result={'schema_version':'blind-comparison.v1','status_basis':status_basis,'document_sha256':frozen['document_sha256'],'claim_count':len(known),'human_count':len(human),'pending_count':len(pending),
        'components':components,'legacy_counts':dict(Counter('valid' if c['legacy']['valid'] else 'not_valid' for c in components)),
        'claims_check_counts':dict(Counter(c['claims_check']['conclusion'] for c in components)),
        'human_counts':dict(Counter(r['label'] for r in human.values())),
        'disagreement_count':sum(c['disagrees'] is True for c in components),
        'full_process':process,
        'boundary':'旧validate只有valid布尔，不将not_valid自动等同专业错误；零标签不表示零分歧，未完成盲标不计算准确率。'}
    (output/'组件对照.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 冻结主张计数对照',f'冻结主张：{len(known)}；人工已标：{len(human)}；未标：{len(pending)}。',
        '组件比较：旧validate '+json.dumps(result['legacy_counts'],ensure_ascii=False)+'；claims-check '+json.dumps(result['claims_check_counts'],ensure_ascii=False)+'。',
        f'已回填样本中的分歧：{result["disagreement_count"]}。未标注部分不计作一致或分歧。',
        '完整流程：'+json.dumps(process,ensure_ascii=False),result['boundary']]
    (output/'对照.md').write_text('\n\n'.join(lines),encoding='utf-8');return result
