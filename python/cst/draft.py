# SPDX-License-Identifier: MPL-2.0
"""Bounded rule drafting: human approval remains independent of model output."""
import hashlib
import json
import os
from pathlib import Path
from typing import Literal
import httpx
import yaml
from pydantic import model_validator
from .model import Model
from .rules import Rule

class DraftAnswer(Model):
    status: Literal['draft','needs_new_predicate']
    reason: str
    rule: Rule | None
    @model_validator(mode='after')
    def gate(self):
        if self.status=='draft':
            if self.rule is None:raise ValueError('缺少规则草案')
            if self.rule.approved or self.rule.approved_by:raise ValueError('AI不得自行审批')
        elif self.rule is not None:raise ValueError('无法表达时不得硬凑规则')
        return self

def validate_draft(answer,text,code,article):
    parsed=DraftAnswer.model_validate(answer)
    if parsed.rule:
        if len(parsed.rule.clauses)!=1:raise ValueError('此入口每次只起草给定的一条正文')
        clause=parsed.rule.clauses[0]
        if (clause.text,clause.code,clause.article)!=(text,code,article):raise ValueError('原文或规范引用被改写，需重答')
    return parsed

def save_draft(parsed,text,code,article,output):
    if parsed.status!='draft':return {'status':parsed.status,'reason':parsed.reason,'output':None}
    token=hashlib.sha256((text+'|'+code+'|'+article).encode()).hexdigest()[:12]
    path=Path(output)/('DRAFT_'+token+'.yaml');path.parent.mkdir(parents=True,exist_ok=True)
    if path.is_file() and yaml.safe_load(path.read_text(encoding='utf-8')).get('approved'):
        return {'status':'approved_rule_preserved','output':path.as_posix(),'approved':True,'reason':'当前文件已经工程师审批；缓存仍是未审批草案，重放不覆盖审批记录'}
    rule=parsed.rule.model_copy(update={'id':'DRAFT_'+token,'approved':False,'approved_by':None})
    path.write_text('# SPDX-License-Identifier: MPL-2.0\n'+yaml.safe_dump(rule.model_dump(),allow_unicode=True,sort_keys=False),encoding='utf-8')
    return {'status':'draft','reason':parsed.reason,'output':path.as_posix(),'approved':False,'note':'格式校验通过不是专业批准；待工程师核对条文、范围和判断条件'}

def draft_rule(text=None,code='待核',article='待核',cache=None,replay=False,output='rules/drafts'):
    if replay:
        if not cache:raise ValueError('重放需提供--cache缓存文件')
        record=json.loads(Path(cache).read_bytes())
        if record.get('origin')!='REAL_API' or record.get('kind')!='RULE_DRAFT':raise ValueError('仅重放真实规则起草缓存')
        source=record['source']
        parsed=validate_draft(record['answer'],source['text'],source['code'],source['article'])
        return {'origin':'REAL_API','network_used':False,**save_draft(parsed,**source,output=output)}
    if not text:raise ValueError('请提供条文正文')
    key=os.getenv('DEEPSEEK_API_KEY')
    if not key:raise ValueError('未设置DEEPSEEK_API_KEY；可改用--replay --cache')
    config=yaml.safe_load(Path(__file__).with_name('ai_config.yaml').read_text(encoding='utf-8'))
    prompt="""只能将一条规范起草为JSON规则，不审批。输出{status:'draft'或'needs_new_predicate',reason:'原因',rule:对象或null}。
规则对象：id,title,approved:false,approved_by:null,clauses:[{code,article,text,strength:'应'或'宜'}],applies_to:[用途],check,on_missing,scope。
规范号/条号/正文必须原样使用用户source，不猜待核引用。用途仅SUBSTATION,DISTRIBUTION_ROOM,ELECTRICAL_SHAFT,ELEVATOR_SHAFT,OTHER_SERVICE_SHAFT,HOT_FLUE,HEAT_ROOM,TOILET,BATHROOM,KITCHEN。
只有六个条件：space_use_in(values用途列表),long_side_gt(threshold房间净长米),opening_count_ge(value出入口整数),adjacent_to_use(values贴邻用途),directly_below_use(values上一层用途),shaft_shared_with(values共井用途)。不能用房间长度条件去判断电流/电压/温度。否定关系用expect:false。
check为{predicate,...}，或{when:{predicate,...},require:{predicate,...}}；禁止任意代码、多个未知条件或含糊地用相邻代替共井。
已有条件表达不了必须needs_new_predicate并rule:null。有可表达条件但缺输入属于on_missing，不新增识别模块。scope说明只是条件初查，缺资料不推定通过。"""
    source={'text':text,'code':code,'article':article}
    messages=[{'role':'system','content':prompt},{'role':'user','content':json.dumps(source,ensure_ascii=False)}]
    transcript=[];parsed=None;answer={};errors=[]
    with httpx.Client(timeout=45) as client:
        for attempt in range(3):
            request={'model':config['model'],'messages':messages,'temperature':0,'max_tokens':config['draft_max_tokens'],'thinking':{'type':config['thinking']},'response_format':{'type':'json_object'}}
            response=client.post(config['base_url']+'/chat/completions',headers={'Authorization':'Bearer '+key},json=request)
            response.raise_for_status();raw=response.json();transcript.append({'request':json.loads(json.dumps(request)),'response':raw})
            message=raw['choices'][0]['message'];messages.append(message)
            try:
                if raw['choices'][0].get('finish_reason')=='length':raise ValueError('输出被截断（finish_reason=length），不写规则')
                answer=json.loads(message.get('content') or '{}')
                parsed=validate_draft(answer,**source);break
            except ValueError as exc:
                errors.append(str(exc));messages.append({'role':'user','content':'格式校验失败，请重答：'+str(exc)})
    token=hashlib.sha256((json.dumps(source,sort_keys=True,ensure_ascii=False)+config['model']+prompt).encode()).hexdigest()[:24]
    path=Path('ai_cache')/('draft_'+token+'.json');path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({'origin':'REAL_API','kind':'RULE_DRAFT','model':config['model'],'source':source,'transcript':transcript,'answer':answer,'validation_errors':errors,'valid':parsed is not None},ensure_ascii=False,indent=2),encoding='utf-8')
    if parsed is None:raise ValueError('最多两次重答仍不合格式，保留缓存但不写规则')
    return {'origin':'REAL_API','network_used':True,'cache_file':path.as_posix(),**save_draft(parsed,**source,output=output)}
