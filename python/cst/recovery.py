# SPDX-License-Identifier: MPL-2.0
"""有界漏房实验：复用L1墙/混凝土边界，仅重建指定房名，不覆盖原扫描。"""
import hashlib
import json
import math
import tempfile
from html import escape
from pathlib import Path
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union, polygonize_full
from shapely.strtree import STRtree
from .model import load, L1, L2, L3, GeometryFact, SemanticObject
from .sanitize import sanitize

METHOD='python_wall_polygonize_vertices_5mm_geos_noding_v1'
ROOT=Path(__file__).resolve().parents[2]


def identity(prefix,value):
    return prefix+hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()[:24]


def label_rows(data):
    rows={}
    for f in data.facts:
        if not f.raw_text or f.source.normalized_layer!='A-Spac-Iden-Auto' or not f.geometry.bounds.is_valid:continue
        b=f.geometry.bounds;x=(b.min_x+b.max_x)/2;y=(b.min_y+b.max_y)/2
        rows.setdefault((f.raw_text,round(x,3),round(y,3)),(f,x,y))
    return list(rows.values())


def wall_lines(l1,ox,oy,radius):
    rows=[];max_shift=0.0
    for p in l1.primitives:
        g=p.raw_geometry;b=g.bounds;s=p.source
        if not b.is_valid or not g.is_exact or p.raw_properties.get('xclip_visibility')=='hidden':continue
        wall=p.is_semantic_candidate and p.adapter_role_hint=='Wall' and s.native_class_name in ('TDbWall','TDbCurtainWall')
        concrete=s.native_class_name=='AcDbHatch' and s.normalized_layer=='S-PATT-WALL' and p.raw_properties.get('hatch_pattern_name')=='钢筋混凝土'
        if not (wall or concrete) or b.max_x<ox-radius or b.min_x>ox+radius or b.max_y<oy-radius or b.min_y>oy+radius:continue
        for path in g.paths:
            coords=[]
            for q in path:
                x=round(q.x/5)*5-ox;y=round(q.y/5)*5-oy
                max_shift=max(max_shift,math.hypot(x-(q.x-ox),y-(q.y-oy)))
                coords.append((x,y))
            for a,z in zip(coords,coords[1:]):
                if a!=z:rows.append((p,LineString([a,z])))
    return rows,max_shift


def opening_closures(l1,wall_rows,ox,oy,radius):
    # 仅复用源开口直线，沿用原C#的墙端跨度/双侧墙返及延续条件。
    network=unary_union([line for _,line in wall_rows]);neighbors={}
    key=lambda xy:tuple(round(v,5) for v in xy)
    for line in network.geoms if hasattr(network,'geoms') else [network]:
        coords=list(line.coords)
        for a,b in zip(coords,coords[1:]):
            a,b=key(a),key(b);neighbors.setdefault(a,set()).add(b);neighbors.setdefault(b,set()).add(a)
    def straight(coords):
        if len(coords)<2 or coords[0]==coords[-1]:return False
        a,b=coords[0],coords[-1];dx,dy=b[0]-a[0],b[1]-a[1]
        return all(abs((q[0]-a[0])*dy-(q[1]-a[1])*dx)<.01 for q in coords[1:-1])
    def return_continues(a,b,span,start):
        if b not in neighbors.get(a,set()):return False
        for q in neighbors[a]-{b}:
            dx,dy=q[0]-a[0],q[1]-a[1];cross=dx*span[1]-dy*span[0];dot=dx*span[0]+dy*span[1]
            if abs(cross)<.01 and (dot<0 if start else dot>0):return True
        return False
    result=[]
    for p in l1.primitives:
        g=p.raw_geometry;b=g.bounds
        if not p.is_semantic_candidate or p.adapter_role_hint!='Opening' or p.source.native_class_name!='TDbOpening' or not g.is_exact or not b.is_valid or p.raw_properties.get('xclip_visibility')=='hidden':continue
        if b.max_x<ox-radius or b.min_x>ox+radius or b.max_y<oy-radius or b.min_y>oy+radius:continue
        paths=[]
        for path in g.paths:
            coords=[(round(q.x/5)*5-ox,round(q.y/5)*5-oy) for q in path]
            if straight(coords):paths.append(coords)
        accepted={i for i,path in enumerate(paths) if len(neighbors.get(path[0],set()))==1 and len(neighbors.get(path[-1],set()))==1}
        matches={i:[] for i in range(len(paths))}
        for i,pa in enumerate(paths):
            for j in range(i+1,len(paths)):
                a,b=pa[0],pa[-1];span=(b[0]-a[0],b[1]-a[1])
                for pb in [paths[j],list(reversed(paths[j]))]:
                    c,d=pb[0],pb[-1]
                    if (d[0]-c[0],d[1]-c[1])!=span or abs((c[0]-a[0])*span[1]-(c[1]-a[1])*span[0])<.01:continue
                    if all([return_continues(a,c,span,True),return_continues(c,a,span,True),return_continues(b,d,span,False),return_continues(d,b,span,False)]):matches[i].append(j);matches[j].append(i);break
        for i,matched in matches.items():
            if len(matched)==1 and matches[matched[0]]==[i]:accepted.add(i)
        for i in sorted(accepted):result.append((p,LineString(paths[i])))
    return result


def reconstruct(l1,l2,l3,name,radius=20000,handle=None,general=False):
    import yaml
    from .uses import classify_name, DEFAULT_TABLE
    table=yaml.safe_load(DEFAULT_TABLE.read_text(encoding='utf-8'))
    if not general and (not table.get('approved') or classify_name(name,table)['category'] not in ('SUBSTATION','DISTRIBUTION_ROOM')):raise ValueError('本次实验仅覆盖已批准词表中的变配电房，不推断其他房间用途')
    matches=[r for r in label_rows(l2) if r[0].raw_text==name and (handle is None or r[0].source.handle==handle)]
    if len(matches)!=1:raise ValueError(name+'：房名未找到或存在多处位置，不能按名称强行匹配；请使用未删去该房名的原始JSON')
    label,x,y=matches[0]
    if any(o.type in ('space','shaft','zone') and (o.source.handle==label.source.handle or any(e.kind=='spatial_text' and e.source_handle==label.source.handle for e in o.evidence)) for o in l3.objects):raise ValueError(name+'：已有空间，不重复补提取')
    ox=math.floor(x/5)*5;oy=math.floor(y/5)*5;point=Point(x-ox,y-oy)
    rows,max_shift=wall_lines(l1,ox,oy,radius)
    if not rows:raise ValueError(name+'：缺少可用墙边界')
    network=unary_union([line for _,line in rows]);polygons,cuts,dangles,invalid=polygonize_full(network)
    hits=[p for p in polygons.geoms if p.contains(point) and 2e6<=p.area<=500e6]
    used_openings=[];method=METHOD
    if general and len(hits)!=1:
        used_openings=opening_closures(l1,rows,ox,oy,radius)
        if used_openings:
            rows+=used_openings;network=unary_union([line for _,line in rows]);polygons,cuts,dangles,invalid=polygonize_full(network)
            hits=[p for p in polygons.geoms if p.contains(point) and 2e6<=p.area<=500e6]
            method=METHOD+'+supported_opening_v1'
    if len(hits)!=1:raise ValueError(name+'：未得到唯一2～500平方米围合，不补墙或移动文字')
    poly=hits[0]
    if poly.interiors:raise ValueError(name+'：轮廓有内孔，当前实验不忽略内孔生成房间')
    if not box(-radius,-radius,radius,radius).contains(poly):raise ValueError(name+'：围合超出局部检索范围，不能截断当房间')
    contained=[f.raw_text for f,lx,ly in label_rows(l2) if poly.contains(Point(lx-ox,ly-oy))]
    if contained!=[name]:raise ValueError(name+'：围合内有多个房名，不强行合并：'+','.join(contained))
    for existing in l3.objects:
        if existing.type not in ('space','shaft','zone') or not existing.geometry.is_closed or not existing.geometry.paths:continue
        shape=Polygon([(q.x-ox,q.y-oy) for q in existing.geometry.paths[0]])
        if shape.is_valid and poly.intersection(shape).area>max(500000,poly.area*.01):raise ValueError(name+'：候选与已有房间明显重叠，不覆盖原结果：'+existing.raw_label)
    tree=STRtree([line for _,line in rows]);supported={}
    coverage=[]
    for i in tree.query(poly.boundary.buffer(.01)):
        primitive,line=rows[int(i)]
        if poly.boundary.intersection(line.buffer(.01)).length>.1:
            supported[primitive.primitive_id]=primitive;coverage.append(line)
    unsupported=poly.boundary.difference(unary_union(coverage).buffer(.02)).length if coverage else poly.length
    if unsupported>.1:raise ValueError(name+'：部分边界找不到源墙证据，不生成空间')
    wcs=[{'x':round(px+ox,3),'y':round(py+oy,3),'z':0.0} for px,py in list(poly.exterior.coords)[:-1]]
    polygon=Polygon([(v['x']-ox,v['y']-oy) for v in wcs]);minx,miny,maxx,maxy=polygon.bounds
    source_ids=sorted(supported);first=supported[source_ids[0]]
    gid=identity('geometry_recovery_',[l3.drawing.sha256,label.source.stable_path,method,wcs])
    sid=identity('sem_recovery_',[gid,label.source.stable_path])
    geometry={'kind':'polygon','is_closed':True,'is_exact':False,'extraction_method':method,'paths':[wcs],
        'bounds':{'min_x':minx+ox,'min_y':miny+oy,'min_z':0.0,'max_x':maxx+ox,'max_y':maxy+oy,'max_z':0.0,'is_valid':True}}
    source=first.source.model_dump();source.update(stable_path='derived:python-room-recovery/'+gid,raw_layer='__DERIVED__',effective_layer='__DERIVED__',normalized_layer='DERIVED-RECOVERED-ROOM',native_dxf_name='DERIVED',native_class_name='PythonRecoveredWallRegion',block_path=[],xref_path=[],xref_hashes=[],wcs_transform=[1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.])
    center=polygon.representative_point()
    fact=GeometryFact.model_validate({'geometry_id':gid,'compatibility_fact_id':gid,'source_primitive_ids':source_ids,
        'feature_kind':'closed_region','adapter_role_hint':'Space','is_semantic_candidate':True,'source':source,'geometry':geometry,
        'measurements':{'length_millimeters':polygon.length,'area_square_millimeters':polygon.area,'area_is_available':True,'area_method':method,
            'width_millimeters':maxx-minx,'height_millimeters':maxy-miny,'representative_point_wcs_millimeters':{'x':center.x+ox,'y':center.y+oy,'z':0.0}},
        'raw_text':'','extraction_confidence':0.0,'raw_properties':{'derived_geometry':method,'snap_tolerance_millimeters':'5','confidence_note':'未校准，不作识别正确率'},'evidence':[], 'reason_codes':['PYTHON_RECOVERED_SPACE']})
    obj=SemanticObject.model_validate({'semantic_id':sid,'type':'space','classification':'','raw_label':name,
        'use_code':('ELECTRICAL_ROOM' if classify_name(name,table)['category'] in ('SUBSTATION','DISTRIBUTION_ROOM','WEAK_CURRENT_ROOM','SMALL_ELECTRICAL_ROOM') else next(iter({o.use_code for o in l3.objects if o.type=='space' and o.raw_label==name}), 'UNKNOWN') if len({o.use_code for o in l3.objects if o.type=='space' and o.raw_label==name})<=1 else 'UNKNOWN'),'status':'review','confidence':0.0,'source':label.source.model_dump(),'geometry':geometry,
        'evidence':[{'code':'GEOMETRY_FACT_SOURCE','kind':'geometry_fact','value':gid,'source_handle':first.source.handle,'weight':0.0},
                    {'code':'ROOM_LABEL_CONTAINED_TEXT','kind':'spatial_text','value':name,'source_handle':label.source.handle,'weight':0.0},
                    {'code':'RECOVERED_WALL_NETWORK','kind':'geometry_topology','value':method,'source_handle':first.source.handle,'weight':0.0}],
        'reason_codes':['PYTHON_RECOVERED_SPACE','LOW_CONFIDENCE']})
    report={'room_name':name,'object_id':sid,'text_handle':label.source.handle,'text_point_wcs_mm':[x,y],
        'text_moved':False,'area_m2':round(polygon.area/1e6,3),'source_handles':sorted({p.source.handle for p in supported.values()}),
        'boundary_source_count':len(supported),'boundary_unsupported_length_mm':round(unsupported,6),
        'max_vertex_snap_shift_mm':round(max_shift,6),'added_wall_segments':0,'source_opening_paths_used':bool(used_openings), 'opening_boundary_handles':sorted({p.source.handle for p,line in used_openings if p.primitive_id in supported}),
        'holes':0,'contained_names':contained,'method':method,'status':'程序补提取；轮廓待工程师核对',
        'root_cause_evidence':'原L2无包含房名的可用围合；同一L1墙/混凝土边界经GEOS相交分割及多边形化得到唯一轮廓。不等同已定位原C#内部唯一故障点。'}
    return fact,obj,report,rows,poly,(ox,oy),point


def diagnostic_html(report,rows,poly,origin,point,path):
    minx,miny,maxx,maxy=poly.bounds;padding=3500;vx=(minx-padding)/1000;vy=-(maxy+padding)/1000;w=(maxx-minx+padding*2)/1000;h=(maxy-miny+padding*2)/1000
    def draw(coords):return 'M'+'L'.join(f'{x/1000:.5f},{-y/1000:.5f}' for x,y in coords)
    raw=''.join('<path d="'+draw(list(line.coords))+'"/>' for _,line in rows)
    sources='、'.join(report['source_handles']);name=escape(report['room_name'])
    html=f'''<!doctype html><meta charset="utf-8"><title>{name} · 漏房实验</title><style>body{{font:16px "Microsoft YaHei",sans-serif;margin:24px;color:#183843}}svg{{width:100%;height:75vh;background:#f8fafb}}.walls{{fill:none;stroke:#8b9fa8;stroke-width:.6;vector-effect:non-scaling-stroke}}.room{{fill:#b77be845;stroke:#ae41a4;stroke-width:2;vector-effect:non-scaling-stroke}}text{{font-size:.4px;fill:#c52338}}</style><h2>{name}：用原墙边界重新形成围合</h2><p>紫色：重建轮廓；红点：程序原有房名定位点，未移动；灰线：原L1墙和混凝土填充边界。面积{report['area_m2']}㎡，未添加墙段。</p><svg viewBox="{vx} {vy} {w} {h}"><g class="walls">{raw}</g><path class="room" d="{draw(list(poly.exterior.coords))}"/><circle cx="{point.x/1000}" cy="{-point.y/1000}" r=".18" fill="#e03948"/><text x="{point.x/1000+.3}" y="{-point.y/1000}">房名定位点 · {report['text_handle']}</text></svg><p>边界来源Handle：{escape(sources)}</p><p>这是程序补提取实验，不是AI绘制；原扫描保留。轮廓和实际房间是否一致，仍需看图核对。</p>'''
    Path(path).write_text(html,encoding='utf-8')


def recover(directory,names,output,public_label,baseline=None,all_unresolved=False):
    if not names and not all_unresolved:raise ValueError('请指定--room房名或--all-unresolved')
    directory=Path(directory);output=Path(output)
    if not output.resolve().is_relative_to(ROOT/'dist') or output.resolve()==directory.resolve():raise ValueError('实验输出放在本仓库dist，不能覆盖原扫描或冻结样例')
    if public_label not in ('A','B'):raise ValueError('公开样例代号用A或B')
    l1,l2,l3=load(directory,L1),load(directory,L2),load(directory,L3)
    if l3.status=='failed' or any(s.drawing.geometry_units!='mm' for s in (l1,l2,l3)):raise ValueError('扫描失败或非毫米数据，不能猜测补全')
    if len({s.drawing.sha256.upper() for s in (l1,l2,l3)})!=1:raise ValueError('三层输入来源不一致')
    original_ids={o.semantic_id for o in l3.objects};reports=[];pictures=[];issues=[]
    targets=[(name,None) for name in dict.fromkeys(names)]
    if all_unresolved:
        from .room_diagnostics import targets_and_issues
        targets,issues=targets_and_issues(l1,l2,l3)
    for name,handle in targets:
        try:
            fact,obj,report,rows,poly,origin,point=reconstruct(l1,l2,l3,name,handle=handle,general=all_unresolved)
        except ValueError as error:
            if not all_unresolved:raise
            from .room_diagnostics import diagnose_label
            issues.append(diagnose_label(l1,l2,l3,name,handle,str(error)))
            continue
        l2.facts.append(fact);l3.objects.append(obj);reports.append(report);pictures.append((report,rows,poly,origin,point))
        for finding in l3.findings:
            if finding.reason_code=='KNOWN_SPACE_LABEL_UNRESOLVED' and finding.source_handle==report['text_handle']:
                finding.reason_code='SPACE_RECOVERED_CANDIDATE';finding.semantic_id=obj.semantic_id;finding.message=name+'：本次程序补提取候选围合，轮廓待核对；原扫描未解析记录见源输入。'
    l2.deterministic_hash_algorithm='cst-recovery-v1:original-digest+added-geometries'
    for model,new_ids in [(l2,[r['object_id'] for r in reports]),(l3,[r['object_id'] for r in reports])]:
        model.deterministic_content_hash=hashlib.sha256(json.dumps([model.deterministic_content_hash,METHOD,new_ids],sort_keys=True,separators=(',',':')).encode()).hexdigest()
        model.producer='cad-semantic-trace.python-recovery';model.producer_version='0.3.0-dev';model.producer_binary_sha256=''
    # 原扫描时间/完整性作为输入记录保留；派生来源、算法与输入文件摘要记在补提取清单。
    local=ROOT/'.local';local.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='room-recovery-',dir=local) as temporary:
        temp=Path(temporary)
        for model,filename in [(l1,'cad-primitives.v1.json'),(l2,'building-geometry.v1.json'),(l3,'building-semantics.v1.json')]:
            (temp/filename).write_text(model.model_dump_json(),encoding='utf-8')
        manifest=sanitize(temp,output,public_label,allowed_labels={r['room_name'] for r in issues})
    inherited=False
    if baseline and (Path(baseline)/'l4_confirmations.yaml').is_file():
        import yaml
        prior=load(baseline);now=load(output);current={o.semantic_id:o for o in now.objects}
        if prior.drawing.sha256.upper()!=now.drawing.sha256.upper() or set(current)!=original_ids|{r['object_id'] for r in reports}:raise ValueError('基线来源不对应，不能继承确认')
        if not all(o.model_dump()==current.get(o.semantic_id).model_dump() for o in prior.objects):raise ValueError('原有对象发生变化，不能继承确认')
        record=yaml.safe_load((Path(baseline)/'l4_confirmations.yaml').read_text(encoding='utf-8'))
        prior_file=Path(baseline)/'building-semantics.v1.json.gz'
        if not prior_file.is_file():prior_file=prior_file.with_suffix('')
        if record['snapshot_sha256']!=hashlib.sha256(prior_file.read_bytes()).hexdigest() or record['drawing_sha256'].upper()!=now.drawing.sha256.upper():raise ValueError('原确认与基线不对应')
        record['snapshot_sha256']=hashlib.sha256((output/'building-semantics.v1.json.gz').read_bytes()).hexdigest()
        (output/'l4_confirmations.yaml').write_text(yaml.safe_dump(record,allow_unicode=True,sort_keys=False),encoding='utf-8');inherited=True
    if not inherited and (output/'l4_confirmations.yaml').is_file():(output/'l4_confirmations.yaml').unlink()
    for picture in pictures:diagnostic_html(*picture,output/(picture[0]['text_handle']+'-diagnostic.html'))
    manifest['recovery']={'input_files_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for name in ('cad-primitives.v1.json','building-geometry.v1.json','building-semantics.v1.json') for p in [directory/name if (directory/name).is_file() else directory/(name+'.gz')]},'method':METHOD,'original_object_count':len(original_ids),'added_spaces':len(reports),'original_objects_unchanged':True,
        'inherited_existing_confirmations':inherited,'new_rooms_engineer_reviewed':False,'source_metadata_scope':'原扫描时间、原图哈希与完整性记录继承自输入；派生生产者不是原插件；未启动CAD或改DWG'}
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    result={'output':output.as_posix(),'method':METHOD,'rooms':reports,'inherited_existing_confirmations':inherited,
        'note':'补提取原未解析房名的候选围合；原扫描不改，不自动创建出入口关系；净长/出口及轮廓需工程核对'}
    (output/'recovery.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    from .verify import verify
    checked=verify(output)
    (output/'verify.json').write_text(json.dumps(checked,ensure_ascii=False,indent=2),encoding='utf-8')
    if checked['failure_count']:raise ValueError('补提取包证据断链，见verify.json')
    if all_unresolved:
        from .room_diagnostics import write_issues
        result['diagnostics']=write_issues(output,issues,reports)
    return result
