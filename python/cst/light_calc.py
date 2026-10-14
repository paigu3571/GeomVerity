# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 张田
"""规整矩形流明法估算。计算数量与几何候选数量分别记录。"""
import math,json,hashlib
from pathlib import Path
import yaml
from shapely.geometry import Polygon
from .model import load
from .naming import digest
from .uses import classify
from .l4 import envelope_dimensions
from .resources import rules_directory
RULE=rules_directory()/'LIGHT-CALC-001.yaml'

def calculate_room(room,category,rule,candidate_count=None):
    base={'room_semantic_id':room.semantic_id,'room_name':room.raw_label,'source_handles':[room.source.handle],'rule_id':rule['id'],'rule_version':rule['rule_version'],'parameters':rule['parameters'],'clauses':rule['clauses'],'normative_values_verified':rule['normative_values_verified'],'approved_by':rule['approved_by'],'sign_off_state':'待工程师签字','input_status':room.status,'formula':{'room_index':'RI=L×W/[h×(L+W)]','required_count':'ceil(E×A/(Φ×光源数×U×K))','average':'Eav=灯具数×光源数×Φ×U×K/A','lpd':'LPD=灯具数×光源数×功率/A'}}
    if category not in rule['applies_to']:return dict(base,result='不适用')
    if not room.geometry.is_closed or len(room.geometry.paths)!=1:return dict(base,result='需人工计算',reason='缺少单一闭合轮廓')
    polygon=Polygon([(p.x,p.y) for p in room.geometry.paths[0]])
    if not polygon.is_valid or polygon.area<=0:return dict(base,result='需人工计算',reason='轮廓无效')
    ratio=polygon.area/polygon.minimum_rotated_rectangle.area
    if ratio<rule['min_rectangle_ratio']:return dict(base,result='需人工计算',reason='异形房间需人工计算',rectangle_ratio=round(ratio,6))
    p=rule['parameters'];keys=['target_illuminance_lx','lpd_limit_w_m2','flux_per_source_lm','sources_per_fixture','power_per_source_w','utilization','maintenance','effective_height_m']
    if any(type(p.get(k)) not in (int,float) or not math.isfinite(p[k]) or p[k]<=0 for k in keys):raise ValueError('计算参数必须为正有限数')
    if p['utilization']>1 or p['maintenance']>1:raise ValueError('利用/维护系数不能超过1')
    dimensions=envelope_dimensions(room.geometry);length=dimensions['long_side_m'];width=dimensions['short_side_m'];area=polygon.area/1e6;h=p['effective_height_m']
    ri=length*width/(h*(length+width));effective_flux=p['flux_per_source_lm']*p['sources_per_fixture']*p['utilization']*p['maintenance'];count=math.ceil(p['target_illuminance_lx']*area/effective_flux)
    def back(n):
        return {'fixture_count':n,'eav_lx':round(n*effective_flux/area,3),'lpd_w_m2':round(n*p['sources_per_fixture']*p['power_per_source_w']/area,3),'illuminance_target_met':n*effective_flux/area>=p['target_illuminance_lx'],'demo_lpd_limit_met':n*p['sources_per_fixture']*p['power_per_source_w']/area<=p['lpd_limit_w_m2']}
    value=dict(base,result='演示参数回算完成',rectangle_ratio=round(ratio,6),area_m2=round(area,6),dimensions_m={'length':length,'width':width},effective_height_m=h,room_index=round(ri,6),calculated_fixture_count=count,estimated=back(count),existing_layout=back(candidate_count) if candidate_count is not None else None,formal_compliance='无法判定：规范表格值、真实灯具参数及驱动功耗尚未全部核验',geometry_note=dimensions['method'])
    if ri<=1:value['formal_compliance']='无法判定：室形指数不大于1，需核实修正限值；另缺规范表格核验及完整灯具功耗'
    return value

def calculate(data,classes,lights=None):
    rule=yaml.safe_load(RULE.read_text(encoding='utf-8'));groups={g['room_semantic_id']:g['candidate_count'] for g in (lights or {}).get('groups',[])}
    rows=[calculate_room(o,classes.get(o.semantic_id,{}).get('category'),rule,groups.get(o.semantic_id)) for o in data.objects if o.type=='space' and classes.get(o.semantic_id,{}).get('category') in rule['applies_to']]
    from .decisions import decision,rule_metadata
    objects={o.semantic_id:o for o in data.objects}
    run_id='run_'+digest({'drawing':data.drawing.sha256,'rule_sha256':hashlib.sha256(RULE.read_bytes()).hexdigest()})[:24]
    for row in rows:row['decision']=decision('lighting_calculation',row['room_semantic_id'],row['result'],[row['room_semantic_id']],objects,rule_metadata(rule['id']),run_id)
    return {'schema_version':'light-calculation.v1','rule_sha256':hashlib.sha256(RULE.read_bytes()).hexdigest(),'origin':'REAL_JSON','rows':rows}

def calculate_directory(directory,output=None):
    from .lighting import generate_directory
    data=load(directory)
    if data.drawing.geometry_units!='mm' or data.status=='failed':raise ValueError('仅支持未失败的毫米快照')
    result=calculate(data,{r['object_id']:r for r in classify(directory)['rows']},generate_directory(directory))
    path=Path(output or 'dist/calculations/'+Path(directory).name+'/lighting_calculations.json');path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return {'output':path.as_posix(),'calculated':sum(r['result']=='演示参数回算完成' for r in result['rows']),'manual':sum(r['result']=='需人工计算' for r in result['rows']),'formal_pass_count':0}


def synthetic_probe(output='dist/calculations/SYNTHETIC/lighting_calculations.json'):
    from types import SimpleNamespace as S
    points=[S(x=x,y=y) for x,y in [(0,0),(9000,0),(9000,7000),(0,7000)]]
    room=S(semantic_id='SYNTHETIC_RECT_9x7',raw_label='SYNTHETIC矩形演示',status='review',source=S(handle='SYNTHETIC_NO_CAD_HANDLE'),geometry=S(is_closed=True,paths=[points]))
    rule=yaml.safe_load(RULE.read_text(encoding='utf-8'));row=calculate_room(room,'DISTRIBUTION_ROOM',rule,30)
    row['origin']='SYNTHETIC';row['source_note']='人工构造9米×7米轮廓，仅验证公式，不能当真实图纸成果。'
    path=Path(output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf-8')
    return {'origin':'SYNTHETIC','output':path.as_posix(),'estimated':row['estimated'],'existing_layout':row['existing_layout']}
