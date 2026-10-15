# SPDX-License-Identifier: MPL-2.0
"""真实JSON离线SVG查看器，WCS仅平移/缩放显示，不修改源数据。"""
import json
import math
from html import escape
from pathlib import Path
from .model import load,L1,L2
from .uses import classify
from .gold import area_m2
from .l4 import check,evidence_chain

COLORS={'SUBSTATION':'#b77be8','DISTRIBUTION_ROOM':'#efb14c','ELECTRICAL_SHAFT':'#f16c8f',
        'WEAK_CURRENT_ROOM':'#60a6eb','SMALL_ELECTRICAL_ROOM':'#7bc6a8','NOT_INCLUDED':'#99c7cd','EXCLUDED':'#c5cbd0'}


def write_view(directory,output=None,generated=None,changes=None,review=None,issues=None):
    directory=Path(directory);data=load(directory);l2=load(directory,L2);l1=load(directory,L1)
    if data.drawing.geometry_units!='mm':raise ValueError('查看器当前支持毫米WCS数据，请先核对单位')
    facts={f.geometry_id:f for f in l2.facts};primitives={p.primitive_id:p for p in l1.primitives}
    from .references import ReferenceIndex
    reference_index=ReferenceIndex(l1,l2)
    classes={r['object_id']:r for r in (json.loads((directory/'classifications.json').read_bytes()) if (directory/'bundle-manifest.json').is_file() else classify(directory))['rows']};results=json.loads((directory/'findings.json').read_bytes()) if (directory/'bundle-manifest.json').is_file() else check(directory)
    for f in results['findings']:
        if f['engineer_reviewed']['record_file']:f['engineer_reviewed']['record_file']='l4_confirmations.yaml'
    visible=[o for o in data.objects if o.type in ('space','shaft','zone','opening','door','window')]
    all_geometries=[p.raw_geometry for p in l1.primitives]+[f.geometry for f in l2.facts]
    coords=[(p.x,p.y) for g in all_geometries for path in g.paths for p in path]
    if not coords:coords=[(p.x,p.y) for o in visible for path in o.geometry.paths for p in path]
    if not coords:raise ValueError('JSON没有可显示的二维路径')
    # 显示原点取工程房间附近，避免原始几何中的远端/零点令浏览器浮点精度退化。
    reference=next((o for o in visible if o.type=='space' and classes.get(o.semantic_id,{}).get('category') in ('SUBSTATION','DISTRIBUTION_ROOM') and o.geometry.paths),None)
    if reference is None:reference=next((o for o in visible if o.type=='space' and o.geometry.paths),None)
    origin_points=[(p.x,p.y) for path in reference.geometry.paths for p in path] if reference else coords
    ox=min(x for x,y in origin_points);oy=min(y for x,y in origin_points)
    def xy(x,y):return ((x-ox)/1000,-(y-oy)/1000)
    def paths(geometry):
        parts=[]
        for path in geometry.paths:
            if not path:continue
            points=[xy(p.x,p.y) for p in path]
            parts.append('M'+'L'.join(f'{x:.3f},{y:.3f}' for x,y in points)+('Z' if geometry.is_closed else ''))
        return ''.join(parts)
    def bounds(g):
        b=g.bounds
        return [*xy(b.min_x,b.max_y),(b.max_x-b.min_x)/1000,(b.max_y-b.min_y)/1000] if b.is_valid else None
    raw=[];seen=set();raw_geometry_count=0;missing_geometry=0
    for g in all_geometries:
        text=paths(g)
        if not text:missing_geometry+=1;continue
        raw_geometry_count+=1
        if text in seen:continue
        seen.add(text);raw.append(text)
    gray=''.join('<path d="'+''.join(raw[i:i+1000])+'"/>' for i in range(0,len(raw),1000))
    text_marks=[]
    for f in l2.facts:
        if f.raw_text:
            p=f.measurements.representative_point_wcs_millimeters;x,y=xy(p.x,p.y)
            text_marks.append(f'<path d="M{x-.08:.3f},{y:.3f}h.16M{x:.3f},{y-.08:.3f}v.16"/>')
    gray+=''.join(text_marks)
    svg=[];records={};room_options=[]
    delta=json.loads(Path(changes).read_bytes()) if changes else None
    if delta and delta['new_hash']!=data.drawing.sha256:raise ValueError('变更图不对应当前扫描')
    revised={r.get('new_group_id') for r in delta.get('lighting_changes',[]) if r.get('state')!='保留候选灯组'} if delta else set()
    by_room={}
    for f in results['findings']:
        for id in f['object_ids']:by_room.setdefault(id,[]).append(f)
    for f in results['findings']:
        for row in f['values'].get('opening_candidate_audit',[]):
            for id in row['object_ids']:by_room.setdefault(id,[]).append(f)
    label_boxes=[]
    for o in visible:
        cls=classes.get(o.semantic_id,{});fs=by_room.get(o.semantic_id,[]);id=o.semantic_id
        handles=sorted({o.source.handle,*[e.source_handle for e in o.evidence if e.source_handle]})
        b=bounds(o.geometry);path=paths(o.geometry)
        if b:x,y=b[0]+b[2]/2,b[1]+b[3]/2
        else:x=y=None
        if o.geometry.is_closed and o.geometry.paths:
            from shapely.geometry import Polygon
            polygon=Polygon([(p.x,p.y) for p in o.geometry.paths[0]])
            if polygon.is_valid:
                label_point=polygon.representative_point();x,y=xy(label_point.x,label_point.y)
        area=area_m2(o,facts)
        refs=[facts[e.value] for e in o.evidence if e.kind=='geometry_fact' and e.value in facts]
        records[id]={'semantic_id':id,'房名':o.raw_label,'类型':o.type,'L4分类':('建筑围合' if o.geometry.extraction_method.startswith('python_wall_polygonize') and cls.get('category')=='NOT_INCLUDED' else cls.get('label','区域对象' if o.type=='zone' else '门窗候选')),
            '二级用途':cls.get('secondary_label','') or (o.raw_label if o.geometry.extraction_method.startswith('python_wall_polygonize') and cls.get('category')=='NOT_INCLUDED' else ''),'L3用途':o.use_code,'状态':o.status,'L2面积(m²)':area or None,
            '源Handle列表':handles,'外层块Handle':o.source.block_path[0].split(':')[0] if o.source.block_path else None,
            '定位字段':reference_index.for_object(o),'source':o.source.model_dump(),'geometry':{'kind':o.geometry.kind,'is_closed':o.geometry.is_closed,
                'is_exact':o.geometry.is_exact,'extraction_method':o.geometry.extraction_method},
            '证据链':evidence_chain(o,facts,primitives),'L2测量':[{'geometry_id':f.geometry_id,**f.measurements.model_dump()} for f in refs],
            '门洞候选清洗':[f['values'] for f in fs if f['rule_id']=='R1'],
            '工程师确认':[f['engineer_reviewed'] for f in fs if f['engineer_reviewed']['reviewed_by']],
            '适用规则结果':fs,'生成对象':[],'view_bounds':b}
        if o.type in ('space','shaft','zone'):
            color=COLORS.get(cls.get('category'),'#b4c9d5');room_options.append({'id':id,'name':o.raw_label,'type':o.type,'category':cls.get('category'),'bounds':b})
            if path:
                svg.append(f'<g class="room" data-id="{id}" tabindex="0" role="button" aria-label="{escape(o.raw_label,quote=True)}">'
                           f'<path d="{path}" fill="{color}" class="room-fill"/>'
                           +(f'<path d="{path}" fill="url(#review)" class="hatch"/>' if o.status=='review' else '')
                           +f'<path d="{path}" fill="none" class="outline"/></g>')
            if x is not None:
                # 同一轮廓的Space/Shaft可能重叠，按屏幕文本包围范围避让。
                label=escape(o.raw_label);area_label=f'{area:.1f} m²' if isinstance(area,(int,float)) else '面积资料缺失'
                for _ in range(12):
                    width=max(len(o.raw_label)*.45,2)
                    box=(x-width/2,y-.45,x+width/2,y+.8)
                    if not any(box[0]<q[2] and box[2]>q[0] and box[1]<q[3] and box[3]>q[1] for q in label_boxes):break
                    y+=1.35
                label_boxes.append(box)
                svg.append(f'<text class="label" x="{x:.3f}" y="{y:.3f}">{label}<tspan x="{x:.3f}" dy=".65">{area_label}</tspan></text>')
                if o.type=='shaft':svg.append(f'<rect class="shaft-box" data-id="{id}" x="{b[0]:.3f}" y="{b[1]:.3f}" width="{b[2]:.3f}" height="{b[3]:.3f}"/>')
        elif x is not None:
            svg.append(f'<circle class="door" data-id="{id}" cx="{x:.3f}" cy="{y:.3f}" r=".22" tabindex="0" role="button" aria-label="门洞 {escape(o.source.handle)}"/>')
    generated_path=Path(generated) if generated else directory/'lighting_candidates.json'
    from .lighting import generate_directory,input_hash
    lamps=json.loads(generated_path.read_text(encoding='utf-8-sig')) if generated_path.is_file() else generate_directory(directory)
    if lamps.get('input_sha256')!=input_hash(directory):raise ValueError('灯具候选对应其他扫描；请重新运行lights，或不指定旧候选文件')
    from .light_calc import calculate
    calculations=json.loads((directory/'lighting_calculations.json').read_bytes()) if (directory/'bundle-manifest.json').is_file() and (directory/'lighting_calculations.json').is_file() else calculate(data,classes,lamps)
    calculations={r['room_semantic_id']:r for r in calculations['rows']}
    for rid,calculation in calculations.items():
        if rid in records:records[rid]['照度计算']=calculation
    if lamps:
        for group in [*lamps.get('groups',[]),*lamps.get('invalidated_groups',[])]:
            stale=group.get('state')=='失效'
            rid=group['room_semantic_id']
            if rid in records:records[rid]['生成对象'].append({k:v for k,v in group.items() if k!='points'})
            for lamp in group.get('points',[]):
                id=('invalid_'+lamp['id']) if stale else lamp['id'];x,y=xy(lamp['x'],lamp['y'])
                records[id]={'生成对象':lamp,'生成依据':{k:v for k,v in group.items() if k!='points'},'房间':rid,
                    'semantic_id':id,'房名':'旧灯具候选（失效）' if stale else '灯具布置候选','类型':'generated_light','状态':'失效' if stale else '演示候选',
                    '定位字段':dict(records.get(rid,{}).get('定位字段',{}),generated_id=id,generated_id_type='生成灯具ID（非CAD原图Handle）',mounting_wall_handle=lamp.get('mounting_wall_handle')),'source':group['room_source'],'外层块Handle':group['room_source']['block_path'][0].split(':')[0] if group['room_source']['block_path'] else None,
                    'L2面积(m²)':records.get(rid,{}).get('L2面积(m²)'),
                    '源Handle列表':group['room_source_handles'],'证据链':records.get(rid,{}).get('证据链'),
                    'view_bounds':[x-.4,y-.4,.8,.8]}
                svg.append(f'<g class="lamp {"invalid" if stale else "revised" if group["group_id"] in revised else ""}" data-room="{rid}" data-id="{id}" tabindex="0" role="button" aria-label="灯具布置候选"><circle cx="{x:.3f}" cy="{y:.3f}" r=".15"/><path d="M{x-.10:.3f},{y-.10:.3f}l.20,.20M{x+.10:.3f},{y-.10:.3f}l-.20,.20"/></g>')
    if delta and review:
        reviewed=json.loads(Path(review).read_text(encoding='utf-8'))
        if (reviewed['old_hash'],reviewed['new_hash'])!=(delta['old_hash'],delta['new_hash']):raise ValueError('修改记录对照不对应这两版扫描；请使用对应记录或不加--review')
        delta['engineer_comparison']=reviewed
    if delta:
        from .model import Geometry
        for c in delta['changes']:
            id=c['id'];reference=c['new'] or c['old']
            b=None
            for side in ('old','new'):
                if c.get(side+'_geometry'):
                    g=Geometry.model_validate(c[side+'_geometry']);d=paths(g);b=bounds(g) or b
                    state='deleted' if side=='old' else 'added' if not c['old'] else 'modified'
                    svg.append(f'<path class="change-shape {state} {"derived" if c.get("basis","").startswith("派生") else ""}" data-kind="{reference["type"]}" d="{d}" data-id="{id}"/>')
            if b:
                records[id]={'semantic_id':id,'房名':reference['name'] or reference['type'],'类型':'change','状态':'变化候选',
                    '源Handle列表':[reference['handle']],'source':{'handle':reference['handle']},'view_bounds':b,'变更':c}
                room_options.append({'id':id,'name':'变更 · '+(reference['name'] or reference['type']),'type':'change','category':'CHANGE','bounds':b})
        for row in delta['review_inheritance']:
            if row['state']=='继承':continue
            o=records.get(row.get('new_room')) or records.get(row.get('old_room'))
            if o:
                source_obj=next((q for q in visible if q.semantic_id==o['semantic_id']),None)
                if source_obj:svg.append('<path class="confirmation-invalid change-shape" d="'+paths(source_obj.geometry)+'"/>')
    if delta:
        # 按已输出的影响关联展示门位；不改对象匹配，也不强配删门/新门为同一实体。
        related={}
        for c in delta['changes']:
            ref=c['new'] or c['old']
            if ref['type'] not in ('opening','door','window'):continue
            for room in c['impact']['rooms']:
                related.setdefault(room['id'],[]).append(c)
        for id,o in records.items():
            c=o.get('变更');keys={id}
            if c and (c['new'] or c['old'])['type']=='space':
                keys.update(q['id'] for q in (c['old'],c['new']) if q)
            else:
                for q in delta['changes']:
                    if q['new'] and q['new']['id']==id and q['old']:keys.add(q['old']['id'])
            rows={}
            for key in keys:
                for q in related.get(key,[]):
                    ref=q['new'] or q['old'];tag=(tuple(q['kinds']),ref['handle'],tuple(tuple(b) for b in q['cloud_bounds']))
                    if tag not in rows:rows[tag]={'change_id':q['id'],'kinds':q['kinds'],
                        'old_handle':(q['old'] or {}).get('handle'),'new_handle':(q['new'] or {}).get('handle'),
                        'type':ref['type'],'expression_count':0}
                    rows[tag]['expression_count']+=1
            if rows:o['门窗变更']=list(rows.values())
    issue_path=Path(issues) if issues else directory/'room_issues.json'
    if issue_path.is_file():
        import hashlib
        issues=json.loads(issue_path.read_text(encoding='utf-8-sig'))
        snapshot=directory/'building-semantics.v1.json.gz'
        if not snapshot.is_file():snapshot=snapshot.with_suffix('')
        if issues.get('snapshot_sha256')!=hashlib.sha256(snapshot.read_bytes()).hexdigest():raise ValueError('房名诊断不对应当前扫描，请重新运行recover --all-unresolved')
        for row in issues['issues']:
            id=row['id'];x,y=xy(*row['point_wcs_mm']);issue_points=[(x-2,y-2),(x+2,y+2)]
            for gap in row['gap_candidates']:issue_points.extend([xy(*gap['a_wcs_mm']),xy(*gap['b_wcs_mm'])])
            if row['text_position_candidate']:issue_points.extend(xy(*p) for p in row['text_position_candidate']['outline_wcs_mm'])
            minx=min(a for a,bxy in issue_points);miny=min(bxy for a,bxy in issue_points)
            b=[minx,miny,max(a for a,bxy in issue_points)-minx,max(bxy for a,bxy in issue_points)-miny]
            records[id]={'semantic_id':id,'房名':row['room_name'],'类型':'drawing_issue','状态':'问题定位',
                'L4分类':'图纸问题','源Handle列表':[row['text_handle']],'外层块Handle':row['outer_block_handle'],
                'view_bounds':b,'图纸问题':row,'source':{'handle':row['text_handle']}}
            room_options.append({'id':id,'name':row['room_name'],'type':'drawing_issue','category':'DRAWING_ISSUE','bounds':b})
            svg.append(f'<g class="issue" data-id="{id}" tabindex="0" role="button" aria-label="图纸问题 {escape(row["room_name"],quote=True)} {row["text_handle"]}"><circle cx="{x:.3f}" cy="{y:.3f}" r=".35"/><path d="M{x-.17:.3f},{y-.17:.3f}l.34,.34M{x+.17:.3f},{y-.17:.3f}l-.34,.34"/></g>')
            extra=[]
            for gap in row['gap_candidates']:
                a=xy(*gap['a_wcs_mm']);bxy=xy(*gap['b_wcs_mm'])
                extra.append(f'<path class="gap-marker" d="M{a[0]},{a[1]}L{bxy[0]},{bxy[1]}"/>')
                for px,py in [a,bxy]:extra.append(f'<circle class="gap-end" cx="{px}" cy="{py}" r=".13"/>')
            candidate=row['text_position_candidate']
            if candidate:
                points=[xy(*p) for p in candidate['outline_wcs_mm']]
                extra.append('<path class="text-region" d="M'+'L'.join(f'{a},{b}' for a,b in points)+'Z"/>')
                q=xy(*candidate['suggested_point_wcs_mm'])
                extra.append(f'<path class="text-suggestion" d="M{x},{y}L{q[0]},{q[1]}"/><circle class="gap-end" cx="{q[0]}" cy="{q[1]}" r=".22"/>')
            records[id]['问题高亮']=''.join(extra)
    full=[(min(x for x,y in coords)-ox)/1000,-(max(y for x,y in coords)-oy)/1000,
          (max(x for x,y in coords)-ox)/1000,(max(y for x,y in coords)-oy)/1000]
    raw_bounds=[(min(x for x,y in coords)-ox)/1000,-(max(y for x,y in coords)-oy)/1000,(max(x for x,y in coords)-min(x for x,y in coords))/1000,(max(y for x,y in coords)-min(y for x,y in coords))/1000]
    plans=[row['bounds'] for row in room_options if row['type']=='space' and row['bounds']]
    if plans:
        left=min(b[0] for b in plans);top=min(b[1] for b in plans)
        full=[left,top,max(b[0]+b[2] for b in plans)-left,max(b[1]+b[3] for b in plans)-top]
    else:full=raw_bounds
    default=next((o['id'] for o in room_options if o['name']=='预留充电桩配电房'),None)
    if default is None:default=next((o['id'] for o in room_options if o['category'] in ('SUBSTATION','DISTRIBUTION_ROOM')),room_options[0]['id'] if room_options else None)
    if delta:
        default=next((r['id'] for r in room_options if r['type']=='change' and '预留充电桩配电房' in r['name']),default)
    from .adjacency import adjacency
    neighbors=adjacency(data,classes)['candidates']
    wall_paths={o.semantic_id:paths(o.geometry) for o in data.objects if o.type=='wall'}
    from .cad_location import cad_location
    for record in records.values():record['CAD定位']=cad_location(record,[ox,oy])
    payload={'change_summary':{k:delta[k] for k in ('change_count','change_types','review_inheritance','lighting_changes','times','checklist','engineer_comparison','lighting_calculation_changes') if k in delta} if delta else None,'neighbors':neighbors,'wall_paths':wall_paths,'objects':records,'rooms':room_options,'full_bounds':full,'default':default,'origin_wcs_mm':[ox,oy],
             'drawing_sha256':data.drawing.sha256,'raw_geometry_count':raw_geometry_count,
             'missing_geometry_records':missing_geometry,'rules_summary':results['summary']}
    if delta:
        from .cloud import cloud_regions
        payload['change_summary']['cloud_regions']=[{**r,'view_bounds':[(r['bounds'][0]-ox)/1000,-(r['bounds'][3]-oy)/1000,(r['bounds'][2]-r['bounds'][0])/1000,(r['bounds'][3]-r['bounds'][1])/1000]} for r in cloud_regions(delta)]
        payload['change_summary']['rule_inputs']={side:[{'rule_id':f['rule_id'],'object_ids':f['object_ids'],'name':f.get('object_name','未识别到适用房间'),
            'candidate_opening_count':f['values'].get('candidate_opening_count'),'manual_confirmation':f['values'].get('manual_confirmation'),
            'water_neighbors':sorted({n['name'] for n in f['values'].get('adjacent_candidates',[]) if n.get('water_candidate')})}
            for f in delta[side+'_check']['findings']] for side in ('old','new')}
    from .uses import DEFAULT_TABLE
    import hashlib,yaml
    term_table=yaml.safe_load(DEFAULT_TABLE.read_text(encoding='utf-8'))
    for record in records.values():
        rid=record.get('房间') if record.get('类型')=='generated_light' else record.get('semantic_id')
        if rid in calculations:record['照度计算']=calculations[rid]
        cls=classes.get(rid,{})
        record['用途解析来源']=cls.get('naming_provenance') or {'mode':'已批准词表','approved_by':term_table.get('approved_by'),'llm_used_for_this_name':False,'table_sha256':hashlib.sha256(DEFAULT_TABLE.read_bytes()).hexdigest()}
    from .priority import room_priorities
    for record in records.values():
        c=record.get('变更')
        oid=(c.get('new') or {}).get('id') if c else record.get('semantic_id')
        record['priorities']=room_priorities(oid,record.get('房名'),record.get('适用规则结果',[]),delta,(c.get('old') or {}).get('id') if c else None)
        record['适用规则结果']=sorted(record.get('适用规则结果',[]),key=lambda f:f.get('priority_rank',3))
    if payload['change_summary']:
        def display_rank(row):return (records.get(row['id'],{}).get('priorities') or [{'rank':99}])[0]['rank']
        if 'checklist' in payload['change_summary']:payload['change_summary']['checklist'].sort(key=display_rank)
        comparison=payload['change_summary'].get('engineer_comparison')
        if comparison:
            def answer_rank(row):
                found=next((r for r in records.values() if r.get('类型')=='change' and row.get('target_handle') in r.get('源Handle列表',[])),None)
                if found is None:found=next((r for r in records.values() if r.get('类型')=='space' and r.get('房名')==row.get('target_name',row.get('name'))),{})
                return (found.get('priorities') or [{'rank':99}])[0]['rank']
            comparison['items'].sort(key=answer_rank)
    template=Path(__file__).with_name('view.html').read_text(encoding='utf-8')
    content=template.replace('__SVG__',''.join(svg)).replace('__GRAY__',gray)
    content=content.replace('__PAYLOAD__',json.dumps(payload,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c'))
    output=Path(output) if output else Path('dist/view')/directory.name/'semantic_view.html'
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(content,encoding='utf-8')
    return {'output':output.as_posix(),'objects':len(records),'room_count':sum(r['type'] in ('space','shaft','zone') for r in room_options),'drawing_issue_count':sum(r['type']=='drawing_issue' for r in room_options),
            'raw_geometry_records':raw_geometry_count,'geometry_missing':missing_geometry,
            'network_required':False,'source_coordinates':'WCS毫米；显示平移缩放，Y轴向上，与CAD方向一致'}
