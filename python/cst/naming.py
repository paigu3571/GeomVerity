# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 张田
"""真实房名实验。人工答案只用于调用后的对照，不进入模型输入。"""
import hashlib
import json
import os
import re
from pathlib import Path
import httpx
import yaml
from .model import load, L2
from .recovery import label_rows
from .uses import DEFAULT_TABLE

ROOT = Path(__file__).resolve().parents[2]
PROMPT = '你是建筑术语提议助手，只分类房名，不判断几何或合规。类别只能选给定类别或UNKNOWN；不了解时选UNKNOWN。返回JSON对象rows，每项{name,category,reason,confidence,needs_review}。confidence为0到1数字，needs_review必须true。每个输入房名恰好一次，理由简短。不要自行批准。'

def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

def validate(answer, names, categories):
    rows=answer.get('rows')
    if not isinstance(rows,list) or len(rows)!=len(names):raise ValueError('房名缺项或多项')
    if {r.get('name') for r in rows}!=set(names) or len({r.get('name') for r in rows})!=len(rows):raise ValueError('房名重复或被改写')
    for r in rows:
        if set(r)!={'name','category','reason','confidence','needs_review'}:raise ValueError('提议字段不完整')
        if r['category'] not in categories:raise ValueError('类别越界')
        if not isinstance(r['reason'],str) or not r['reason'].strip():raise ValueError('缺少理由')
        if type(r['confidence']) not in (float,int) or not 0<=r['confidence']<=1:raise ValueError('置信值越界')
        if r['needs_review'] is not True:raise ValueError('模型不得跳过人工审批')
    return sorted(rows,key=lambda r:r['name'])

def experiment(directories, replay=False):
    table=yaml.safe_load(DEFAULT_TABLE.read_text(encoding='utf-8'))
    names=set();sources={};drawing_hashes=set()
    for directory in directories:
        drawing_hashes.add(load(directory).drawing.sha256.upper())
        found={o.raw_label for o in load(directory).objects if o.type in ('space','shaft') and o.raw_label}
        found|={f.raw_text for f,x,y in label_rows(load(directory,L2))}
        for name in found:sources.setdefault(name,[]).append(Path(directory).name)
        names|={name for name in found if not re.fullmatch(r"[\d\s.]+",name) and not name.startswith("[REDACTED_")}
    corpus=ROOT/'eval/room_name_corpus.json'
    if corpus.is_file():names|={r['name'] for r in json.loads(corpus.read_bytes())['rows'] if r['drawing_sha256'].upper() in drawing_hashes}
    names=sorted(names);categories={r['code']:r['label'] for r in table['classes']};categories['UNKNOWN']='用途无法判断'
    config=yaml.safe_load(Path(__file__).with_name('ai_config.yaml').read_text(encoding='utf-8'))
    available={};records={}
    for path in sorted((ROOT/'ai_cache/naming').glob('*.json')):
        record=json.loads(path.read_bytes());first=record['transcript'][0]['request']
        if record.get('origin')!='REAL_API' or not record.get('valid') or record['source']['categories']!=categories or first['model']!=config['model'] or first['messages'][0]['content']!=PROMPT:continue
        if digest({'request':first,'base_url':config['base_url'],'schema_version':'naming.v1'})!=record['request_sha256']:raise ValueError('命名缓存身份校验失败')
        expected_settings={'model':config['model'],'temperature':0,'max_tokens':8192,'thinking':{'type':config['thinking']},'response_format':{'type':'json_object'}}
        if any(first.get(k)!=v for k,v in expected_settings.items()):continue
        records[path.stem]=record
        for row in validate(record['answer'],record['source']['names'],categories):available.setdefault(row['name'],(row,path.stem))
    rows=[available[name][0] for name in names if name in available]
    cache_by_name={name:available[name][1] for name in names if name in available};cache_ids=sorted(set(cache_by_name.values()));attempts=sum(len(records[i]['transcript']) for i in cache_ids)
    pending=[name for name in names if name not in available]
    if pending and replay:raise ValueError('新增房名尚无真实缓存，请先联网运行一次命名实验')
    for offset in range(0,len(pending),20):
        batch=pending[offset:offset+20];source={'names':batch,'categories':categories}
        request={'model':config['model'],'messages':[{'role':'system','content':PROMPT},{'role':'user','content':json.dumps(source,ensure_ascii=False)}],'temperature':0,'max_tokens':8192,'thinking':{'type':config['thinking']},'response_format':{'type':'json_object'}}
        token=digest({'request':request,'base_url':config['base_url'],'schema_version':'naming.v1'})
        path=ROOT/'ai_cache'/'naming'/f'{token}.json';cache_ids.append(token);cache_by_name.update({name:token for name in batch})
        if replay:
            record=json.loads(path.read_bytes())
            if record.get('request_sha256')!=token or record.get('origin')!='REAL_API':raise ValueError('缓存身份不匹配')
            rows.extend(validate(record['answer'],batch,categories));attempts+=len(record['transcript']);continue
        key=os.environ.get('DEEPSEEK_API_KEY')
        if not key:raise ValueError('未设置DEEPSEEK_API_KEY；已有缓存可用--replay')
        transcript=[];answer={};errors=[];valid=False
        with httpx.Client(timeout=90) as client:
            for attempt in range(3):
                response=client.post(config['base_url']+'/chat/completions',headers={'Authorization':'Bearer '+key},json=request)
                response.raise_for_status();raw=response.json();transcript.append({'request':json.loads(json.dumps(request)),'response':raw})
                try:
                    if raw['choices'][0].get('finish_reason')=='length':raise ValueError('回答截断')
                    answer=json.loads(raw['choices'][0]['message']['content']);validated=validate(answer,batch,categories);valid=True;break
                except (ValueError,KeyError,TypeError) as exc:
                    errors.append(str(exc));request['messages'].append({'role':'user','content':'请修正后完整重答：'+str(exc)})
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps({'origin':'REAL_API','kind':'NAMING_PROPOSAL','request_sha256':token,'model':config['model'],'source':source,'answer':answer,'valid':valid,'validation_errors':errors,'transcript':transcript},ensure_ascii=False,indent=2),encoding='utf-8')
        if not valid:raise ValueError('重答仍不合格式，缓存已保留')
        rows.extend(validated);attempts+=len(transcript)
    rows.sort(key=lambda r:r['name'])
    gold=table['confirmed_names'];compared=[r for r in rows if r['name'] in gold];disagree=[r for r in compared if r['category']!=gold[r['name']]['category']];new=[r for r in rows if r['name'] not in gold]
    proposals={'schema_version':'naming-proposals.v1','approved':False,'model':config['model'],'cache_ids':cache_ids,'entries':[dict(r,approved=False,approved_by=None,cache_id=cache_by_name[r["name"]]) for r in new]}
    target=ROOT/'rules/naming_proposals.yaml'
    if target.exists():
        previous=yaml.safe_load(target.read_text(encoding='utf-8')) or {};approved={r['name']:r for r in previous.get('entries',[]) if (r.get('approved') and r.get('approved_by')) or r.get('reviewed_by')}
        proposals['entries']=[approved.get(r['name'],r) for r in proposals['entries']]
    target.write_text('# SPDX-License-Identifier: MPL-2.0\n'+yaml.safe_dump(proposals,allow_unicode=True,sort_keys=False),encoding='utf-8')
    text=['# 房名术语解析实测','',f'三份快照及同源原扫描房名补充清单共{len(names)}种房名候选（含未围合及上空标注）。人工词表有{len(gold)}种，其中{len(compared)}种出现在本次输入。模型与工程师一级分类一致{len(compared)-len(disagree)}/{len(compared)}；这是本批房名的对照结果，不外推到其他图纸。', '',f'真实接口请求{attempts}次，模型{config["model"]}。人工答案未发送给模型。模型只收到类别名称和房名候选；格式校验检查枚举、完整性和审批状态，不证明专业分类正确。', '', '## 不一致明细','', '| 房名 | 工程师分类 | 模型提议 | 模型理由 |','|---|---|---|---|']
    text += [f'| {r["name"]} | {gold[r["name"]]["category"]} | {r["category"]} | {r["reason"].replace("|","/")} |' for r in disagree]
    if not disagree:text.append('本批对照无不一致项。')
    text+=['','## 人工名称清单外的提议（部分已被关键词覆盖）','','| 房名 | 提议类别 | 理由 |','|---|---|---|']+[f'| {r["name"]} | {r["category"]} | {r["reason"].replace("|","/")} |' for r in new]
    approval_count=sum(bool(r.get('approved') and r.get('approved_by')) for r in proposals['entries'])
    deferred_count=sum(r.get('review_state')=='本阶段暂缓启用' for r in proposals['entries'])
    text+=['',f'当前提议共{len(new)}项，其中{approval_count}项已获工程师确认、{deferred_count}项暂缓启用、{len(new)-approval_count-deferred_count}项待批准。模型原输出与人工采用类别分别保留；35/49对照不因事后审批重算。']
    text+=['','新名称保存在rules/naming_proposals.yaml，未批准项不会参与用途分类。未知名称继续按现有词表处理。', '', '## 重放','', '`python -m cst naming samples/A samples/B samples/A-change --replay`','', '补充清单仅按源图哈希关联实验输入，不限制扫描新图。缺失名称增量真实调用，已缓存名称不重跑。重放核对提示词、类别定义、模型及缓存身份，无网络请求。原始49种人工分类未覆盖的名称，不计算一致率。']
    review_path=ROOT/'eval/naming-engineer-review.json'
    if review_path.is_file():
        reviewed=json.loads(review_path.read_bytes())
        text+=['','## 工程师审核', '',f"审核{reviewed['reviewed']}项："+'、'.join(f'{k}{v}项' for k,v in reviewed['responses'].items())+'。启用与暂缓按逐项记录执行；人工修正不计为模型直接判断正确。', '', '[完整审核明细](naming-engineer-review.json)']
    (ROOT/'eval/llm_naming.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
    (ROOT/'eval/llm_naming_results.json').write_text(json.dumps({'schema_version':'naming-eval.v1','names':names,'gold_total':len(gold),'compared':len(compared),'agree':len(compared)-len(disagree),'disagreements':disagree,'new_proposals':new,'missing_gold':sorted(set(gold)-set(names)),'rows':rows,'cache_ids':cache_ids,'model':config['model'],'request_count':attempts},ensure_ascii=False,indent=2),encoding='utf-8')
    return {'names':len(names),'gold_total':len(gold),'compared':len(compared),'agree':len(compared)-len(disagree),'new_proposals':len(new),'network_used':not replay,'cache_ids':cache_ids}
