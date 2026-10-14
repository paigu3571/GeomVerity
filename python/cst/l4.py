# SPDX-License-Identifier: MPL-2.0
"""Read existing three-layer evidence; no CAD recognition or fabricated relationships."""
from collections import Counter
from pathlib import Path
import math
import hashlib
import yaml
from pydantic import Field
from .model import Model
from .model import load,L1,L2
from .uses import classify
from .rules import load_rules,evaluate

from .resources import rules_directory
RULES=rules_directory()

def envelope_dimensions(geometry):
    if not geometry.is_closed or len(geometry.paths)!=1:return None
    points=sorted(set((p.x,p.y) for p in geometry.paths[0]))
    if len(points)<3:return None
    ox,oy=points[0];points=[(x-ox,y-oy) for x,y in points]
    def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    lower=[];upper=[]
    for target,seq in ((lower,points),(upper,reversed(points))):
        for p in seq:
            while len(target)>1 and cross(target[-2],target[-1],p)<=0:target.pop()
            target.append(p)
    hull=lower[:-1]+upper[:-1]
    candidates=[]
    for a,b in zip(hull,hull[1:]+hull[:1]):
        dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
        if not length:continue
        ux,uy=dx/length,dy/length
        xs=[x*ux+y*uy for x,y in hull];ys=[-x*uy+y*ux for x,y in hull]
        w,h=max(xs)-min(xs),max(ys)-min(ys)
        candidates.append((w*h,max(w,h),min(w,h)))
    if not candidates:return None
    _,long,short=min(candidates)
    return {"long_side_m":round(long/1000,6),"short_side_m":round(short/1000,6),
            "method":"二维凸包最小外包矩形；不是室内净长"}

def shared_boundary_mm(a,b,tolerance=5.0):
    """Collinear boundary overlap candidate; point contact/gaps aren't proof of adjacency."""
    if not a.is_closed or not b.is_closed:return 0.0
    best=0.0
    for pa in a.paths:
        for p,q in zip(pa,pa[1:]+pa[:1]):
            dx,dy=q.x-p.x,q.y-p.y;length=math.hypot(dx,dy)
            if not length:continue
            ux,uy=dx/length,dy/length
            for pb in b.paths:
                for c,d in zip(pb,pb[1:]+pb[:1]):
                    if max(abs((v.x-p.x)*uy-(v.y-p.y)*ux) for v in (c,d))>tolerance:continue
                    projections=sorted((v.x-p.x)*ux+(v.y-p.y)*uy for v in (c,d))
                    best=max(best,min(length,projections[1])-max(0.0,projections[0]))
    return round(max(best,0.0),6)

def evidence_chain(obj,facts,primitives):
    chains=[]
    for e in obj.evidence:
        if e.kind!='geometry_fact':continue
        fact=facts.get(e.value)
        records=[]
        for pid in fact.source_primitive_ids if fact else []:
            p=primitives.get(pid)
            records.append({"l1_id":pid,"handle":p.source.handle if p else None,
                            "stable_path":p.source.stable_path if p else None})
        chains.append({"l3_id":obj.semantic_id,"l2_id":e.value,"l1_sources":records,
                       "complete":bool(fact and records) and all(p['handle'] for p in records)})
    return {"object_id":obj.semantic_id,"source_handle":obj.source.handle,"chains":chains,
            "text_sources":[{'handle':e.source_handle,'text':e.value} for e in obj.evidence if e.kind=='spatial_text']}


class RoomConfirmation(Model):
    object_id: str
    name: str
    net_length_gt_7: bool
    entrance_count: int = Field(ge=0)

class R1Confirmations(Model):
    schema_version: str
    drawing_sha256: str
    snapshot_sha256: str
    reviewed_by: str
    reviewed_date: str
    origin: str
    screenshot_sha256: list[str]
    rooms: list[RoomConfirmation]

def read_r1_confirmations(directory,drawing_hash):
    path=Path(directory)/'l4_confirmations.yaml'
    if not path.is_file():return {},None
    review=R1Confirmations.model_validate(yaml.safe_load(path.read_text(encoding='utf-8')))
    if review.schema_version!='r1-confirmations.v1' or review.origin!='ENGINEER_REVIEW' or not review.reviewed_by:
        raise ValueError('人工核对记录缺少正确版本/来源/复核人')
    source=Path(directory)/'building-semantics.v1.json'
    if not source.is_file():source=source.with_name(source.name+'.gz')
    if review.drawing_sha256!=drawing_hash or review.snapshot_sha256!=hashlib.sha256(source.read_bytes()).hexdigest():
        return {},'人工核对对应其他图纸或扫描，本次未套用；扫描及候选计算可继续'
    if len({r.object_id for r in review.rooms})!=len(review.rooms):raise ValueError('人工核对有重复对象')
    return {r.object_id:(r,review) for r in review.rooms},None

def opening_candidates(room,linked,tolerance=5.0):
    """L4 audit only: preserve original references, collapse coincident aliases and filter far candidates."""
    groups={}
    for o in linked:
        key=(o.source.drawing_hash,o.source.handle,tuple(o.source.xref_hashes),
             tuple(tuple((round(p.x,3),round(p.y,3),round(p.z,3)) for p in path) for path in o.geometry.paths))
        groups.setdefault(key,[]).append(o)
    audit=[];kept=[]
    def distance(p,a,b):
        dx,dy=b.x-a.x,b.y-a.y;length2=dx*dx+dy*dy
        t=max(0,min(1,((p.x-a.x)*dx+(p.y-a.y)*dy)/length2)) if length2 else 0
        return math.hypot(p.x-a.x-t*dx,p.y-a.y-t*dy)
    for group in groups.values():
        o=group[0]
        distances=[distance(p,a,b) for path in o.geometry.paths for p in path
                   for boundary in room.geometry.paths for a,b in zip(boundary,boundary[1:]+boundary[:1])] if room.geometry.is_closed else []
        closest=min(distances) if distances else None
        include=closest is not None and closest<=tolerance
        if include:kept.append(o)
        audit.append({'handle':o.source.handle,'object_ids':[x.semantic_id for x in group],
                      'stable_paths':[x.source.stable_path for x in group],
                      'boundary_distance_mm':round(closest,6) if closest is not None else None,
                      'included':include,'reason':'近边门洞候选，仍需确认出入口性质' if include else '距房间实际轮廓超过容差或缺闭合轮廓'})
    return {'raw_opening_relation_count':len(linked),'coincident_opening_count':len(groups),
            'candidate_opening_count':len(kept),'candidate_opening_ids':[o.semantic_id for o in kept],
            'candidate_opening_handles':sorted({o.source.handle for o in kept}),
            'opening_candidate_audit':audit,'opening_boundary_tolerance_mm':tolerance,
            'opening_method':'L4同源同位置几何重合去重；路径点距闭合房间轮廓不超过5mm的候选；不证明有效出入口'}

def risk_use(row):
    if row.get('category')=='EXCLUDED':return None
    if row.get('category') in ('HOT_FLUE','HEAT_ROOM'):return row['category']
    if row.get('l3_use_code') in ('HOT_FLUE','HEAT_ROOM'):return row['l3_use_code']
    if row.get('water_needs_confirmation'):return None
    name=row.get('name','')
    if any(word in name for word in ('厕所','卫生间')):return 'TOILET'
    if '浴室' in name:return 'BATHROOM'
    if '厨房' in name:return 'KITCHEN'
    return None

def coedges(directory):
    data=load(directory);rows={r['object_id']:r for r in classify(directory)['rows']}
    targets=[o for o in data.objects if rows.get(o.semantic_id,{}).get('category') in ('SUBSTATION','DISTRIBUTION_ROOM','ELECTRICAL_SHAFT')]
    candidates=[]
    for obj in targets:
        for other in data.objects:
            row=rows.get(other.semantic_id,{})
            if other.semantic_id==obj.semantic_id or row.get('category')=='EXCLUDED':continue
            if not (row.get('water_candidate') or risk_use(row) in ('HOT_FLUE','HEAT_ROOM')):continue
            overlap=shared_boundary_mm(obj.geometry,other.geometry) if data.drawing.geometry_units=='mm' else 0
            if overlap>5:
                candidates.append({'room_name':obj.raw_label,'room_id':obj.semantic_id,'room_handle':obj.source.handle,
                    'other_name':other.raw_label,'other_id':other.semantic_id,'other_handle':other.source.handle,
                    'risk_use':risk_use(row),'water_needs_confirmation':row.get('water_needs_confirmation',False),
                    'shared_boundary_mm':overlap,'candidate_source':'geometry_coedge_5mm','status':'输入待复核'})
    return {'origin':'REAL','target_count':len(targets),'candidate_count':len(candidates),'candidates':candidates,
            'note':'原轮廓共边候选；无命中不证明没有贴邻；泵房/水箱/水池只列人工风险候选'}

def enrich_finding(f):
    f['engineer_reviewed']=f.get('engineer_reviewed') or {'reviewed_by':None,'reviewed_date':None,'record_file':None}
    if f['result']=='无法判定':
        name=f.get('object_name','未识别到的适用房间');handles=', '.join(f.get('source_handles',[])) or '尚无对应Handle'
        f['request_question']=f'请建筑专业补充或核对“{name}”（Handle：{handles}）的资料：{f["reason"]}。'
    else:f['request_question']=None
    for sub in f.get('subchecks',[]):
        if sub['result']=='无法判定':
            sub['request_question']=f'请建筑专业提供“{f.get("object_name","适用房间")}”（Handle：{", ".join(f.get("source_handles",[])) or "尚无对应Handle"}）的资料：{sub["reason"]}。'
    return f

def check(directory,rules_dir=RULES, inherited_confirmations=None):
    l3=load(directory);l2=load(directory,L2);l1=load(directory,L1)
    objs={o.semantic_id:o for o in l3.objects};facts={f.geometry_id:f for f in l2.facts};primitives={p.primitive_id:p for p in l1.primitives}
    classes=classify(directory);uses={r['object_id']:r for r in classes['rows']}
    rules=load_rules(rules_dir)
    confirmations,confirmation_warning=read_r1_confirmations(directory,l3.drawing.sha256)
    if inherited_confirmations:
        confirmations.update(inherited_confirmations)
    from .adjacency import adjacency
    partition=adjacency(l3,uses)
    adjacent_by_room={}
    for row in partition['candidates']:
        adjacent_by_room.setdefault(row['room_id'],[]).append(row)
    findings=[]
    for rule in rules:
        targets=[o for o in l3.objects if uses.get(o.semantic_id,{}).get('category') in rule.applies_to]
        if not targets:
            findings.append({'id':'finding_'+rule.id+'_no_target','rule_id':rule.id,'rule_title':rule.title,'object_ids':[],
                'result':'无法判定','reason':'未识别到纳入本条的对象；不能据此说明图中没有','input_confidence':'输入待复核',
                'level':'提示' if rule.id=='R4' else '辅助审查','source_handles':[],'values':{},'evidence':[],
                'clauses':[c.model_dump() for c in rule.clauses],'origin':'REAL','scope':rule.scope,'rule_approved':rule.approved})
        for obj in sorted(targets,key=lambda o:o.semantic_id):
            item={'id':obj.semantic_id,'name':obj.raw_label,'use':uses[obj.semantic_id]['category'],'status':obj.status,
                  'source_handles':[obj.source.handle], 'origin':'REAL','input_statuses':[]}
            evidence_objects=[obj];values={};missing=[]
            if uses[obj.semantic_id].get('naming_provenance'):values['naming_provenance']=uses[obj.semantic_id]['naming_provenance']
            if l3.status=='failed':missing.append('源语义扫描失败')
            if l3.drawing.geometry_units!='mm':missing.append('图纸单位不是已支持的毫米')
            if rule.id=='R1':
                dimensions=envelope_dimensions(obj.geometry) if l3.drawing.geometry_units=='mm' else None
                if dimensions:values['candidate_dimensions']=dimensions
                linked=[]
                for rel in l3.relations:
                    if rel.type!='connects':continue
                    if obj.semantic_id==rel.from_semantic_id:other=objs.get(rel.to_semantic_id)
                    elif obj.semantic_id==rel.to_semantic_id:other=objs.get(rel.from_semantic_id)
                    else:continue
                    if other and other.type=='opening':linked.append(other);item['input_statuses'].append(rel.status)
                values.update(opening_candidates(obj,linked))
                evidence_objects+=list({o.semantic_id:o for o in linked}.values())
                confirmation=confirmations.get(obj.semantic_id)
                if confirmation and confirmation[0].name==obj.raw_label:
                    confirmed,review=confirmation
                    item.update(length_threshold_confirmation={'threshold':7.0,'value':confirmed.net_length_gt_7},
                                opening_count=confirmed.entrance_count,opening_complete=True)
                    values['manual_confirmation']={'origin':review.origin,'reviewed_by':review.reviewed_by,
                        'reviewed_date':review.reviewed_date,'net_length_gt_7':confirmed.net_length_gt_7,
                        'entrance_count':confirmed.entrance_count,'snapshot_sha256':review.snapshot_sha256,
                        'screenshot_sha256':review.screenshot_sha256,
                        'note':'工程师确认净长阈值与总出入口数量；具体候选Handle映射仍为自动待复核'}
                else:
                    missing+=['缺少已确认室内净长','门洞候选尚未确认是有效出入口']
                    if confirmation_warning:missing.append(confirmation_warning)
            elif rule.id in ('R2','R4'):
                neighbours=[]
                for relation in adjacent_by_room.get(obj.semantic_id,[]):
                    other=objs[relation['other_id']];use=uses.get(other.semantic_id,{})
                    neighbours.append({**relation,'id':other.semantic_id,'name':other.raw_label,
                        'use':use.get('category'),'risk_use':risk_use(use),
                        'water_candidate':use.get('water_candidate',False),
                        'water_needs_confirmation':use.get('water_needs_confirmation',False),'handle':other.source.handle})
                    evidence_objects.extend([other,objs[relation['wall_id']]])
                    item['input_statuses'].extend([other.status,objs[relation['wall_id']].status])
                values['adjacent_candidates']=neighbours
                item['adjacent_uses']=[n['risk_use'] for n in neighbours if n['risk_use']]
                item['adjacent_uses_complete']=False
                values['candidate_source']='geometry_partition_wall'
                values['adjacency_config']=partition['config']
                values['adjacency_method']='两空间平行边界重叠及同一L3墙的两面厚度证据；候选待复核'
                missing+=['缺少完整且确认的贴邻关系','热源用途/隔热措施待核' if rule.id=='R2' else '用水候选不等于漏水风险已确认']
            elif rule.id=='R3':missing+=['缺少上一层语义']
            else:missing.append('新增规则缺少已确认的专业关系数据')
            if not rule.approved:missing.append('规则实施口径未批准')
            out={'rule_id':rule.id,'object_ids':[obj.semantic_id],'result':'无法判定','reason':'；'.join(missing),
                 'input_confidence':'输入待复核','level':'提示' if rule.id=='R4' else '辅助审查',
                 'source_handles':sorted({o.source.handle for o in evidence_objects}), 'values':values,
                 'clauses':[c.model_dump() for c in rule.clauses],'scope':rule.scope,'origin':'REAL'}
            if rule.approved and l3.status!='failed' and l3.drawing.geometry_units=='mm':
                evaluated=evaluate(rule,item)
                evaluated['values'].update(values)
                evaluated['reason']='；'.join(dict.fromkeys([evaluated['reason']]+missing))
                if values.get('manual_confirmation'):
                    m=values['manual_confirmation']
                    evaluated['reason']=f"依据{m['reviewed_by']}人工核对：净长超过7米={m['net_length_gt_7']}，出入口{m['entrance_count']}处；"+evaluated['reason']+'；仅本条数量辅助初查，原识别与候选Handle仍待复核'
                out=evaluated
            if values.get('manual_confirmation'):
                m=values['manual_confirmation']
                out['engineer_reviewed']={'reviewed_by':m['reviewed_by'],'reviewed_date':m['reviewed_date'],
                    'record_file':(Path(directory)/'l4_confirmations.yaml').as_posix()}
            if rule.id in ('R2','R4') and out['result']=='不通过':
                out['reason']='隔墙贴邻候选发现风险，需工程师复核；'+out['reason']
            out.update(id='finding_'+rule.id+'_'+obj.semantic_id,object_name=obj.raw_label,rule_approved=rule.approved,rule_title=rule.title,
                       source_handles=sorted({o.source.handle for o in evidence_objects}),
                       evidence=[evidence_chain(o,facts,primitives) for o in evidence_objects])
            if rule.id=='R4':out['subchecks']=[{'id':'waterproof','result':'无法判定','strength':'应','reason':'缺少隔墙防水资料；仅在贴邻适用条件成立后检查'}]
            findings.append(out)
    findings=[enrich_finding(f) for f in findings]
    from .decisions import finding_decisions
    finding_decisions(l3,findings,rules_dir)
    return {'status':'partial','origin':'REAL','drawing_hash':l3.drawing.sha256,'producer_version':l3.producer_version,
            'summary':dict(Counter(f['result'] for f in findings)),'rules':[{'id':r.id,'approved':r.approved} for r in rules],
            'findings':[enrich_finding(f) for f in findings],'note':'真实数据辅助审查；缺少确认资料不输出合规结论，候选数值供工程师定位复核'}
