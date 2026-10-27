# SPDX-License-Identifier: MPL-2.0
"""基于真实空间轮廓的演示灯具候选，不作照度设计，不修改源DWG。"""
import hashlib
import json
import math
from pathlib import Path
import yaml
from shapely.geometry import Polygon,Point,LineString,box
from shapely.strtree import STRtree
from .adjacency import segments,parallel,project
from .model import load
from .uses import classify

from .resources import rules_directory
RULES=rules_directory()
TITLE='灯具布置候选（演示规则，非照度设计）'


def input_hash(directory):
    p=Path(directory)/'building-semantics.v1.json'
    if not p.is_file():p=p.with_name(p.name+'.gz')
    return hashlib.sha256(p.read_bytes()).hexdigest()


def short_id(prefix,value):return prefix+hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:24]


def mounting_context(data):
    faces=[(o,seg) for o in data.objects if o.type=='wall' for seg in segments(o)]
    openings=[o for o in data.objects if o.type in ('opening','door','window') and o.geometry.bounds.is_valid]
    tree=STRtree([LineString(seg[:2]) for _,seg in faces])
    return faces,tree,openings


def wall_points(room,rule,context):
    """把墙体碎段投影到同一房间周长轴，合并后布点，避免每个CAD碎段重启间距。"""
    if context is None:return [],{'placement_surface':'缺少墙体几何，未生成壁灯','mounting_wall_count':0}
    faces,tree,openings=context;tol=rule.get('wall_match_tolerance_mm',20)
    margin=rule.get('opening_clearance_mm',300);spacing=rule['max_spacing_m']*1000
    radius=rule.get('symbol_radius_mm',150);poly=Polygon([(p.x,p.y) for p in room.geometry.paths[0]])
    boxes=[box(o.geometry.bounds.min_x-margin,o.geometry.bounds.min_y-margin,o.geometry.bounds.max_x+margin,o.geometry.bounds.max_y+margin) for o in openings]
    opening_tree=STRtree(boxes);spans=[];blocked=[];excluded=set();offset=0.0
    for boundary in segments(room):
        line=LineString(boundary[:2]);u=((boundary[1][0]-boundary[0][0])/boundary[2],(boundary[1][1]-boundary[0][1])/boundary[2])
        for idx in sorted(int(i) for i in tree.query(line.buffer(tol))):
            wall,face=faces[idx]
            if not parallel(boundary,face,1):continue
            ts,ns=project(face,boundary[0],u)
            if max(abs(n) for n in ns)>tol:continue
            lo=max(0,ts[0]);hi=min(boundary[2],ts[1])
            if hi-lo<1:continue
            spans.append((offset+lo,offset+hi,offset,boundary,u,wall,face))
            for oi in sorted(int(i) for i in opening_tree.query(line,predicate='intersects')):
                corners=list(boxes[oi].exterior.coords)
                projections=[(x-boundary[0][0])*u[0]+(y-boundary[0][1])*u[1] for x,y in corners]
                left=max(lo,min(projections));right=min(hi,max(projections))
                if right>left:blocked.append((offset+left,offset+right));excluded.add(openings[oi].source.handle)
        offset+=boundary[2]
    def union(intervals):
        merged=[]
        for left,right in sorted(intervals):
            if merged and left<=merged[-1][1]+.01:merged[-1]=(merged[-1][0],max(right,merged[-1][1]))
            else:merged.append((left,right))
        return merged
    available=union((a,b) for a,b,*_ in spans)
    for a,b in union(blocked):
        cut=[]
        for left,right in available:
            if b<=left or a>=right:cut.append((left,right));continue
            if a>left:cut.append((left,a))
            if b<right:cut.append((b,right))
        available=cut
    # 接缝不是墙体中断：闭合周长起终点的可安装区合成同一段再均布。
    if len(available)>1 and available[0][0]<.01 and available[-1][1]>offset-.01:
        available=[(available[-1][0],available[0][1]+offset),*available[1:-1]]
    points=[];walls=set();rejected=0;largest_gap=0.0
    def place(distance):
        t=distance%offset
        for left,right,start,boundary,u,wall,face in spans:
            if not left-.001<=t<=right+.001:continue
            q=(boundary[0][0]+u[0]*(t-start),boundary[0][1]+u[1]*(t-start))
            fu=((face[1][0]-face[0][0])/face[2],(face[1][1]-face[0][1])/face[2])
            along=max(0,min(face[2],(q[0]-face[0][0])*fu[0]+(q[1]-face[0][1])*fu[1]))
            anchor=(face[0][0]+fu[0]*along,face[0][1]+fu[1]*along);normal=(-fu[1],fu[0])
            for sign in (1,-1):
                for inset in (radius,radius+tol+.02):
                    centre=(anchor[0]+sign*normal[0]*inset,anchor[1]+sign*normal[1]*inset)
                    if not poly.contains(Point(centre)) or poly.boundary.distance(Point(centre))<radius-.001:continue
                    # 用最小必要内移修正墙/房间容差差异，不以丢点掩盖10~20mm的偏差。
                    if inset>radius:
                        low,high=radius,inset
                        for _ in range(18):
                            mid=(low+high)/2;c=Point(anchor[0]+sign*normal[0]*mid,anchor[1]+sign*normal[1]*mid)
                            if poly.contains(c) and poly.boundary.distance(c)>=radius:high=mid
                            else:low=mid
                        inset=high;centre=(anchor[0]+sign*normal[0]*inset,anchor[1]+sign*normal[1]*inset)
                    if len(opening_tree.query(Point(centre).buffer(radius),predicate='intersects')):continue
                    if any(math.dist(centre,(p['x'],p['y']))<radius*2 for p in points):continue
                    return {'x':round(centre[0],3),'y':round(centre[1],3),'z':0.0,'mounting_wall_id':wall.semantic_id,
                        'mounting_wall_handle':wall.source.handle,'wall_anchor_x':round(anchor[0],3),'wall_anchor_y':round(anchor[1],3),
                        'symbol_radius_mm':radius,'inset_from_wall_mm':round(inset,3)}
        return None
    for left,right in available:
        if right-left<radius*2:continue
        n=max(1,math.ceil((right-left)/spacing));step=(right-left)/n;placed=[]
        for i in range(n):
            target=left+(i+.5)*step;found=None;at=target
            for shift in (0,radius,-radius,2*radius,-2*radius):
                at=target+shift
                if left+radius<=at<=right-radius:found=place(at)
                if found:break
            if found:points.append(found);walls.add(found['mounting_wall_handle']);placed.append(at)
            else:rejected+=1
        placed.sort()
        gaps=[b-a for a,b in zip(placed,placed[1:])]
        if placed:gaps.extend((2*(placed[0]-left),2*(right-placed[-1])))
        else:gaps.append(right-left)
        largest_gap=max(largest_gap,max(gaps,default=0))
    return sorted(points,key=lambda p:(p['x'],p['y'],p['mounting_wall_handle'])),{
        'placement_surface':'合并同一周长轴上的已有墙面；连续可安装区均布，开口处断开','mounting_wall_count':len(walls),
        'opening_clearance_mm':margin,'excluded_opening_handles':sorted(excluded),'wall_match_tolerance_mm':tol,
        'available_wall_length_mm':round(sum(b-a for a,b in available),3),'rejected_placement_count':rejected,
        'largest_candidate_spacing_mm':round(largest_gap,3),'needs_manual_spacing_review':largest_gap>spacing+.1,
        'spacing_scope':'按连续可安装墙段均布；圆角/缺墙/避让造成缺点时明确标记间距待复核，不能作为照明设计通过'}


def layout_room(room,grid,wall,mode='auto',context=None):
    if not room.geometry.is_closed or len(room.geometry.paths)!=1:
        return {'result':'无法生成','reason':'缺少单一闭合空间轮廓','points':[]}
    path=room.geometry.paths[0]
    if len(path)<3:return {'result':'无法生成','reason':'空间轮廓点不足','points':[]}
    ox=min(p.x for p in path);oy=min(p.y for p in path)
    poly=Polygon([(p.x-ox,p.y-oy) for p in path])
    if not poly.is_valid or poly.is_empty or poly.area<=0:
        return {'result':'无法生成','reason':'空间轮廓无效，需人工布置','points':[]}
    rect=poly.minimum_rotated_rectangle;ratio=poly.area/rect.area
    use_grid=mode=='grid' or mode=='auto' and ratio>=grid['min_rectangle_ratio']
    rule=grid if use_grid else wall
    if not rule.get('approved'):return {'result':'无法生成','reason':'演示规则未批准','points':[]}
    if use_grid and ratio<grid['min_rectangle_ratio']:
        return {'result':'异形房间需人工布置','reason':'轮廓面积/最小外包矩形面积不足0.95','rectangle_ratio':round(ratio,6),'points':[], 'rule_id':grid['id'],'rule_version':grid['rule_version']}
    clearance=rule['wall_clearance_m']*1000;spacing=rule['max_spacing_m']*1000
    local=[];extra={}
    if use_grid:
        corners=list(rect.exterior.coords)[:-1];edges=[]
        for a,b in zip(corners,corners[1:]+corners[:1]):
            dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
            if dx<0 or abs(dx)<1e-8 and dy<0:dx,dy=-dx,-dy
            edges.append((length,dx/length,dy/length))
        _,ux,uy=max(edges);vs=[(x*ux+y*uy,-x*uy+y*ux) for x,y in corners]
        lowx=min(x for x,y in vs)+clearance;highx=max(x for x,y in vs)-clearance
        lowy=min(y for x,y in vs)+clearance;highy=max(y for x,y in vs)-clearance
        if highx>=lowx and highy>=lowy:
            nx=max(1,math.ceil((highx-lowx)/spacing)+1);ny=max(1,math.ceil((highy-lowy)/spacing)+1)
            xs=[(lowx+highx)/2] if nx==1 else [lowx+i*(highx-lowx)/(nx-1) for i in range(nx)]
            ys=[(lowy+highy)/2] if ny==1 else [lowy+j*(highy-lowy)/(ny-1) for j in range(ny)]
            for x in xs:
                for y in ys:
                    p=Point(x*ux-y*uy,x*uy+y*ux)
                    if poly.covers(p) and poly.boundary.distance(p)>=clearance-1e-5:local.append((p.x,p.y))
            extra={'grid_columns':nx,'grid_rows':ny,'grid_spacing_x_mm':0 if nx==1 else (highx-lowx)/(nx-1),
                   'grid_spacing_y_mm':0 if ny==1 else (highy-lowy)/(ny-1),
                   'filtered_grid_points':nx*ny-len(local)}
        if extra.get('filtered_grid_points'):
            if mode=='auto':return layout_room(room,grid,wall,'wall',context)
            return {'result':'无法生成','reason':'局部凹口使网格不完整，需人工布置','points':[],
                    'rectangle_ratio':round(ratio,6),'rule_id':grid['id'],'rule_version':grid['rule_version']}
    else:
        wall_result,extra=wall_points(room,rule,context)
    points=[{'x':round(ox+x,3),'y':round(oy+y,3),'z':0.0} for x,y in local]
    if not use_grid:points=wall_result
    return {'result':'已生成候选' if points else '无法生成','reason':'按演示规则布点；仍需专业布置' if points else '缺少可用墙面或扣除门洞后无可安装墙段，需人工布置',
            'rule_id':rule['id'],'rule_version':rule['rule_version'],'strategy':rule['strategy'],
            'rectangle_ratio':round(ratio,6),'wall_clearance_mm':clearance if use_grid else 0,'max_spacing_mm':spacing,
            'points':points,**extra}


def generate(data,classes,digest,mode='auto'):
    if data.drawing.geometry_units!='mm':raise ValueError('灯具候选仅支持毫米单位，不能猜测比例')
    if data.status=='failed':raise ValueError('语义扫描失败，不能生成灯具候选')
    grid=yaml.safe_load((RULES/'LIGHT-DEMO-001.yaml').read_text(encoding='utf-8'))
    wall=yaml.safe_load((RULES/'LIGHT-DEMO-002.yaml').read_text(encoding='utf-8'))
    groups=[];context=mounting_context(data)
    for room in data.objects:
        if room.type!='space' or classes.get(room.semantic_id,{}).get('category') not in grid['applies_to']:continue
        placed=layout_room(room,grid,wall,mode,context)
        source=[room.source.handle,tuple(p.split(':')[0] for p in room.source.block_path),tuple(room.source.xref_path)]
        handles=sorted({room.source.handle,*[e.source_handle for e in room.evidence if e.kind=='geometry_fact' and e.source_handle]})
        for p in placed['points']:
            p['id']=short_id('light_',[source,placed['rule_id'],placed['rule_version'],p['x'],p['y']])
        groups.append({'group_id':short_id('light_group_',[source,placed.get('rule_id'),placed['points']]),
            'room_semantic_id':room.semantic_id,'room_name':room.raw_label,'room_source_handles':handles,
            'room_source':room.source.model_dump(),'input_sha256':digest,'input_status':room.status,
            'state':'生成候选','title':TITLE,'candidate_count':len(placed['points']),**placed})
    from .decisions import lighting_decisions
    result={'origin':'REAL_JSON','title':TITLE,'input_sha256':digest,'drawing_sha256':data.drawing.sha256,
            'geometry_units':'mm','coordinate_system':data.drawing.coordinate_system,'mode':mode,
            'groups':groups,'point_count':sum(len(g['points']) for g in groups),
            'note':'壁灯沿已有墙面布点并按开口几何避让；未绘制或缺失的门洞不能代为识别，不作照度、设备避让或施工判断；不修改源图'}
    lighting_decisions(data,result,'run_'+digest[:24])
    return result


def generate_directory(directory,mode='auto'):
    return generate(load(directory),{r['object_id']:r for r in classify(directory)['rows']},input_hash(directory),mode)


def write_dxf(result,path):
    try:import ezdxf
    except ImportError:raise ValueError('候选DXF需可选依赖：python -m pip install -e ".[dxf]"')
    doc=ezdxf.new('R2010');doc.units=4;doc.appids.new('CST_TRACE')
    doc.layers.new('CST_LIGHT_CANDIDATE',dxfattribs={'color':2})
    doc.layers.new('CST_LIGHT_INVALID',dxfattribs={'color':1})
    block=doc.blocks.new('CST_LIGHT_CANDIDATE');block.add_circle((0,0),150)
    block.add_line((-100,-100),(100,100));block.add_line((-100,100),(100,-100))
    tags=['rule_id','rule_version','room_semantic_id','room_source_handles','input_sha256','lamp_id','state','mounting_wall_handle']
    for i,tag in enumerate(tags):block.add_attdef(tag,insert=(0,-200-i*30),height=25,dxfattribs={'flags':1})
    count=invalid=0
    for group in [*result['groups'],*result.get('invalidated_groups',[])]:
        stale=group.get('state')=='失效'
        for p in group['points']:
            values={tag:str(group.get(tag,'')) for tag in tags}
            values['mounting_wall_handle']=str(p.get('mounting_wall_handle',''))
            values['room_source_handles']=','.join(group['room_source_handles']);values['lamp_id']=p['id'];values['state']='INVALID' if stale else 'CANDIDATE'
            entity=doc.modelspace().add_blockref('CST_LIGHT_CANDIDATE',(p['x'],p['y'],p['z']),dxfattribs={'layer':'CST_LIGHT_INVALID' if stale else 'CST_LIGHT_CANDIDATE'})
            entity.add_auto_attribs(values)
            entity.set_xdata('CST_TRACE',[(1000,k+'='+v) for k,v in values.items()])
            invalid+=int(stale);count+=int(not stale)
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);doc.saveas(path)
    return {'output':path.as_posix(),'candidate_count':count,'invalid_count':invalid,'units':'mm','source_modified':False}


def lights(directory,output=None,mode='auto'):
    folder=Path(output) if output else Path('dist/lighting')/Path(directory).name
    folder.mkdir(parents=True,exist_ok=True);result=generate_directory(directory,mode)
    (folder/'lighting_candidates.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    exported=write_dxf(result,folder/'lighting_candidates.dxf')
    return exported|{'rooms':len(result['groups']),'point_count':result['point_count'],'json':(folder/'lighting_candidates.json').as_posix(),'title':TITLE,
                     'manual_rooms':[g['room_name'] for g in result['groups'] if not g['points']]}


def compare_groups(old,new,mapping,changes):
    current={g['room_semantic_id']:g for g in new['groups']};changed={}
    for c in changes:
        if c['old']:changed.setdefault(c['old']['id'],[]).extend(c['kinds'])
    rows=[];used=set();stale=[]
    for group in old['groups']:
        rid=group['room_semantic_id'];nid=mapping.get(rid);ng=current.get(nid);used.add(nid)
        types=changed.get(rid,[])
        def positions(g):
            # 灯ID包含本次快照身份，不能拿编号判定灯位变化。
            return sorted((round(p['x'],3),round(p['y'],3),round(p.get('z',0),3)) if 'x' in p else (p['id'],) for p in g['points'])
        rule_changed=ng is not None and any(group.get(k)!=ng.get(k) for k in ('rule_id','rule_version','strategy'))
        altered=ng is None or bool(set(types)-{'来源对象变化','输入状态变化'}) or rule_changed or positions(group)!=positions(ng)
        state='旧灯组失效，已按新轮廓重生成' if altered and ng and ng['points'] else '旧灯组失效，需人工重新布置' if altered else '保留候选灯组'
        reason='房间几何变化' if '几何变化' in types else '房间删除、来源/用途变化或布点规则变化' if altered else '候选位置与规则一致；换版来源重新绑定，灯位未改变'
        if not group['points'] and (not ng or not ng['points']):state='仍需人工布置';reason='两版均无可生成候选灯组'
        if altered and group['points']:stale.append({**group,'state':'失效','invalidation_reason':reason})
        rows.append({'old_room_id':rid,'new_room_id':nid,'room_name':group['room_name'],'state':state,'reason':reason,
            'old_group_id':group['group_id'],'new_group_id':ng['group_id'] if ng else None,
            'old_count':len(group['points']),'new_count':len(ng['points']) if ng else 0,
            'old_source_handles':group['room_source_handles'],'new_source_handles':ng['room_source_handles'] if ng else []})
    for rid,g in current.items():
        if rid not in used:rows.append({'new_room_id':rid,'room_name':g['room_name'],'state':'新增候选灯组' if g['points'] else '需人工布置','reason':g['reason'],'new_count':len(g['points']),'new_group_id':g['group_id']})
    new['invalidated_groups']=stale
    return rows
