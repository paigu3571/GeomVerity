# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 张田
"""工程风险优先级由后端生成，界面与AI消费同一结果。"""
def finding_rank(f):
    if f['result']=='不通过':return 0
    if f['rule_id']=='R4' and any(n.get('water_candidate') for n in f['values'].get('adjacent_candidates',[])):return 1
    if f['result']=='无法判定':return 2
    return 3

def room_priorities(object_id,name,findings,delta=None,old_id=None):
    if delta and old_id is None:
        paired=next((c for c in delta['changes'] if (c.get('new') or {}).get('id')==object_id),None)
        old_id=(paired.get('old') or {}).get('id') if paired else None
    inputs=delta['new_check']['findings'] if delta else findings
    alerts=[]
    after=next((f for f in inputs if f['rule_id']=='R1' and object_id in f['object_ids']),None)
    before=next((f for f in delta['old_check']['findings'] if f['rule_id']=='R1' and old_id in f['object_ids']),None) if delta and old_id else None
    previous=(before or {}).get('values',{}).get('manual_confirmation',{}).get('entrance_count')
    count=(after or {}).get('values',{}).get('candidate_opening_count')
    if previous is not None and count is not None and count<previous:
        alerts.append({'rank':0,'title':'出口可能减少，请优先核对规范要求','text':f'旧版已确认出口 {previous} 处 → 新版门洞候选 {count} 处。','action':'先核对新版实际出口数和室内净长；若净长仍超过7米且实际出口不足两处，可能不满足本次出口数量规则。','boundary':'门洞候选尚未逐个确认，目前是风险提示。','finding_ids':[before['id'],after['id']]})
    for f in inputs:
        if f['rule_id']!='R4':continue
        neighbors=[n for n in f['values'].get('adjacent_candidates',[]) if n.get('water_candidate')]
        if not neighbors:continue
        if object_id not in f['object_ids'] and not any(n.get('id')==object_id for n in neighbors):continue
        labels=sorted({n['name'] for n in neighbors})
        alerts.append({'rank':1,'title':'贴邻用水候选房间，请优先核对防水措施','text':f'{f.get("object_name",name)}与'+ '、'.join(labels)+'存在隔墙相邻候选。','action':'核对漏水影响及相邻隔墙的防水、无渗漏和防结露措施；缺少做法时向建筑专业提资。','boundary':'用水候选尚未直接认定违规，措施由工程师确认。','finding_ids':[f['id']]})
    for f in findings:
        if f['result']=='不通过' and not any(f['id'] in a['finding_ids'] for a in alerts):
            alerts.append({'rank':2,'title':'规则发现需优先处理的问题','text':f['reason'],'action':'核对涉及对象和条文，再确认处理措施。','boundary':'见该项输入状态与复核记录。','finding_ids':[f['id']]})
    return sorted(alerts,key=lambda a:a['rank'])
