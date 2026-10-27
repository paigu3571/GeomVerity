# SPDX-License-Identifier: MPL-2.0
"""同图两版语义差异及有界影响分析；不修改图纸或识别结果。"""
from collections import Counter,defaultdict
import json
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
import time
from datetime import datetime,timezone,timedelta
import yaml
from shapely.geometry import Polygon,LineString,Point,GeometryCollection,box
from shapely.ops import unary_union
from .model import load,L2,snapshot_session
from .uses import classify
from .l4 import check,read_r1_confirmations,RULES

ELECTRICAL={'SUBSTATION','DISTRIBUTION_ROOM','ELECTRICAL_SHAFT','WEAK_CURRENT_ROOM','SMALL_ELECTRICAL_ROOM'}

_geometry_cache = ContextVar('comparison_geometry_cache', default=None)


@contextmanager
def geometry_session():
    token=_geometry_cache.set({})
    try:yield
    finally:_geometry_cache.reset(token)


def shape(obj):
    cache=_geometry_cache.get()
    if cache is None:return _shape(obj)
    key=id(obj)
    if key not in cache:cache[key]=(obj,_shape(obj))
    return cache[key][1]


def _shape(obj):
    parts=[]
    for path in obj.geometry.paths:
        xy=[(p.x,p.y) for p in path]
        if not xy:continue
        if obj.geometry.is_closed and len(set(xy))>=3:
            polygon=Polygon(xy)
            if not polygon.is_valid:return None
            parts.append(polygon)
        elif len(set(xy))>=2:parts.append(LineString(xy))
        else:parts.append(Point(xy[0]))
    return unary_union(parts) if parts else None

def match_shape(o):
    """匹配只比较路径；无效闭合CAD轮廓不升格为有效面积多边形。"""
    g=shape(o)
    if g is not None:return g
    parts=[]
    for path in o.geometry.paths:
        xy=[(p.x,p.y) for p in path]
        if len(xy)>=2:parts.append(LineString(xy))
        elif xy:parts.append(Point(xy[0]))
    return GeometryCollection(parts) if parts else None


def source_key(o):
    # 块名可能重命名，实例Handle与外参路径区分同Handle的不同实例。
    return (o.type,o.source.handle.upper(),tuple(p.split(':')[0].upper() for p in o.source.block_path),tuple(o.source.xref_path))

def raw_paths(obj):
    cache=_geometry_cache.get();key=('raw_paths',id(obj))
    if cache is not None and key in cache:return cache[key][1]
    shapes=[];zs=[];all_z=[]
    for path in obj.geometry.paths:
        xy=[(p.x,p.y) for p in path];z=[p.z for p in path]
        shapes.append(LineString(xy) if len(xy)>=2 else Point(xy[0]) if xy else GeometryCollection())
        zs.append(z);all_z.extend(z)
    result=(shapes,zs,(min(all_z),max(all_z)) if all_z else None)
    if cache is not None:cache[key]=(obj,result)
    return result


def same_geometry(a,b):
    if a.geometry.kind!=b.geometry.kind or a.geometry.is_closed!=b.geometry.is_closed:return False
    if a.geometry.is_exact!=b.geometry.is_exact:return False
    ap,az,ar=raw_paths(a);bp,bz,br=raw_paths(b)
    # 只有所有可能配对都在原有Z容差内时省去逐点循环；否则沿用逐点判断。
    z_safe=ar is None or br is None or max(abs(ar[0]-br[1]),abs(ar[1]-br[0]))<=0.001
    if not z_safe and any(abs(p-q)>0.001 for pa,pb in zip(az,bz) for p,q in zip(pa,pb)):return False
    remaining=list(bp)
    raw_equal=len(ap)==len(remaining)
    if raw_equal:
        for g in ap:
            match=next((i for i,h in enumerate(remaining) if g.equals(h) or g.equals_exact(h,0.001,normalize=True)),None)
            if match is None:raw_equal=False;break
            remaining.pop(match)
        if raw_equal:return True
    ga,gb=shape(a),shape(b)
    if ga is not None and gb is not None:
        return ga.equals(gb) or ga.equals_exact(gb,0.001,normalize=True) or ga.simplify(0.001).equals_exact(gb.simplify(0.001),0.001,normalize=True)
    return a.geometry.model_dump()==b.geometry.model_dump()


def ref(o):
    if o is None:return None
    return {'id':o.semantic_id,'handle':o.source.handle,'name':o.raw_label,'type':o.type,'use':o.use_code,
            'block_instance_handles':[p.split(':')[0] for p in o.source.block_path]}

def compare_objects(old,new):
    pairs=[];used_old=set();used_new=set();warnings=[]
    groups=[]
    for data in (old,new):
        d=defaultdict(list)
        for o in data.objects:d[source_key(o)].append(o)
        groups.append(d)
    def pair(a,b,method):
        pairs.append((a,b,method));used_old.add(a.semantic_id);used_new.add(b.semantic_id)
    # 房名文字证据优先于派生围合锚点；仅对唯一文字来源对应，重名不强配。
    label_indexes=[]
    for dataset in (old,new):
        index=defaultdict(list)
        for o in dataset.objects:
            labels=tuple(sorted({e.source_handle.upper() for e in getattr(o,'evidence',[]) if e.code=='ROOM_LABEL_CONTAINED_TEXT'}))
            if o.type in ('space','shaft') and labels:index[(o.type,labels,tuple(o.source.block_path),tuple(o.source.xref_path))].append(o)
        label_indexes.append(index)
    for key in label_indexes[0].keys() & label_indexes[1].keys():
        aa,bb=label_indexes[0][key],label_indexes[1][key]
        if len(aa)==len(bb)==1:pair(aa[0],bb[0],'unique_room_label_evidence_handle')
    # 天正分解对象Handle在不同扫描中可能重编号。唯一几何先锚定，
    # 不把旧Handle恰好被另一个分解对象复用当成同一工程对象。
    from shapely import set_precision
    geometric=[]
    for dataset in (old,new):
        index=defaultdict(list)
        for o in dataset.objects:
            g=match_shape(o)
            if g is not None and not g.is_empty:
                key=(o.type,set_precision(g,0.001).normalize().wkb)
                index[key].append(o)
        geometric.append(index)
    for key in geometric[0].keys() & geometric[1].keys():
        aa=[o for o in geometric[0][key] if o.semantic_id not in used_old];bb=[o for o in geometric[1][key] if o.semantic_id not in used_new]
        if len(aa)==len(bb)==1:pair(aa[0],bb[0],'unique_type+exact_wcs_geometry_0.001mm')
        elif key[0] not in ('space','shaft'):
            # 同位置重复表达只比较几何数量，不声称跨版实例身份确定。
            def order(o):return (o.raw_label,tuple(o.source.block_path),o.source.handle,o.semantic_id)
            for a,b in zip(sorted(aa,key=order),sorted(bb,key=order)):
                if a.raw_label==b.raw_label:pair(a,b,'geometry_multiset_equivalent_identity_unverified')
            warnings.append({'kind':'重复几何按数量对应，实例身份未确认','type':key[0],'old_count':len(aa),'new_count':len(bb)})
    # 坐标在量化格线两侧会产生不同WKB，补作既有0.001mm容差比较。
    # 不增加识别容差；用空间索引查近邻，并按实例路径去掉重复表达噪声。
    from shapely.strtree import STRtree
    candidates_new=[o for o in new.objects if o.semantic_id not in used_new and match_shape(o) is not None]
    candidate_shapes=[match_shape(o) for o in candidates_new];tree=STRtree(candidate_shapes)
    for a in old.objects:
        if a.semantic_id in used_old:continue
        ga=match_shape(a)
        if ga is None:continue
        x0,y0,x1,y1=ga.bounds
        near=[candidates_new[int(i)] for i in tree.query(box(x0-.001,y0-.001,x1+.001,y1+.001))]
        near=[b for b in near if b.semantic_id not in used_new and a.type==b.type and same_geometry(a,b)]
        context=[b for b in near if source_key(a)[2:]==source_key(b)[2:]]
        if len(context)==1:pair(a,context[0],'wcs_geometry_tolerance_0.001mm+instance_context')
        elif len(near)==1:pair(a,near[0],'unique_wcs_geometry_tolerance_0.001mm')
        elif near and a.type not in ('space','shaft'):pair(a,sorted(near,key=lambda o:(source_key(o),o.semantic_id))[0],'tolerance_geometry_multiset_identity_unverified')
    for key in sorted(groups[0].keys() & groups[1].keys()):
        aa=[o for o in groups[0][key] if o.semantic_id not in used_old];bb=[o for o in groups[1][key] if o.semantic_id not in used_new]
        if len(aa)==len(bb)==1:pair(aa[0],bb[0],'source_handle+block_instances+xref_path')
        else:
            for a in aa:
                exact=[b for b in bb if b.semantic_id==a.semantic_id and same_geometry(a,b)]
                if len(exact)==1:pair(a,exact[0],'source_handle+same_semantic_snapshot')
            for a in aa:
                if a.semantic_id in used_old:continue
                equal=[b for b in bb if b.semantic_id not in used_new and a.raw_label==b.raw_label and same_geometry(a,b)]
                if len(equal)==1:pair(a,equal[0],'source_handle+unique_geometry')
            if any(a.semantic_id not in used_old for a in aa):warnings.append({'kind':'同源多候选未强行匹配','handle':key[1],'type':key[0]})
    # 无Handle匹配的房间用名称+真实轮廓交并比辅助；不使用外包框面积。
    candidates=[]
    aa=[o for o in old.objects if o.semantic_id not in used_old and o.type in ('space','shaft') and o.raw_label.strip()]
    bb=[o for o in new.objects if o.semantic_id not in used_new and o.type in ('space','shaft')]
    for a in aa:
        ga=match_shape(a)
        if ga is None or not ga.area:continue
        for b in bb:
            if a.type!=b.type or a.raw_label.strip()!=b.raw_label.strip():continue
            gb=shape(b)
            if gb is None or not gb.area:continue
            union=ga.union(gb).area;score=ga.intersection(gb).area/union if union else 0
            if score>=0.5:candidates.append((score,a,b))
    for score,a,b in sorted(candidates,key=lambda row:(-row[0],row[1].semantic_id,row[2].semantic_id)):
        if a.semantic_id in used_old or b.semantic_id in used_new:continue
        alternatives=[s for s,x,y in candidates if (x.semantic_id==a.semantic_id and y.semantic_id!=b.semantic_id) or (y.semantic_id==b.semantic_id and x.semantic_id!=a.semantic_id)]
        if alternatives and max(alternatives)>=score-0.05:continue
        pair(a,b,'room_name+polygon_iou>=0.5')
    changes=[];mapping={};unchanged=set()
    for a,b,method in pairs:
        mapping[a.semantic_id]=b.semantic_id;kinds=[]
        if not same_geometry(a,b):kinds.append('几何变化')
        if (a.raw_label,a.use_code,a.classification)!=(b.raw_label,b.use_code,b.classification):kinds.append('名称或用途变化')
        if source_key(a)!=source_key(b):kinds.append('来源对象变化')
        if a.status!=b.status:kinds.append('输入状态变化')
        if kinds:changes.append({'kinds':kinds,'old':ref(a),'new':ref(b),'match_method':method})
        elif not method.endswith('identity_unverified'):unchanged.add(a.semantic_id)
    for data,used,kind in [(old,used_old,'删除'),(new,used_new,'新增')]:
        for o in data.objects:
            if o.semantic_id not in used:changes.append({'kinds':[kind],'old':ref(o) if kind=='删除' else None,'new':ref(o) if kind=='新增' else None,'match_method':'unmatched'})
    changes.sort(key=lambda c:((c['new'] or c['old'])['type'],(c['new'] or c['old'])['handle'],json.dumps(c,ensure_ascii=False)))
    for i,c in enumerate(changes):c['id']='change_'+str(i+1)
    return changes,mapping,unchanged,warnings

def inherit_reviews(old_findings,new_findings,mapping,unchanged,confirmations,review_records=None):
    from .decisions import inherit_decision
    # unchanged参数保留旧调用兼容；所有适用性判断只来自inherit_decision。
    newer={(f['rule_id'],tuple(f['object_ids'])):f for f in new_findings}
    inherited={};records=[]
    for f in old_findings:
        if f['rule_id']!='R1' or not f['object_ids'] or not f['engineer_reviewed']['reviewed_by']:continue
        room=f['object_ids'][0];new_id=mapping.get(room);nf=newer.get(('R1',(new_id,)))
        transfer=next((r for r in reversed(review_records or []) if r.get('old_decision_id')==f['decision']['id'] and nf and r.get('new_decision_id')==nf['decision']['id']),None)
        outcome=inherit_decision(f['decision'],nf['decision'] if nf else None,mapping,confirmation_available=room in confirmations,identity_confirmation=transfer)
        if outcome['inherited']:
            confirmed,review=confirmations[room]
            inherited[new_id]=(confirmed.model_copy(update={'object_id':new_id}),review)
        records.append({'old_room':room,'new_room':new_id,'room_name':f['object_name'],
            'source_handles':f['source_handles'],**outcome,'engineer_reviewed':f['engineer_reviewed'],
            'old_decision_id':f['decision']['id']})
    return inherited,records


def conclusion_changes(old_findings,new_findings,mapping):
    remaining={f['id']:f for f in new_findings};rows=[]
    for old in old_findings:
        target=mapping.get(old['object_ids'][0]) if old['object_ids'] else None
        matches=[f for f in remaining.values() if f['rule_id']==old['rule_id'] and (f['object_ids']==[target] if target else not old['object_ids'] and not f['object_ids'])]
        new=matches[0] if len(matches)==1 else None
        if new:remaining.pop(new['id'])
        kind=('消失' if new is None else '不变' if new['result']==old['result'] and new['input_confidence']==old['input_confidence'] else '由通过变不通过' if old['result']=='通过' and new['result']=='不通过' else '新增提示' if new['result']=='不通过' else '结论变化')
        rows.append({'change':kind,'rule_id':old['rule_id'],'old_id':old['id'],'new_id':new['id'] if new else None,
                     'old_result':old['result'],'new_result':new['result'] if new else None})
    for new in remaining.values():rows.append({'change':'新增提示' if new['result']=='不通过' else '新增结论','rule_id':new['rule_id'],'old_id':None,'new_id':new['id'],'old_result':None,'new_result':new['result']})
    return rows

def impact_for(change,old,new,uses):
    hits=[];uncertain=False
    for side,data in [('old',old),('new',new)]:
        reference=change[side]
        if not reference:continue
        obj=next((o for o in data.objects if o.semantic_id==reference['id']),None)
        if obj is None:uncertain=True;continue
        geo=shape(obj)
        targets=[o for o in data.objects if uses[side].get(o.semantic_id,{}).get('category') in ELECTRICAL]
        if geo is None or data.drawing.geometry_units!='mm':uncertain=True;continue
        for room in targets:
            rg=shape(room)
            if rg is None:uncertain=True;continue
            if obj.semantic_id==room.semantic_id or geo.distance(rg)<=5:
                hits.append({'side':side,**ref(room),'room_use':uses[side][room.semantic_id]['category']})
    unique={(r['side'],r['id']):r for r in hits};hits=list(unique.values())
    return {'result':'影响候选，需复核' if hits else '无法判定影响' if uncertain else '限定范围内未发现影响候选',
            'rooms':hits,'scope':'仅限已识别电气房间内部及5mm轮廓近邻；不代表对整图电气设计无影响'}

def comparison_times(old,new):
    def local(value):
        return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S') if value else '未记录'
    return {'timezone':'Asia/Shanghai','old_scan':local(old.generated_at_utc),'new_scan':local(new.generated_at_utc),
            'old_file_saved':local(old.drawing.source_last_write_utc),'new_file_saved':local(new.drawing.source_last_write_utc),
            'comparison_generated':local(datetime.now(timezone.utc).isoformat()),
            'meaning':'扫描时间是取得快照的时间；文件保存时间不是每项修改时间。只能确定两版之间存在差异，精确改动时刻未记录。'}


def change_checklist(changes,old,new):
    """面向工程师的独立核对清单；重复块表达合并，仍保留全部证据编号。"""
    rows=[];groups={}
    names={'space':'房间','wall':'墙体','opening':'门洞','door':'门','window':'窗','zone':'区域','shaft':'井道'}
    objects={side:{o.semantic_id:o for o in d.objects} for side,d in [('old',old),('new',new)]}
    for c in changes:
        ref_=c['new'] or c['old'];kind=ref_['type'];details=[];areas={}
        for side in ('old','new'):
            if c[side]:
                g=shape(objects[side][c[side]['id']])
                if kind in ('space','shaft') and g is not None:areas[side]=round(g.area/1e6,3)
        if kind in ('space','shaft') and c['old'] and c['new']:
            if c['old']['name']!=c['new']['name']:details.append('房名：'+c['old']['name']+' → '+c['new']['name'])
            if '几何变化' in c['kinds']:details.append('提取面积：'+str(areas.get('old'))+' → '+str(areas.get('new'))+' m²')
        if not details:details.append('新版未提取到对应房间' if c['basis'].startswith('房名文字仍在') else '、'.join(k for k in c['kinds'] if k!='来源对象变化'))
        key=(kind,tuple(c['kinds']),tuple(tuple(round(x,2) for x in b) for b in c['cloud_bounds']),tuple(details))
        if key in groups:
            row=groups[key];row['change_ids'].append(c['id']);row['handles']=sorted(set(row['handles']+[r['handle'] for r in (c['old'],c['new']) if r]));continue
        name=ref_['name'] if kind=='space' else names.get(kind,kind)
        if kind!='space':
            hits=sorted({r['name'] for r in c['impact']['rooms'] if r['name']})
            if not hits:
                near=[]
                for side,d in [('old',old),('new',new)]:
                    if not c[side]:continue
                    g=shape(objects[side][c[side]['id']])
                    if g is None:continue
                    near.extend((g.distance(shape(o)),o.raw_label) for o in d.objects if o.type=='space' and shape(o) is not None)
                hits=[v[1] for v in sorted(near)[:1] if v[0]<=1000]
            if hits:name+=' · '+ '、'.join(hits)
        row={'id':c['id'],'change_ids':[c['id']],'name':name,'type':names.get(kind,kind),
             'content':'；'.join(details),'basis':c['basis'],'impact':c['impact']['result'],
             'handles':[r['handle'] for r in (c['old'],c['new']) if r],'areas_m2':areas}
        rows.append(row);groups[key]=row
    return sorted(rows,key=lambda r:(r['type']!='房间',r['name'],r['id']))


def diff(old_dir,new_dir,output='dist/changes',progress=None,review_records=None):
    with snapshot_session(),geometry_session():
        return _diff(old_dir,new_dir,output,progress,review_records)


def _diff(old_dir,new_dir,output,progress,review_records):
    emit=progress or (lambda message:None)
    emit('读取并验证两版数据')
    start=time.perf_counter();old,new=load(old_dir),load(new_dir)
    emit('匹配对象来源与几何')
    if old.drawing.geometry_units!=new.drawing.geometry_units or old.drawing.coordinate_system!=new.drawing.coordinate_system:
        raise ValueError('两版单位或坐标系不同，不能直接比较；请提供同图同坐标扫描')
    changes,mapping,unchanged,warnings=compare_objects(old,new)
    for c in changes:
        for side,data in [('old',old),('new',new)]:
            if c[side]:
                o=next(o for o in data.objects if o.semantic_id==c[side]['id'])
                c[side+'_geometry']=o.geometry.model_dump()
    emit('核对旧版规则与依据')
    old_check=check(old_dir)
    emit('核对新版规则与依据')
    new_check=check(new_dir)
    from .reviews import apply_reviews
    apply_reviews(old_check['findings'],old.drawing.sha256,review_records or [])
    apply_reviews(new_check['findings'],new.drawing.sha256,review_records or [])
    confirmations,_=read_r1_confirmations(old_dir,old.drawing.sha256)
    inherited,reviews=inherit_reviews(old_check['findings'],new_check['findings'],mapping,unchanged,confirmations,review_records)
    if inherited:
        emit('重核原确认的适用范围')
        new_check=check(new_dir,inherited_confirmations=inherited)
        for f in new_check['findings']:
            if f['object_ids'] and f['object_ids'][0] in inherited and f['rule_id']=='R1':
                f['engineer_reviewed']['record_file']='旧版/l4_confirmations.yaml'
                f['values']['confirmation_inherited']=True
                f['reason']='继承未变化对象的原人工核对；'+f['reason']
    apply_reviews(new_check['findings'],new.drawing.sha256,review_records or [])
    uses={side:{r['object_id']:r for r in classify(directory)['rows']} for side,directory in [('old',old_dir),('new',new_dir)]}
    work_map=yaml.safe_load((RULES/'impact_map.yaml').read_text(encoding='utf-8'))
    identity_changes=[c for c in changes if c['kinds']==['来源对象变化']]
    changes=[c for c in changes if c['kinds']!=['来源对象变化']]
    missing_rooms=[c for c in changes if c['old'] and not c['new'] and c['old']['type']=='space']
    remaining_texts={f.source.handle.upper() for f in load(new_dir,L2).facts if f.raw_text} if missing_rooms else set()
    physical=[c for c in changes if (c['new'] or c['old'])['type'] in ('wall','opening','door','window')]
    emit('分析变化影响')
    for change_index,change in enumerate(changes,1):
        if change_index==1 or change_index%25==0 or change_index==len(changes):emit(f'分析变化影响 {change_index}/{len(changes)}')
        change['basis']='源几何或名称变化候选'
        if (change['new'] or change['old'])['type'] in ('space','shaft'):
            related=[]
            for side,dataset in [('old',old),('new',new)]:
                if not change[side]:continue
                room=next(o for o in dataset.objects if o.semantic_id==change[side]['id']);rg=shape(room)
                if rg is None:continue
                for c in physical:
                    if not c[side]:continue
                    obj=next(o for o in dataset.objects if o.semantic_id==c[side]['id']);g=shape(obj)
                    if g is not None and g.distance(rg)<=300:related.append(c['id'])
            change['related_source_changes']=sorted(set(related))
            if change['old'] and not change['new']:
                old_room=next(o for o in old.objects if o.semantic_id==change['old']['id'])
                labels={e.source_handle.upper() for e in old_room.evidence if e.code=='ROOM_LABEL_CONTAINED_TEXT'}
                if labels & remaining_texts:change['basis']='房名文字仍在，但新版未提取到对应围合：属于识别缺口，不断言房间拆除'
            if change['kinds']==['几何变化','来源对象变化'] and not related:
                change['basis']='派生围合差异：附近未发现墙/门/窗源几何变化，不作为已证实建筑修改'
        if not change.get('old_geometry',{}).get('paths') and not change.get('new_geometry',{}).get('paths'):
            change['basis']='缺少可比较路径：记录无法对应，不能断言实体新增或删除'
        change['impact']=impact_for(change,old,new,uses)
        change['cloud_bounds']=[]
        for side,data in [('old',old),('new',new)]:
            if change[side]:
                o=next(o for o in data.objects if o.semantic_id==change[side]['id']);g=shape(o)
                if g is not None and not g.is_empty:change['cloud_bounds'].append(list(g.bounds))
        if not change['cloud_bounds']:change['basis']='缺少可比较的有效几何：记录无法对应，不能断言实体新增或删除'
        work=[]
        for room in change['impact']['rooms']:
            category=room['room_use'];types=set(change['kinds'])
            if (change['new'] or change['old'])['type']=='opening':types.add('出入口变化')
            if (change['new'] or change['old'])['id']!=room['id']:types.add('贴邻范围变化')
            for row in work_map['items']:
                if row['room_use'] in (category,'*') and row['change_type'] in types:work.extend(row['work'])
        change['suggested_work']={'approved':bool(work_map.get('approved')),'items':sorted(set(work))}
    from .lighting import generate,input_hash,compare_groups
    emit('计算灯具候选与换版影响')
    old_lights=generate(old,uses['old'],input_hash(old_dir))
    new_lights=generate(new,uses['new'],input_hash(new_dir))
    lighting_changes=compare_groups(old_lights,new_lights,mapping,changes)
    from .decisions import INHERITANCE_VERSION
    result={'schema_version':'changes.v2','inheritance_version':INHERITANCE_VERSION,'object_mapping':mapping,'identity_changes':identity_changes,'origin':'REAL_JSON','lineage_assumption':'调用者提供同一DWG的两版；Handle不是跨图永久身份',
            'times':comparison_times(old,new),'checklist':change_checklist(changes,old,new),
            'old_hash':old.drawing.sha256,'new_hash':new.drawing.sha256,'geometry_units':new.drawing.geometry_units,'coordinate_system':new.drawing.coordinate_system,
            'matched':len(mapping),'unchanged':len(unchanged),'change_count':len(changes),
            'change_types':dict(Counter(k for c in changes for k in c['kinds'])),
            'impact_counts':dict(Counter(c['impact']['result'] for c in changes)),
            'changes':changes,'review_inheritance':reviews,'lighting_changes':lighting_changes,
            'conclusion_changes':conclusion_changes(old_check['findings'],new_check['findings'],mapping),
            'matching_warnings':warnings,'mapping_approved':bool(work_map.get('approved')),
            'old_check':old_check,'new_check':new_check,'tool_seconds':round(time.perf_counter()-start,4)}
    from .light_calc import calculate
    emit('复核派生计算')
    old_calculations=calculate(old,uses['old'],old_lights)['rows'];new_calculations=calculate(new,uses['new'],new_lights)['rows']
    new_calc_by_room={r['room_semantic_id']:r for r in new_calculations}
    result['lighting_calculation_changes']=[]
    for prior in old_calculations:
        rid=prior['room_semantic_id'];current=new_calc_by_room.get(mapping.get(rid))
        old_fp=prior['decision']['inputs'][0]['content_fingerprint'];new_fp=current['decision']['inputs'][0]['content_fingerprint'] if current else None
        changed=old_fp!=new_fp
        state='旧计算失效，按新版重算' if changed and prior.get('estimated') else '轮廓变化，计算适用性需按新版重核' if changed else '输入未变化，计算记录保留'
        result['lighting_calculation_changes'].append({'room_name':prior['room_name'],'old_room_id':rid,'new_room_id':mapping.get(rid),'state':state,'old_calculation':prior,'new_calculation':current,'invalidated':bool(changed and prior.get('estimated'))})
    finalize_review_decisions(result)
    emit('写出比较结果')
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    (output/'lighting_candidates.json').write_text(json.dumps(new_lights,ensure_ascii=False,indent=2),encoding='utf-8')
    from .lighting import write_dxf
    try:result['lighting_export']=write_dxf(new_lights,output/'lighting_candidates.dxf')
    except ValueError as exc:result['lighting_export']={'status':'未导出','reason':str(exc)}
    (output/'diff.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    write_impact_report(result,output/'impact_report.html')
    return {k:result[k] for k in ('origin','matched','unchanged','change_count','change_types','impact_counts','tool_seconds')} | {'output':output.as_posix()}

def write_impact_report(result,path):
    from html import escape
    e=lambda x:escape(str(x))
    body='<h1>提资变更影响单</h1><p>改动清单 → 受影响房间 → 结论变化 → 失效确认 → 需重做工作</p>'
    body+=f'<p>改动对象{result["change_count"]}项；{e(result["impact_counts"])}；工具耗时{result["tool_seconds"]}秒。</p>'
    body+='<p>仅比较调用者提供的同图两版JSON；影响为已识别范围内的候选，工作映射'+('已批准' if result['mapping_approved'] else '尚未工程师批准')+'。</p>'
    for c in result['changes']:
        body+=f'<details><summary>{e((c["new"] or c["old"])["name"])} · {e(c["kinds"])} · {e(c["impact"]["result"])}</summary>'
        for side,label in [('old','旧版'),('new','新版')]:
            r=c[side];body+=f'<p>{label}：'+(f'{e(r["name"])} / Handle {e(r["handle"])} / ID {e(r["id"])}' if r else '不存在')+'</p>'
        rooms='；'.join(r['name']+'（'+r['side']+'，Handle '+r['handle']+'）' for r in c['impact']['rooms'])
        work='；'.join(c['suggested_work']['items'])
        body+=f'<p>匹配：{e(c["match_method"])}</p><p>受影响房间：{e(rooms or "当前范围未命中")}</p><p>工作建议（'+('已批准' if c['suggested_work']['approved'] else '草案')+f'）：{e(work or "尚无对应建议，需工程师补充")}</p></details>'
    body+='<h2>灯具布置候选换版</h2><p>演示规则，非照度设计；按同一组当前演示规则分别重算两版，不读取DWG中既有灯具。</p>'
    for row in result.get('lighting_changes',[]):
        body+=f'<p>{e(row["room_name"])}：{e(row["state"])}；{e(row["reason"])}。旧{row.get("old_count",0)}个→新{row.get("new_count",0)}个。</p>'
    body+='<h2>结论变化</h2>'
    old_findings={f['id']:f for f in result['old_check']['findings']}
    new_findings={f['id']:f for f in result['new_check']['findings']}
    for row in result['conclusion_changes']:
        f=new_findings.get(row['new_id']) or old_findings.get(row['old_id'])
        body+=f'<p>{e(f.get("object_name","未识别到适用房间"))} · {e(row["rule_id"])}：{e(row["old_result"] or "无旧结论")} → {e(row["new_result"] or "无新结论")}（{e(row["change"])}）</p>'
    body+='<h2>确认继承与失效</h2>'
    for row in result['review_inheritance']:
        body+=f'<p>{e(row["room_name"])}：<b>{e(row["state"])}</b>。{e(row["reason"])}；原复核人{e(row["engineer_reviewed"]["reviewed_by"])}，日期{e(row["engineer_reviewed"]["reviewed_date"])}。</p>'
    body+='<p>本单不修改原图，不代替工程师判断；未识别对象的变化不在当前覆盖范围。</p>'
    Path(path).write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>提资变更影响单</title><style>body{font:16px/1.7 "Microsoft YaHei",sans-serif;background:#f5f7fb;color:#21334c;max-width:1050px;margin:auto;padding:24px}details{background:white;padding:16px;border:1px solid #ccd7e7;border-radius:8px;margin:12px 0}summary{cursor:pointer;font-weight:bold}p{overflow-wrap:anywhere}</style>'+body+'</html>',encoding='utf-8')



def finalize_review_decisions(result):
    """复用原优先项/决策处理，供完整比较与仅复核重算共享。"""
    from .priority import room_priorities
    for c in result['changes']:
        ref=c['new'] or c['old'];oid=(c['new'] or {}).get('id')
        c['priorities']=room_priorities(oid,ref['name'],[f for f in result['new_check']['findings'] if oid in f['object_ids']],result,(c['old'] or {}).get('id')) if ref['type']=='space' else []
    current_findings={f['id']:f for f in result['new_check']['findings']}
    prior_findings={f['id']:f for f in result['old_check']['findings']}
    for change in result['changes']:
        for alert in change['priorities']:
            for fid in alert['finding_ids']:
                if fid not in current_findings:continue
                finding=current_findings[fid];finding['priority_rank']=alert['rank'];finding['decision']['priority']=alert
                finding['decision']['priority_evidence']={'old_drawing_sha256':result['old_hash'],'new_drawing_sha256':result['new_hash'],'change_id':change['id'],'prior_decision_ids':[prior_findings[i]['decision']['id'] for i in alert['finding_ids'] if i in prior_findings]}
    from .decisions import inherit_decision
    new_decisions={(f['rule_id'],tuple(f['object_ids'])):f['decision'] for f in result['new_check']['findings']}
    result['decision_inheritance']=[]
    shared_reviews={r['old_decision_id']:r for r in result['review_inheritance']}
    for f in result['old_check']['findings']:
        mapped=tuple(result['object_mapping'].get(i) for i in f['object_ids'])
        current=new_decisions.get((f['rule_id'],mapped))
        shared=shared_reviews.get(f['decision']['id'])
        outcome=({k:shared[k] for k in ('policy_version','status','state','reason','inherited','requires_confirmation','confirmation_available') } | ({k:shared[k] for k in ('engineer','identity_confirmation') if k in shared})) if shared else inherit_decision(f['decision'],current,result['object_mapping'])
        if outcome['inherited'] and current and not shared:current['engineer']=outcome['engineer'];current['sign_off_state']='原范围工具结果核对已继承，非整图签字'
        result['decision_inheritance'].append({'old_decision_id':f['decision']['id'],'new_decision_id':current['id'] if current else None,'rule_id':f['rule_id'],**outcome})
