# SPDX-License-Identifier: MPL-2.0
"""把已有变化/检查按房间归并给工程师；不产生新的专业判定。"""
HELP={
 'R1':'核对实际出口数量；需要时量取室内净长。',
 'R2':'核对同层相邻房间的用途及共同隔墙。',
 'R3':'补充上一层平面图，核对本房间上方是否有用水场所。',
 'R4':'核对同层用水房间及隔墙防水做法。',
}

def room_tasks(report):
    mapping=report.get('object_mapping',{});groups={}
    def room(rid,name,old_only=False):
        key=mapping.get(rid,rid)
        if key not in groups:groups[key]={'room_id':key,'name':name or '未命名房间','old_only':old_only,'change_ids':[],'changes':[],'actions':[],'checks':[],'confirmation':None}
        return groups[key]
    for c in report.get('changes',[]):
        for ref in c.get('impact',{}).get('rooms',[]):
            g=room(ref['id'],ref.get('name'),ref.get('side')=='old' and ref['id'] not in mapping)
            if c['id'] in g['change_ids']:continue
            g['change_ids'].append(c['id'])
            obj=c['new'] or c['old'];noun={'opening':'门的位置','door':'门','wall':'墙','window':'窗','space':'房间范围或名称'}.get(obj['type'],'图中对象')
            kinds=['取消' if k=='删除' else '新增' if k=='新增' else '位置或形状调整' if k=='几何变化' else '名称或用途调整' if k=='名称或用途变化' else '内部编号更新' for k in c['kinds']]
            text=noun+'：'+'、'.join(kinds)
            if text not in g['changes']:g['changes'].append(text)
            for a in c.get('suggested_work',{}).get('items',[]):
                if a not in g['actions']:g['actions'].append(a)
    for c in report.get('changes',[]):
        obj=c.get('new') or c.get('old') or {}
        if obj.get('type')!='space':continue
        g=room(obj['id'],obj.get('name'),not c.get('new') and obj['id'] not in mapping)
        if c['id'] not in g['change_ids']:g['change_ids'].append(c['id'])
        description='房间范围、名称或用途变化：'+'、'.join(c['kinds'])
        if description not in g['changes']:g['changes'].append(description)
    for c in report.get('review_inheritance',[]):
        g=room(c.get('new_room') or c['old_room'],c.get('room_name'))
        g['confirmation']={k:c.get(k) for k in ('status','old_decision_id','new_room','old_room')}
    for f in report.get('new_check',{}).get('findings',[]):
        for rid in f['object_ids']:
            if rid not in groups:continue
            groups[rid]['checks'].append({'id':f['id'],'rule_id':f['rule_id'],'title':f.get('rule_title',f['rule_id']),'result':f['result'],'next_step':data_help(f),'manual_review':f.get('manual_review'),'values':{k:f.get('values',{}).get(k) for k in ('manual_confirmation','candidate_opening_count','confirmation_inherited')}})
    from .priority import room_priorities
    for g in groups.values():
        g['alerts']=room_priorities(g['room_id'],g['name'],[f for f in report.get('new_check',{}).get('findings',[]) if g['room_id'] in f['object_ids']],report if 'new_check' in report and 'old_check' in report else None)
        pending=g['confirmation'] and g['confirmation']['status'] in ('pending_identity','invalidated')
        r1=next((f for f in g['checks'] if f['rule_id']=='R1'),None)
        from .reviews import review_recorded
        g['confirmation_recorded']=bool(r1 and r1['manual_review'] and review_recorded(r1))
        g['requires_decision']=bool(pending and not g['confirmation_recorded'])
        g['waiting_data']=sum(f['result']=='无法判定' for f in g['checks'])
        g['recorded']=sum(review_recorded(f) for f in g['checks'])
        if not g['changes']:g['changes']=['房间和门的内容未变，内部编号更新。']
        if not g['actions']:g['actions']=['核对本房间原确认是否适用。'] if g['confirmation'] else ['查看本房间的检查资料和待办。'] if g['checks'] else ['本房间未纳入自动规则；看图核对照明、设备及管线是否需调整。']
        g['water_neighbors']=[]
        for f in report.get('new_check',{}).get('findings',[]):
            if f['rule_id']!='R4':continue
            for n in f['values'].get('adjacent_candidates',[]):
                if not n.get('water_candidate'):continue
                if g['room_id'] in f['object_ids']:g['water_neighbors'].append({'id':n['id'],'name':n['name']})
                elif g['room_id']==n['id']:g['water_neighbors'].append({'id':f['object_ids'][0],'name':f['object_name']})
    return sorted(groups.values(),key=lambda g:(not g['requires_decision'],min((a['rank'] for a in g['alerts']),default=99),-len(g['change_ids']),g['name'],g['room_id']))


def data_help(f):
    if f['result']!='无法判定':return f['reason']
    if f['rule_id']=='R1':return '需要：CAD实测室内净长、实际有效出口总数。由电气工程师看图量取并核实；可在意见中记录数值和改图要求。本版尚无数值补录重算入口，保存文字不会改变自动检查结果。'
    if f['rule_id']=='R3':return '需要：本房间对应的上一层平面、楼层对应位置及用水房间用途。请建筑专业提供；当前只有本层扫描，不能判断上方是否有用水场所。可先登记具体提资要求，本版尚不能导入上层平面重算。'
    if f['rule_id']=='R4':
        names='、'.join(sorted({n['name'] for n in f['values'].get('adjacent_candidates',[]) if n.get('water_candidate')}))
        return ('已发现贴邻用水候选：'+names+'。' if names else '尚未获得完整确认的同层用水邻房清单。')+'需要建筑确认是否有漏水/结露影响，以及共同隔墙防水做法。先看图核对隔墙，再登记待补资料或需要改图；本版不从一段意见自动认定防水合格。'
    return '需要核实同层相邻房间用途及隔墙构造；请建筑专业提供，并在本条意见中登记具体待办。当前扫描无法证明资料完整。'
