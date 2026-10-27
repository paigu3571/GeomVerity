# SPDX-License-Identifier: MPL-2.0
"""展示已有确认继承结果与已核验原句的差别；不修改核验器或专业结果。"""
import re
from .naming import digest

PHRASE='原确认因变化失效'


def review_target(report, room_id, *, old_decision_id=None, change_id=None):
    """只提供已有对象/检查的跳转引用，不用房名模糊匹配或补造复核项。"""
    room_id=report.get('object_mapping',{}).get(room_id,room_id)
    pair=next((r for r in report.get('decision_inheritance',[]) if old_decision_id and r.get('old_decision_id')==old_decision_id),{})
    findings=[f for f in report.get('new_check',{}).get('findings',[]) if room_id and room_id in f.get('object_ids',[])]
    finding=next((f for f in findings if pair.get('new_decision_id') and f.get('decision',{}).get('id')==pair['new_decision_id']),None)
    return {'room_id':room_id,'finding_id':finding.get('id') if finding else None,'old_decision_id':old_decision_id,'change_id':change_id}


def comparison_table(workspace, comparison):
    empty={'rows':[], 'checked_count':0, 'scope':'仅核对列出的房间变化字段及旧确认状态，不代表整篇意见或整图设计通过。'}
    if not workspace or workspace.get('context_stale') or not comparison:return empty
    checked=workspace.get('report') or {}; report=comparison.get('report') or {}
    if (checked.get('status_basis')!='current' or checked.get('drawing_hash')!=report.get('new_hash')
        or checked.get('changes_sha256')!=digest(report)):
        return dict(empty,message='意见依据尚未对应当前比较，请载入示例或重新核验。')
    from .workbench_compare import review_context
    contexts={c['old_decision_id']:c for c in review_context(report)}
    inheritance={r['room_name']:r for r in report.get('review_inheritance',[])}
    rows=[];seen=set()
    for row in checked.get('rows',[]):
        claim=row['claim'];text=claim['text']
        if row.get('validity')!='有效' or PHRASE not in text:continue
        for name,review in inheritance.items():
            mentioned=name in [cell.strip() for cell in text.split('|')] if text.lstrip().startswith('|') else name in text
            if name in seen or not mentioned:continue
            # 只摘原文房名及明确状态片段；不把句柄表或引用存在结论冒充整句正确。
            phrase=re.search(r'原确认因变化失效(?:[，,]需复核)?',text).group()
            if '|' in text:
                excerpt=name+'：'+phrase
            else:
                excerpt=re.sub(r'^\d+[.、]\s*','',text.replace('**','')).split('：',1)[-1]
            c=contexts.get(review.get('old_decision_id'),{});status=review.get('status')
            if status=='invalidated':
                old=c.get('old',{}).get('values',{}).get('manual_confirmation') or {}
                count=c.get('new',{}).get('values',{}).get('candidate_opening_count')
                fact=(f"旧版确认{old['entrance_count']}个出口，新版识别{count}处门洞候选；原确认失效，实际出口需看图核对。"
                      if isinstance(old.get('entrance_count'),int) and isinstance(count,int)
                      else '房间或门洞输入发生变化，原确认失效，需重新看图核对。')
                verdict='一致'
            elif status=='pending_identity':
                fact='房间和门的内容未变，只是内部编号变了，需工程师确认是否沿用原确认。';verdict='不一致'
            elif status=='inherited':
                fact='已有记录表明原确认按原范围沿用；不是原确认失效，也不是整间房设计通过。';verdict='不一致'
            else:
                fact='当前没有足够的原确认对应结果，不能判断这句失效说法。';verdict='查不了'
            rows.append({'ai_excerpt':excerpt,'drawing_fact':fact,'verdict':verdict,
                         'room_name':name,'claim_id':claim['id'],'original_text':text,'span':claim['span'],
                         'basis_status':status,'original_check':row.get('conclusion'),
                         'review_target':review_target(report,review.get('new_room') or review.get('old_room'),old_decision_id=review.get('old_decision_id'))})
            seen.add(name)
            if len(rows)==10:break
        if len(rows)==10:break
    # 原文的单项房间变化表可核对名称和变化类型；引用存在本身仍不算一致。
    changes={c['id']:c for c in report.get('changes',[])}
    for row in checked.get('rows',[]):
        if len(rows)>=10:break
        claim=row['claim'];text=claim['text']
        if row.get('validity')!='有效' or not text.lstrip().startswith('|'):continue
        ids=re.findall(r'change_\d+',text)
        if len(ids)!=1 or ids[0] not in changes:continue
        change=changes[ids[0]];old=change.get('old');new=change.get('new')
        if (new or old).get('type')!='space':continue
        cells=[cell.strip() for cell in text.strip().strip('|').split('|')]
        if len(cells)<4:continue
        def label(cell):
            pieces=[part.strip() for part in cell.split('/')]
            return pieces[1] if len(pieces)>=3 else None if cell=='无' else cell
        old_label,new_label=label(cells[2]),label(cells[3])
        expected=[k.strip() for k in cells[1].split('、') if k.strip()!='来源对象变化']
        if not expected:continue
        correct=(old_label==((old or {}).get('name')) and new_label==((new or {}).get('name'))
                 and set(expected)<=set(change['kinds']))
        name=(new or old).get('name') or '未命名房间'
        excerpt=(old_label or '无原房间')+' → '+(new_label or '新版未识别')+'：'+'、'.join(expected)
        if not old:fact='新版提取到“'+name+'”；旧版未匹配到房间，需看原图确认是否新建或识别变化。'
        elif not new:fact='新版未提取到“'+old['name']+'”的可用围合；不能直接认定房间已经拆除。'
        elif old['name']!=new['name']:fact='房间名称或用途由“'+old['name']+'”变为“'+new['name']+'”。请核对本房间及相邻专业影响。'
        else:fact='“'+name+'”的轮廓位置或形状有变化，需在图上核对边界及设备、照明影响。'
        rows.append({'ai_excerpt':excerpt,'drawing_fact':fact,'verdict':'一致' if correct else '不一致',
            'room_name':name,'claim_id':claim['id'],'original_text':text,'span':claim['span'],
            'basis_status':'room_change_fields','original_check':row.get('conclusion'),
            'review_target':review_target(report,(new or old).get('id'),change_id=change['id'])})
    return dict(empty,rows=rows,checked_count=len(checked.get('rows',[])))
