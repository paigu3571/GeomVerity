# SPDX-License-Identifier: MPL-2.0
"""只读房名/围合问题诊断；坐标建议不自动改图、不补造墙。"""
import csv
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path
from shapely.geometry import Point,Polygon
from shapely.ops import unary_union,polygonize_full
from .recovery import label_rows,wall_lines


def issue(label,x,y,reason,code='UNRESOLVED_BOUNDARY'):
    return {'id':'issue_'+hashlib.sha256(label.source.stable_path.encode()).hexdigest()[:24],
        'room_name':label.raw_text,'text_handle':label.source.handle,
        'outer_block_handle':label.source.block_path[0].split(':')[0] if label.source.block_path else None,
        'point_wcs_mm':[x,y],'reason_code':code,'reason':reason,'gap_candidates':[],
        'text_position_candidate':None,'automatic_text_move':False,'automatic_wall_added':False,
        'downstream_action':'此处房间范围未确认；不要据此认定墙/门改动不影响灯具，需定位核对。'}


def targets_and_issues(l1,l2,l3):
    unresolved={f.source_handle for f in l3.findings if f.reason_code=='KNOWN_SPACE_LABEL_UNRESOLVED'}
    associated={o.source.handle for o in l3.objects if o.type in ('space','shaft','zone')}
    associated.update(e.source_handle for o in l3.objects if o.type in ('space','shaft','zone') for e in o.evidence if e.kind=='spatial_text')
    targets=[];issues=[]
    for f,x,y in label_rows(l2):
        if f.source.handle in associated or f.raw_text.startswith('[REDACTED_'):continue
        # 房名图层混有门号、尺寸及说明；词典外只查房名形态，不推定专业用途。
        likely_room=bool(re.search(r'(?:房|室|间|井|池|厅|楼梯|通道|坡道|洗消区|男卫|女卫|服务站)(?:[（(][^）)]*[）)])?$',f.raw_text))
        if f.source.handle not in unresolved and not likely_room:continue
        if f.raw_text in ('采光井','采光天井','露天井'):
            row=issue(f,x,y,'顶板开洞区域本阶段暂不补充用途语义，不按实体房间自动补提取。','REGION_SEMANTICS_DEFERRED');row['downstream_action']='保留源文字位置；后续单独建立区域语义。';issues.append(row)
        elif '上空' in f.raw_text:
            row=issue(f,x,y,'“上空”为跨层空间说明，本轮不把它自动新增为本层实体房间。','OVERHEAD_LABEL');row['downstream_action']='核对楼层与空间用途后再参与布置。';issues.append(row)
        else:targets.append((f.raw_text,f.source.handle))
    return targets,issues


def diagnose_label(l1,l2,l3,name,handle,error,radius=20000):
    label,x,y=next(r for r in label_rows(l2) if r[0].raw_text==name and r[0].source.handle==handle)
    row=issue(label,x,y,error)
    ox=math.floor(x/5)*5;oy=math.floor(y/5)*5;point=Point(x-ox,y-oy)
    walls,_=wall_lines(l1,ox,oy,radius)
    if not walls:row['reason_code']='NO_WALL_DATA';return row
    network=unary_union([line for _,line in walls]);polygons,cuts,dangles,invalid=polygonize_full(network)
    enclosing=[p for p in polygons.geoms if p.contains(point)]
    row['enclosing_areas_m2']=[round(p.area/1e6,3) for p in enclosing]
    row['nearby_closed_region_count']=len(polygons.geoms)
    if '多个房名' in error:row['reason_code']='MULTIPLE_LABELS'
    elif '明显重叠' in error:row['reason_code']='EXISTING_ROOM_OVERLAP'
    elif '内孔' in error:row['reason_code']='INNER_HOLES'
    elif '超出' in error:row['reason_code']='SEARCH_EXTENT'
    elif enclosing and max(p.area for p in enclosing)<2e6:row['reason_code']='BELOW_AREA_THRESHOLD'
    elif enclosing and min(p.area for p in enclosing)>500e6:row['reason_code']='ABOVE_AREA_THRESHOLD'
    # 原始有效语义轮廓里出现另一房名，只给位置冲突提示，不把它强配给邻房。
    conflicts=[]
    for o in l3.objects:
        if o.type not in ('space','shaft','zone') or not o.geometry.is_closed or not o.geometry.paths:continue
        poly=Polygon([(p.x-ox,p.y-oy) for p in o.geometry.paths[0]])
        if poly.is_valid and poly.contains(point) and o.raw_label!=name:
            conflicts.append({'object_id':o.semantic_id,'room_name':o.raw_label,'handle':o.source.handle})
    row['conflicting_rooms']=conflicts
    if conflicts:
        row['reason_code']='TEXT_REGION_CONFLICT';row['reason']='房名定位点落在另一已提取空间内：'+ '、'.join(r['room_name'] for r in conflicts)+'。可能是文字位置或原轮廓问题，不能自动挪文字。'
    # 附近唯一无房名闭合区域，仅提出文字位置候选，不用于生成房间。
    candidates=[]
    for poly in polygons.geoms:
        if poly.interiors or not 2e6<=poly.area<=500e6 or poly.contains(point):continue
        if not 5<poly.distance(point)<=2000:continue
        if any(poly.contains(Point(lx-ox,ly-oy)) for _,lx,ly in label_rows(l2)):continue
        candidates.append(poly)
    candidates.sort(key=lambda p:p.distance(point))
    if candidates:
        poly=candidates[0];q=poly.representative_point()
        row['text_position_candidate']={'suggested_point_wcs_mm':[round(q.x+ox,3),round(q.y+oy,3)],
            'distance_to_boundary_mm':round(poly.distance(point),1),'area_m2':round(poly.area/1e6,3),
            'nearby_empty_region_count':len(candidates),'status':'位置建议；需工程师确认，不自动移动',
            'outline_wcs_mm':[[round(a+ox,3),round(b+oy,3)] for a,b in poly.exterior.coords]}
        if row['reason_code']=='UNRESOLVED_BOUNDARY':row['reason_code']='TEXT_POSITION_CANDIDATE';row['reason']='定位点不在有效围合内；附近存在无房名闭合区域，已标出位置候选。不是已证实文字错位。'
    # 开口端点候选须近距且方向相近；不能把门洞、墙端或裁剪误称真实缺墙。
    degrees=Counter();directions={}
    for line in network.geoms if hasattr(network,'geoms') else [network]:
        coords=list(line.coords)
        for a,b in [(coords[0],coords[1]),(coords[-1],coords[-2])]:
            a=tuple(round(v,5) for v in a);degrees[a]+=1;directions[a]=(a[0]-b[0],a[1]-b[1])
    ends=[a for a,n in degrees.items() if n==1 and Point(a).distance(point)<=10000]
    pairs=[]
    for i,a in enumerate(ends):
        for b in ends[i+1:]:
            dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
            if not 5<length<=500:continue
            da,db=directions[a],directions[b]
            if max(abs((d[0]*dx+d[1]*dy)/(math.hypot(*d)*length)) for d in [da,db])<.9:continue
            nearby=[p.source.handle for p,line in walls if line.distance(Point(a))<.1 or line.distance(Point(b))<.1]
            pairs.append({'a_wcs_mm':[round(a[0]+ox,3),round(a[1]+oy,3)],'b_wcs_mm':[round(b[0]+ox,3),round(b[1]+oy,3)],
                'length_mm':round(length,1),'source_handles':sorted(set(nearby)),
                'status':'边界端点待检查；可能是墙端/门洞/裁剪，不自动补墙',
                '_distance':Point((a[0]+b[0])/2,(a[1]+b[1])/2).distance(point)})
    pairs.sort(key=lambda p:p['_distance'])
    for p in pairs[:5]:p.pop('_distance');row['gap_candidates'].append(p)
    row['search_radius_mm']=radius
    return row


def write_issues(output,issues,recovered,snapshot=None):
    result={'scope':'原L3未解析房名，加名称图层中未关联的词典外房名候选；门号/尺寸/说明不按房间强补' ,
        'counts':dict(Counter(r['reason_code'] for r in issues)),'remaining':len(issues),
        'recovered_count':len(recovered),'snapshot_sha256':hashlib.sha256((Path(snapshot) if snapshot else Path(output)/'building-semantics.v1.json.gz').read_bytes()).hexdigest(),'issues':issues,'recovered':recovered,
        'note':'端点与文字位置都是排查候选，不是已证实CAD错误；未自动补墙或挪文字。'}
    output=Path(output);(output/'room_issues.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    with (output/'room_issues.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f);writer.writerow(['房名','文字Handle','问题类型','中文原因','端点候选数','文字位置候选','下游处理'])
        writer.writerows([r['room_name'],r['text_handle'],r['reason_code'],r['reason'],len(r['gap_candidates']),'有' if r['text_position_candidate'] else '无',r['downstream_action']] for r in issues)
    return {k:v for k,v in result.items() if k not in ('issues','recovered')}


def diagnose_directory(directory, output):
    """生成当前快照的问题定位侧车；不新增空间或修改三层数据。"""
    from .model import load,L1,L2
    directory=Path(directory);output=Path(output);output.mkdir(parents=True,exist_ok=True)
    l1,l2,l3=load(directory,L1),load(directory,L2),load(directory)
    targets,issues=targets_and_issues(l1,l2,l3)
    for name,handle in targets:
        issues.append(diagnose_label(l1,l2,l3,name,handle,'原扫描未关联有效房间围合；请核对房名位置和边界。'))
    snapshot=directory/'building-semantics.v1.json.gz'
    if not snapshot.is_file():snapshot=snapshot.with_suffix('')
    return write_issues(output,issues,[],snapshot)
