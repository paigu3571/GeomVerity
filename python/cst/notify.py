# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 张田
"""生成待签字的提资通知；不发送消息，不编造逐项编辑时间。"""
import json,os,re
from datetime import datetime,timezone,timedelta
from pathlib import Path
import httpx,yaml
from .model import load
from .ai import ReadTools,validate
from .naming import digest
from .priority import room_priorities
ROOT=Path.cwd()
PROMPT='起草电气专业提资变更通知，返回JSON {claims:[{text,object_ids,values}],reason:null}。每个notice_item恰好一个claim，保持给定风险顺序。text只写具体影响和协作动作，房名、Handle、版本时间由程序另行排版，不在text重复数字或编号，也不罗列ID。values必须包括该变更ID.name、.old_handle、.new_handle（null也保留），和version_old.version、version_old.scanned_at、version_new.version、version_new.scanned_at。object_ids必须包括该变更ID、version_old、version_new。values从truth逐字复制，仅用顶层字段，不输出嵌套字段。门洞减少只能说请核对有效出口；用水贴邻只能建议核对漏水影响和隔墙措施。不得称已确认违规、合规或已签字，不猜编辑时刻。未命中时只能写限定范围内未发现影响候选，不能说不影响电气或无需协作。'

def numeric_tokens(text):return set(re.findall(r'(?<![A-Za-z])\d+(?:\.\d+)?',str(text)))
def validate_notice(answer,truth):
    result=validate(answer,truth)
    for claim in answer.get('claims',[]):
        declared=set().union(*(numeric_tokens(v) for v in claim.get('values',{}).values())) if claim.get('values') else set()
        if numeric_tokens(claim.get('text',''))-declared:result['errors'].append('正文数字未在values声明')
        if re.search(r'不影响.{0,12}电气|无需.{0,12}协作|没有.{0,6}风险',claim.get('text','')):result['errors'].append('超出已识别范围，不能宣称无影响或无需协作')
        ids=claim.get('object_ids',[])
        if not any(i.startswith(('change_','finding_')) for i in ids):result['errors'].append('通知项缺少变更或规则引用')
        if not {'version_old','version_new'}<=set(ids):result['errors'].append('通知项缺少两版时间引用')
    if not answer.get('claims'):result['errors'].append('通知为空')
    expected={i for i in truth['objects'] if i.startswith('change_')}
    actual=[i for c in answer.get('claims',[]) for i in c.get('object_ids',[]) if i.startswith('change_')]
    if set(actual)!=expected or len(actual)!=len(expected):result['errors'].append('变更通知缺项或重复')
    for c in answer.get('claims',[]):
        cid=next((i for i in c.get('object_ids',[]) if i.startswith('change_')),None)
        required={cid+'.'+f for f in ('name','old_handle','new_handle')} if cid else set()
        required|={i+'.'+f for i in ('version_old','version_new') for f in ('version','scanned_at')}
        if not required<=set(c.get('values',{})):result['errors'].append('缺少通知必需事实引用')
    result['valid']=not result['errors'];return result

def registered_versions(old,new,registry):
    records=yaml.safe_load(Path(registry).read_text(encoding='utf-8')).get('versions',[])
    result={}
    for side,directory in [('old',old),('new',new)]:
        data=load(directory);row=next((r for r in records if r.get('drawing_sha256')==data.drawing.sha256),None)
        if row is None:raise ValueError('版本未登记：'+Path(directory).name)
        result['version_'+side]={'id':'version_'+side,'status':'review',**{k:row[k] for k in ('version','drawing_saved_at','scanned_at','issued_by')}}
    return result

def notify(old,new,replay=False,output='dist/notify',registry='versions.yaml',changes=None):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    if changes:
        delta=json.loads(Path(changes).read_bytes())
        if (delta['old_hash'],delta['new_hash'])!=(load(old).drawing.sha256,load(new).drawing.sha256):raise ValueError('变更文件与两版不对应')
    else:
        from .changes import diff
        diff(old,new,output);changes=output/'diff.json';delta=json.loads(Path(changes).read_bytes())
    change_id_bindings={}
    for change in delta['changes']:
        stable_id='change_'+digest({'old_id':(change['old'] or {}).get('id'),'new_id':(change['new'] or {}).get('id'),'kinds':change['kinds']})[:24]
        change_id_bindings[stable_id]=change['id'];change['id']=stable_id
    tools=ReadTools(new,changes);tools.changes_data=delta;versions=registered_versions(old,new,registry)
    changes_rows=tools.get_changes(type='space',limit=100)['items']
    findings=delta['new_check']['findings'];truth={'objects':{**versions,**{c['id']:c for c in changes_rows},**{f['id']:tools._finding_reference(f) for f in findings}},'summary':tools.summary()}
    priorities=[]
    for c in delta['changes']:
        o=c['new'] or c['old']
        if o['type']=='space':priorities.extend(room_priorities((c['new'] or {}).get('id'),o['name'],[f for f in findings if (c['new'] or {}).get('id') in f['object_ids']],delta,(c['old'] or {}).get('id')))
    source={'versions':versions,'changes':changes_rows,'impacts':tools.get_impacts(limit=100),'priorities':sorted(priorities,key=lambda p:p['rank']),'truth':truth,'time_boundary':'保存/扫描时间属于版本；逐项编辑时刻未记录。'}
    notice_items=[]
    for c in delta['changes']:
        ref=c['new'] or c['old']
        if ref['type']!='space':continue
        local=room_priorities((c['new'] or {}).get('id'),ref['name'],[f for f in findings if (c['new'] or {}).get('id') in f['object_ids']],delta,(c['old'] or {}).get('id'))
        change_ref=tools._change_reference(c)
        compact={k:v for k,v in change_ref.items() if k not in ('old','new','priorities')}
        if compact['result']=='不影响现有电气结论':compact['result']='限定范围内未发现影响候选'
        truth['objects'][c['id']]=compact
        notice_items.append({'id':c['id'],'rank':local[0]['rank'] if local else 3,'facts':compact,'risk':local,'affected_rooms':c['impact']['rooms'],'suggested_work':c['suggested_work']})
    notice_items.sort(key=lambda r:(r['rank'],r['id']))
    source={'versions':versions,'notice_items':notice_items,'truth':{'objects':{k:v for k,v in truth['objects'].items() if k.startswith(('version_','change_'))}},'time_boundary':'版本时间来自扫描登记，逐项编辑时刻未记录。'}
    config=yaml.safe_load(Path(__file__).with_name('ai_config.yaml').read_text(encoding='utf-8'))
    request={'model':config['model'],'messages':[{'role':'system','content':PROMPT},{'role':'user','content':json.dumps(source,ensure_ascii=False)}],'temperature':0,'max_tokens':12000,'thinking':{'type':config['thinking']},'response_format':{'type':'json_object'}}
    token=digest({'request':request,'base_url':config['base_url'],'schema':'notice.v1'});path=ROOT/'ai_cache/notifications'/f'{token}.json'
    if replay:
        record=json.loads(path.read_bytes())
        if record['request_sha256']!=token or record['origin']!='REAL_API':raise ValueError('缓存与当前输入不一致')
        answer=record['answer'];validation=validate_notice(answer,truth)
    else:
        key=os.environ.get('DEEPSEEK_API_KEY')
        if not key:raise ValueError('未设置DEEPSEEK_API_KEY')
        transcript=[];answer={};validation={'valid':False,'errors':[]}
        with httpx.Client(timeout=120) as client:
            for attempt in range(3):
                response=client.post(config['base_url']+'/chat/completions',headers={'Authorization':'Bearer '+key},json=request);response.raise_for_status();raw=response.json();transcript.append({'request':json.loads(json.dumps(request)),'response':raw})
                try:
                    if raw['choices'][0].get('finish_reason')=='length':raise ValueError('回答被截断')
                    answer=json.loads(raw['choices'][0]['message']['content']);validation=validate_notice(answer,truth)
                except (ValueError,KeyError,TypeError) as exc:validation={'valid':False,'errors':[str(exc)]}
                if validation['valid']:break
                request['messages'].append({'role':'user','content':'引用校验未通过，请完整重答JSON：'+json.dumps(validation['errors'],ensure_ascii=False)})
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps({'origin':'REAL_API','kind':'COORDINATION_NOTICE','request_sha256':token,'model':config['model'],'source':source,'answer':answer,'validation':validation,'retry_count':len(transcript)-1,'transcript':transcript},ensure_ascii=False,indent=2),encoding='utf-8')
    expected={r['id'] for r in notice_items}
    actual=[i for c in answer.get('claims',[]) for i in c.get('object_ids',[]) if i.startswith('change_')]
    if set(actual)!=expected or len(actual)!=len(expected):validation['errors'].append('变更通知缺项或重复')
    for c in answer.get('claims',[]):
        cid=next((i for i in c.get('object_ids',[]) if i.startswith('change_')),None)
        required={cid+'.'+f for f in ('name','old_handle','new_handle')} if cid else set()
        required|={i+'.'+f for i in ('version_old','version_new') for f in ('version','scanned_at')}
        if not required<=set(c.get('values',{})):validation['errors'].append('缺少通知必需事实引用')
    validation['valid']=not validation['errors']
    (output/'notice.json').write_text(json.dumps({'answer':answer,'validation':validation,'cache_id':token,'sign_off_state':'待工程师签字','sent':False,'change_id_bindings':change_id_bindings},ensure_ascii=False,indent=2),encoding='utf-8')
    display_time=lambda value:datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S（北京时间）')
    paragraphs=['# 致电气专业：提资变更通知','', '签字状态：待工程师签字；未发送。', '', '两版之间的变化如下。时间对应文件保存与扫描，不代表逐项编辑时刻。', '']
    if not validation['valid']:paragraphs+=['**引用校验未通过，此草案不采用。**','',*validation['errors']]
    else:
        claims={next(i for i in c['object_ids'] if i.startswith('change_')):c for c in answer['claims']}
        for item in notice_items:
            fact=item['facts'];claim=claims[item['id']]
            change=next(c for c in delta['changes'] if c['id']==item['id'])
            before=(change['old'] or {}).get('name');after=(change['new'] or {}).get('name')
            description='房名：'+str(before)+' → '+str(after) if before and after and before!=after else fact['change_type']
            paragraphs += ['## '+('优先核对：' if item['rank']<=1 else '')+fact['name'], '', '旧版：'+versions['version_old']['version']+'；扫描：'+display_time(versions['version_old']['scanned_at'])+'；Handle：'+str(fact['old_handle'] or '无旧对象'), '新版：'+versions['version_new']['version']+'；扫描：'+display_time(versions['version_new']['scanned_at'])+'；Handle：'+str(fact['new_handle'] or '无新对象'), '', '变化：'+description, *([item['risk'][0]['text']] if item['risk'] else []), claim['text'], '']
    presentation=render_notice(delta,notice_items,answer,validation,versions,tools.objects,output)
    (output/'notice.json').write_text(json.dumps({'answer':answer,'validation':validation,'cache_id':token,'sign_off_state':'待工程师签字','sent':False,'change_id_bindings':change_id_bindings,'presentation':presentation},ensure_ascii=False,indent=2),encoding='utf-8')
    return {'valid':validation['valid'],'errors':validation['errors'],'cache_id':token,'network_used':not replay,'output':output.as_posix(),'sent':False}


def is_recognition_fluctuation(change):
    basis=change.get('basis','')
    return basis.startswith('派生围合差异') or (basis.startswith('房名文字仍在') and not change.get('related_source_changes'))


def render_notice(delta,items,answer,validation,versions,objects,output):
    """同一结构生成Markdown和正式离线HTML；模型原缓存单独保留。"""
    from html import escape
    from shapely.geometry import Polygon
    claims={next((i for i in c.get('object_ids',[]) if i.startswith('change_')),None):c for c in answer.get('claims',[])}
    changes={c['id']:c for c in delta['changes']};groups={'优先处理':[],'需复核':[],'仅记录':[]}
    for item in items:
        c=changes[item['id']];ref=c['new'] or c['old'];fluctuation=is_recognition_fluctuation(c)
        group='仅记录' if fluctuation else '优先处理' if item['rank']<=1 else '需复核' if item['rank']==2 or c.get('related_source_changes') else '仅记录'
        geometry=c.get('new_geometry') or c.get('old_geometry') or {};paths=geometry.get('paths',[])
        area=None;position=None
        if paths:
            polygon=Polygon([(p['x'],p['y']) for p in paths[0]])
            if polygon.is_valid:
                area=polygon.area/1e6;q=polygon.representative_point();position=[round(q.x,1),round(q.y,1)]
        obj=objects.get((c['new'] or {}).get('id'))
        labels=[e.source_handle for e in obj.evidence if e.kind=='spatial_text'] if obj else []
        location={'space_id':ref['id'],'room_text_handles':labels,'geometry_reference_handle':ref['handle'],'area_m2':area,'position_wcs_mm':position}
        sentences=[]
        def template(text):sentences.append({'text':text,'source':'模板','validation':'源快照核对通过','evidence_refs':[c['id'],'version_old','version_new']})
        template(ref['name']+(f'，面积{area:.1f}㎡' if area is not None else '')+(f'，位置WCS({position[0]:.1f}, {position[1]:.1f})mm' if position else '')+'；房名文字Handle：'+('、'.join(labels) or '未取得')+'。')
        if fluctuation:
            template('程序识别波动，无需处理建筑修改；仅记录围合提取差异，原图修改未获证实。')
        else:
            before=(c['old'] or {}).get('name');after=(c['new'] or {}).get('name')
            template('变化：'+(f'{before} → {after}' if before and after and before!=after else '、'.join(k for k in c['kinds'] if k!='来源对象变化'))+'。')
            if item['risk']:template(item['risk'][0]['title'])
            claim=claims.get(item['id'])
            if claim and validation['valid']:sentences.append({'text':claim['text'],'source':'模型','validation':'引用校验通过','evidence_refs':claim['object_ids']})
            elif claim:template('模型草案引用校验未通过，未采用其文字。')
        sentences=[dict(sentence,text=part.strip()) for sentence in sentences for part in re.split(r'(?<=[。！？])',sentence['text']) if part.strip()]
        groups[group].append({'id':c['id'],'name':ref['name'],'location':location,'fluctuation':fluctuation,'sentences':sentences})
    # 房间轮廓未变但门窗变化时，仍从实际源对象变化补一条模板协作项。
    covered={r['location']['space_id'] for rows in groups.values() for r in rows if not r['fluctuation']}
    door_rooms={}
    for c in delta['changes']:
        if (c.get('new') or c.get('old') or {}).get('type') not in ('opening','door','window'):continue
        for room in c.get('impact',{}).get('rooms',[]):
            if room['side']!='new' or room['id'] in covered:continue
            door_rooms.setdefault(room['id'],{'room':room,'changes':[]})['changes'].append(c)
    for rid,row in door_rooms.items():
        obj=objects.get(rid)
        if obj is None:continue
        c=row['changes'][0];labels=[e.source_handle for e in obj.evidence if e.kind=='spatial_text']
        polygon=Polygon([(p.x,p.y) for p in obj.geometry.paths[0]]) if obj.geometry.paths else None
        area=polygon.area/1e6 if polygon is not None and polygon.is_valid else None
        position=[round(polygon.representative_point().x,1),round(polygon.representative_point().y,1)] if area is not None else None
        text=obj.raw_label+(f'（面积{area:.1f}㎡，位置WCS{position}mm）' if area is not None else '')+'的关联门窗源对象发生变化，请核对门位、有效出入口和相关灯具布置。'
        groups['需复核'].append({'id':c['id'],'name':obj.raw_label,'location':{'space_id':rid,'room_text_handles':labels,'area_m2':area,'position_wcs_mm':position},'fluctuation':False,'sentences':[{'text':text,'source':'模板','validation':'源对象引用核对通过','evidence_refs':[v['id'] for v in row['changes']]}]})
    summary=f"本次{len(groups['优先处理'])}项优先处理、{len(groups['需复核'])}项需复核、{len(groups['仅记录'])}项仅记录。"
    local_time=lambda value:datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S 北京时间')
    versions_text='旧版 '+versions['version_old']['version']+'（扫描 '+local_time(versions['version_old']['scanned_at'])+'） → 新版 '+versions['version_new']['version']+'（扫描 '+local_time(versions['version_new']['scanned_at'])+'）；时间只对应版本。'
    md=['# 致电气专业：提资变更通知','',summary+'【模板｜源快照核对通过】','',versions_text+'【模板｜版本登记核对通过】','', '待工程师签字；未发送。【模板｜状态字段核对通过】','']
    sections=[]
    for title,rows in groups.items():
        md+=['## '+title,''];cards=[]
        for row in rows:
            md+=['### '+row['name'],'']
            body=[]
            for sentence in row['sentences']:
                badge=sentence['source']+'｜'+sentence['validation'];md+=[sentence['text']+'【'+badge+'】','']
                body.append('<p>'+escape(sentence['text'])+'<small>'+escape(badge)+'</small></p>')
            cards.append('<article><h3>'+escape(row['name'])+'</h3>'+''.join(body)+'<details><summary>开发者 / AI：对象与引用</summary><pre>'+escape(json.dumps(row,ensure_ascii=False,indent=2))+'</pre></details></article>')
        sections.append('<section><h2>'+title+' · '+str(len(rows))+'项</h2>'+(''.join(cards) or '<p>本组无事项。</p>')+'</section>')
    html='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>提资变更通知</title><style>body{font:16px/1.75 "Microsoft YaHei",sans-serif;background:#f3f7fa;color:#183949;margin:0}main{max-width:1080px;margin:24px auto;padding:24px}header{border-top:6px solid #147b80;background:white;padding:24px}h1{font-size:27px}h2{color:#147b80}article{background:white;border-left:4px solid #d8e6ed;padding:12px 22px;margin:16px 0}section:first-of-type article{border-left-color:#e98528}small{display:block;color:#627888;font-size:12px}pre{white-space:pre-wrap;font-size:12px}details{font-size:12px}p{margin:9px 0}</style><main><header><h1>致电气专业：提资变更通知</h1><p><b>'+summary+'</b><small>模板｜源快照核对通过</small></p><p>'+escape(versions_text)+'<small>模板｜版本登记核对通过</small></p><p>待工程师签字；未发送。<small>模板｜状态字段核对通过</small></p></header>'+''.join(sections)+'</main></html>'
    output=Path(output);(output/'notice.md').write_text('\n'.join(md)+'\n',encoding='utf-8');(output/'notice.html').write_text(html,encoding='utf-8')
    return {'summary':summary,'groups':groups,'model_validation':validation,'version_times':versions}
