# SPDX-License-Identifier: MPL-2.0
"""L4隔墙贴邻候选：同一L3墙的两面证据，不修改源语义。"""
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
import yaml
from shapely.geometry import LineString, box
from shapely.strtree import STRtree
from .model import load
from .uses import classify

from .resources import rules_directory
CONFIG=rules_directory()/'adjacency.yaml'
TARGETS={'SUBSTATION','DISTRIBUTION_ROOM','ELECTRICAL_SHAFT'}


def segments(obj):
    result=[]
    for path in obj.geometry.paths:
        points=[(p.x,p.y) for p in path]
        pairs=list(zip(points,points[1:]))
        if obj.geometry.is_closed and len(points)>2 and points[0]!=points[-1]:pairs.append((points[-1],points[0]))
        for a,b in pairs:
            length=math.dist(a,b)
            if length>1e-4:result.append((a,b,length))
    return result


def project(seg,origin,u):
    points=[((p[0]-origin[0])*u[0]+(p[1]-origin[1])*u[1],
             -(p[0]-origin[0])*u[1]+(p[1]-origin[1])*u[0]) for p in seg[:2]]
    return sorted(p[0] for p in points),[p[1] for p in points]


def parallel(a,b,angle):
    ax,ay=a[1][0]-a[0][0],a[1][1]-a[0][1]
    bx,by=b[1][0]-b[0][0],b[1][1]-b[0][1]
    return abs(ax*by-ay*bx)/(a[2]*b[2])<=math.sin(math.radians(angle))


def between_segments(a,b,wall_rows,config):
    """两房边界共同投影区间内，必须有同一墙体的两个面。"""
    if not parallel(a,b,config['parallel_angle_degrees']):return []
    u=((a[1][0]-a[0][0])/a[2],(a[1][1]-a[0][1])/a[2])
    ts,ns=project(b,a[0],u)
    lo,hi=max(0,ts[0]),min(a[2],ts[1]);tol=config['thickness_tolerance_mm']
    if hi-lo<config['min_overlap_m']*1000 or ns[0]*ns[1]<=0:return []
    # 近似平行也需整个投影段的间距足够一致，避免斜交面假贴邻。
    if abs(ns[0]-ns[1])>tol:return []
    gap=sum(ns)/2
    if abs(gap)<=tol or abs(gap)>config['max_search_gap_mm']:return []
    faces=defaultdict(lambda:[[],[]])
    for wall,s in wall_rows:
        if not parallel(a,s,config['parallel_angle_degrees']):continue
        xs,ys=project(s,a[0],u);start,end=max(lo,xs[0]),min(hi,xs[1])
        if end-start<config['min_overlap_m']*1000:continue
        normal=sum(ys)/2
        if max(abs(y) for y in ys)<=tol:faces[wall.semantic_id][0].append((wall,start,end,normal))
        if max(abs(y-gap) for y in ys)<=tol:faces[wall.semantic_id][1].append((wall,start,end,normal))
    hits=[]
    for key,(left,right) in faces.items():
        best=None
        for x in left:
            for y in right:
                overlap=min(x[2],y[2])-max(x[1],y[1]);thickness=abs(y[3]-x[3])
                mid=(x[3]+y[3])/2
                if overlap<config['min_overlap_m']*1000 or abs(thickness-abs(gap))>tol:continue
                if not min(0,gap)<mid<max(0,gap):continue
                if best is None or overlap>best['overlap_mm']:
                    best={'wall_id':key,'wall_handle':x[0].source.handle,'wall_status':x[0].status,
                          'overlap_mm':round(overlap,3),'boundary_gap_mm':round(abs(gap),3),
                          'wall_thickness_mm':round(thickness,3),
                          'thickness_source':'同一L3 Wall的两侧平行几何面；非属性墙厚'}
        if best:hits.append(best)
    return hits


def adjacency(data,classes,config=None):
    config=config or yaml.safe_load(CONFIG.read_text(encoding='utf-8'))
    if data.drawing.geometry_units!='mm':
        return {'origin':'REAL_JSON','candidate_count':0,'candidates':[],'note':'单位不是毫米，无法计算隔墙贴邻','config':config}
    rooms=[o for o in data.objects if o.type in ('space','shaft') and o.geometry.is_closed
           and classes.get(o.semantic_id,{}).get('category')!='EXCLUDED']
    targets=[o for o in rooms if classes.get(o.semantic_id,{}).get('category') in TARGETS]
    room_segs=[(o,s) for o in rooms for s in segments(o)]
    wall_segs=[(o,s) for o in data.objects if o.type=='wall' for s in segments(o)]
    room_tree=STRtree([LineString(s[:2]) for _,s in room_segs])
    wall_tree=STRtree([LineString(s[:2]) for _,s in wall_segs])
    best={}
    for room in targets:
        for a in segments(room):
            bounds=LineString(a[:2]).bounds;gap=config['max_search_gap_mm'];tol=config['thickness_tolerance_mm']
            nearby=room_tree.query(box(bounds[0]-gap,bounds[1]-gap,bounds[2]+gap,bounds[3]+gap))
            for i in nearby:
                other,b=room_segs[int(i)]
                if other.semantic_id==room.semantic_id:continue
                if not parallel(a,b,config['parallel_angle_degrees']):continue
                combined=LineString([*a[:2],*b[:2]]).bounds
                ids=wall_tree.query(box(combined[0]-tol,combined[1]-tol,combined[2]+tol,combined[3]+tol))
                for hit in between_segments(a,b,[wall_segs[int(j)] for j in ids],config):
                    key=(room.semantic_id,other.semantic_id,hit['wall_id'])
                    if key not in best or hit['overlap_mm']>best[key]['overlap_mm']:
                        best[key]={'room_id':room.semantic_id,'room_name':room.raw_label,'room_handle':room.source.handle,
                                   'other_id':other.semantic_id,'other_name':other.raw_label,'other_handle':other.source.handle,
                                   'other_category':classes.get(other.semantic_id,{}).get('category'),**hit,
                                   'candidate_source':'geometry_partition_wall','status':'输入待复核'}
    rows=sorted(best.values(),key=lambda r:(r['room_name'],r['other_name'],r['wall_handle']))
    return {'origin':'REAL_JSON','target_count':len(targets),'candidate_count':len(rows),'candidates':rows,'config':config,
            'note':'隔墙贴邻候选；同一墙两面几何计算厚度，仍需工程师核对；无命中不证明无贴邻'}


def neighbors(directory,output=None):
    data=load(directory);classes={r['object_id']:r for r in classify(directory)['rows']}
    result=adjacency(data,classes)
    if output:
        folder=Path(output);folder.mkdir(parents=True,exist_ok=True)
        (folder/'adjacency.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        objects={o.semantic_id:o for o in data.objects};grouped={}
        for row in result['candidates']:
            key=tuple((objects[row[k]].source.handle,objects[row[k]].raw_label,
                       tuple(round(v,2) for v in (objects[row[k]].geometry.bounds.min_x,objects[row[k]].geometry.bounds.min_y)))
                      for k in ('room_id','other_id'))
            g=grouped.setdefault(key,{'目标房间':row['room_name'],'房间Handle':row['room_handle'],
                '隔墙邻房':row['other_name'],'邻房Handle':row['other_handle'],'墙体Handle':set(),
                '最大重叠长度(m)':0,'墙厚(mm)':set(),'状态':'输入待复核'})
            g['墙体Handle'].add(row['wall_handle']);g['墙厚(mm)'].add(row['wall_thickness_mm'])
            g['最大重叠长度(m)']=max(g['最大重叠长度(m)'],row['overlap_mm']/1000)
        rows=[]
        for g in grouped.values():
            g['墙体Handle']='、'.join(sorted(g['墙体Handle']))
            g['墙厚(mm)']='、'.join(str(x) for x in sorted(g['墙厚(mm)']))
            rows.append(g)
        result['neighbor_pair_count']=len(rows)
        with (folder/'neighbors.csv').open('w',encoding='utf-8-sig',newline='') as f:
            fields=['目标房间','房间Handle','隔墙邻房','邻房Handle','墙体Handle','最大重叠长度(m)','墙厚(mm)','状态']
            writer=csv.DictWriter(f,fields);writer.writeheader();writer.writerows(rows)
        result['output']=folder.as_posix()
    return result
