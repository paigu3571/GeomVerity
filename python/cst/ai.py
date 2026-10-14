# SPDX-License-Identifier: MPL-2.0
"""五个只读工具、有限引用校验、带真实/合成标签的缓存；不声称校验所有自然语言。"""
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import httpx
import yaml
from pydantic import Field
from .model import Model,load,L2
from .summary import summary
from .gold import area_m2

class Claim(Model):
    text:str
    object_ids:list[str]
    values:dict[str,str|int|float|bool|None]

class Answer(Model):
    claims:list[Claim]
    reason:str|None=None

class ReadTools:
    def __init__(self,directory,changes=None):
        self.changes_path=Path(changes) if changes else Path(directory)/'changes.json'
        if not self.changes_path.is_file() and self.changes_path.with_name(self.changes_path.name+'.gz').is_file():self.changes_path=self.changes_path.with_name(self.changes_path.name+'.gz')
        self.changes_data=None
        if self.changes_path.is_file():
            self.changes_data=json.loads(self.changes_bytes())
            if self.changes_data.get('new_hash')!=load(directory).drawing.sha256:raise ValueError('变更结果不对应当前扫描')
        self.directory=Path(directory); self.data=load(directory)
        self.objects={o.semantic_id:o for o in self.data.objects};self.facts=None;self.findings=({f['id']:f for f in self.changes_data['new_check']['findings']} if self.changes_data else None)
    def changes_bytes(self):
        payload=self.changes_path.read_bytes()
        return gzip.decompress(payload) if self.changes_path.name.endswith('.gz') else payload
    def summary(self):
        value=summary(self.data)
        value['space_count']=value['objects_by_type'].get('space',0)
        value['review_object_count']=value['object_status'].get('review',0)
        return value
    def list_objects(self,type=None,use=None,status=None,offset=0,limit=20):
        if not isinstance(offset,int) or not isinstance(limit,int) or offset<0 or not 1<=limit<=100:raise ValueError('分页参数无效')
        objs=[o for o in self.data.objects if (type is None or o.type==type) and (use is None or o.use_code==use) and (status is None or o.status==status)]
        return {'total':len(objs),'offset':offset,'items':[self.get_object(o.semantic_id) for o in objs[offset:offset+limit]]}
    def get_object(self,id):
        o=self.objects.get(id)
        if o is None:return {'error':'对象ID不存在','id':id}
        if self.facts is None:self.facts={f.geometry_id:f for f in load(self.directory,L2).facts}
        area=area_m2(o,self.facts)
        return {'id':id,'type':o.type,'name':o.raw_label,'use':o.use_code,'status':o.status,'handle':o.source.handle,
                'area_m2':None if area == '' else area,'confidence':o.confidence}
    def get_evidence(self,id):
        o=self.objects.get(id)
        if o is None:return {'error':'对象ID不存在','id':id}
        return {'id':id,'source':o.source.model_dump(),'evidence':[e.model_dump() for e in o.evidence],
                'note':'证据存在不证明识别正确；完整引用可用verify核对'}
    def _findings(self):
        if self.findings is None:
            from .l4 import check
            self.findings={f['id']:f for f in check(self.directory)['findings']}
        return self.findings
    def list_findings(self,rule_id=None,result=None,offset=0,limit=20):
        if not isinstance(offset,int) or not isinstance(limit,int) or offset<0 or not 1<=limit<=100:raise ValueError('分页参数无效')
        rows=[f for f in self._findings().values() if (rule_id is None or f['rule_id']==rule_id) and (result is None or f['result']==result)]
        return {'total':len(rows),'offset':offset,'items':[self._finding_reference(f) for f in rows[offset:offset+limit]]}
    def _finding_reference(self,f):
        return {k:f[k] for k in ('id','rule_id','result','reason','input_confidence','object_ids','source_handles','values')} | {'status':'accepted' if f['input_confidence']=='输入已确认' else 'review'}
    def get_changes(self,offset=0,limit=20,type=None):
        if not isinstance(offset,int) or not isinstance(limit,int) or offset<0 or not 1<=limit<=100:raise ValueError('分页参数无效')
        if self.changes_data is None:return {'total':0,'items':[],'reason':'未提供两版变更结果'}
        rows=[c for c in self.changes_data['changes'] if type is None or (c['new'] or c['old'])['type']==type]
        return {'total':len(rows),'offset':offset,'items':[self._change_reference(c) for c in rows[offset:offset+limit]]}
    def _change_reference(self,c):
        o=c['new'] or c['old']
        return {'id':c['id'],'name':o['name'],'type':o['type'],'change_type':'、'.join(c['kinds']),
                'old_handle':(c['old'] or {}).get('handle'),'new_handle':(c['new'] or {}).get('handle'),
                'result':c['impact']['result'],'status':'review','old':c['old'],'new':c['new'],'priorities':c.get('priorities',[])}
    def get_impacts(self,change_id=None,offset=0,limit=20):
        page=self.get_changes(offset,limit)
        if self.changes_data is None:return page
        rows=self.changes_data['changes']
        if change_id is not None:rows=[c for c in rows if c['id']==change_id]
        page_rows=rows[offset:offset+limit]
        room_ids={r['id'] for c in page_rows for r in c['impact']['rooms']}|{ref['id'] for c in page_rows for ref in (c['old'],c['new']) if ref}
        return {'total':len(rows),'offset':offset,'items':[{'id':'impact_'+c['id'],'change_id':c['id'],
            'result':c['impact']['result'],'rooms':c['impact']['rooms'],'scope':c['impact']['scope'],
            'suggested_work':c['suggested_work'],'status':'review'} for c in page_rows],
            'review_inheritance':[r for r in self.changes_data['review_inheritance'] if r.get('old_room') in room_ids or r.get('new_room') in room_ids],
            'lighting_changes':[r for r in self.changes_data['lighting_changes'] if r.get('old_room_id') in room_ids or r.get('new_room_id') in room_ids]}
    def call(self,name,args):
        if name not in {'summary','list_objects','get_object','get_evidence','list_findings','get_changes','get_impacts'}:raise ValueError('未授权工具')
        return getattr(self,name)(**args)
    def truth(self,answer):
        objects={}
        for claim in answer.get('claims',[]):
            for id in claim.get('object_ids',[]):
                if id.startswith('change_') and self.changes_data:
                    row=next((c for c in self.changes_data['changes'] if c['id']==id),None)
                    if row:objects[id]=self._change_reference(row)
                elif id.startswith('impact_change_') and self.changes_data:
                    row=self.get_impacts(id.removeprefix('impact_'))['items']
                    if row:objects[id]=row[0]
                elif id in self.objects:objects[id]=self.get_object(id)
                elif id.startswith('finding_') and id in self._findings():objects[id]=self._finding_reference(self._findings()[id])
        return {'objects':objects,'summary':self.summary()}

DEFINITIONS=[
 *[{'type':'function','function':{'name':n,'description':'读取已有真实两版变更或影响；ID可引用，候选不能称已确认','parameters':{'type':'object','properties':({'change_id':{'type':'string'}} if n=='get_impacts' else {'type':{'type':'string'}})|{'offset':{'type':'integer'},'limit':{'type':'integer'}},'additionalProperties':False}}} for n in ['get_changes','get_impacts']],
 {'type':'function','function':{'name':'list_findings','description':'读取实际辅助审查结果与缺资料原因，result仅通过/不通过/无法判定；可引用结果id，不把候选当确认','parameters':{'type':'object','properties':{'rule_id':{'type':'string'},'result':{'type':'string','enum':['通过','不通过','无法判定','不适用']},'offset':{'type':'integer'},'limit':{'type':'integer'}},'additionalProperties':False}}},
 {'type':'function','function':{'name':'summary','description':'读取实际对象和状态统计','parameters':{'type':'object','properties':{},'additionalProperties':False}}},
 {'type':'function','function':{'name':'list_objects','description':'按L3类型/用途/状态读取分页对象','parameters':{'type':'object','properties':{'type':{'type':'string'},'use':{'type':'string'},'status':{'type':'string'},'offset':{'type':'integer'},'limit':{'type':'integer'}},'additionalProperties':False}}},
 *[{'type':'function','function':{'name':name,'description':'读取已有对象，不编造ID','parameters':{'type':'object','properties':{'id':{'type':'string'}},'required':['id'],'additionalProperties':False}}} for name in ['get_object','get_evidence']],
]

def affirmative(text,pattern):
    """有限措辞检查：否定句不是肯定；转折后的新断言仍要检查。"""
    for match in re.finditer(pattern,text):
        prefix=re.split(r'[，,。；;！？!?\n]|但是|然而|不过|但',text[:match.start()])[-1][-18:]
        if not re.search(r'无法|不能|不足以|尚未|未|没有|并非|不是|不应|不宜|不可|不代表|不意味着|不等于',prefix):
            return True
    return False

def validate(answer,truth):
    errors=[]
    try: parsed=Answer.model_validate(answer)
    except ValueError:return {'valid':False,'errors':['回答不符合claims结构']}
    for claim in parsed.claims:
        referenced=[]
        for id in claim.object_ids:
            if id not in truth['objects']:errors.append('编造或不存在对象ID：'+id)
            else:referenced.append(truth['objects'][id])
        if not claim.object_ids and not any(k.startswith('summary.') for k in claim.values):errors.append('陈述没有可核对引用')
        for key,value in claim.values.items():
            owner,_,field=key.rpartition('.')
            if owner=='summary':source=truth.get('summary',{})
            elif owner in claim.object_ids:source=truth['objects'].get(owner,{})
            else:source={}
            if field not in source:errors.append('未知或未引用字段：'+key);continue
            expected=source[field]
            if type(value) in (int,float) and type(expected) in (int,float):
                equal=math.isclose(value,expected,rel_tol=0,abs_tol=1e-6)
            else:equal=type(value)==type(expected) and value==expected
            if not equal:errors.append('数值或状态不一致：'+key)
        if any(o.get('status')!='accepted' for o in referenced) and affirmative(claim.text,'已确认|确认无误|确定合规'):errors.append('将Review/未确认输入说成已确认')
        if any(o.get('result')=='无法判定' for o in referenced) and affirmative(claim.text,'已通过|判定通过|审查通过'):errors.append('将无法判定说成通过')
    return {'valid':not errors,'errors':errors,'scope':'核查结构化引用/数值/状态及有限措辞，不能证明所有自然语言陈述正确'}

def replay(path,directory=None):
    record=json.loads(Path(path).read_bytes())
    if record.get('origin')=='SYNTHETIC':
        return {'origin':'SYNTHETIC','network_used':False,'cases':[{'name':c['name'],'expected_valid':c['expected_valid'],**validate(c['answer'],record['ground_truth'])} for c in record['cases']]}
    if record.get('origin')!='REAL_API':raise ValueError('缓存缺少真实/合成来源标记')
    tools=ReadTools(directory)
    file=tools.directory/'building-semantics.v1.json'
    if not file.is_file():file=file.with_name(file.name+'.gz')
    if hashlib.sha256(file.read_bytes()).hexdigest()!=record['dataset_sha256']:raise ValueError('缓存与本次数据不对应，请选择匹配缓存')
    if record.get('changes_sha256') and (not tools.changes_path.is_file() or hashlib.sha256(tools.changes_bytes()).hexdigest()!=record['changes_sha256']):raise ValueError('缓存与变更结果不对应')
    return {'origin':'REAL_API','network_used':False,'answer':record['answer'],'validation':validate(record['answer'],tools.truth(record['answer']))}

def ask(directory,question,cache_dir):
    key=os.getenv('DEEPSEEK_API_KEY')
    if not key:raise ValueError('未设置DEEPSEEK_API_KEY；真实API未调用，不能用合成缓存冒充')
    directory=Path(directory)
    manifest=json.loads((directory/'manifest.json').read_bytes())
    if not manifest.get('sanitized'):raise ValueError('本次只发送有清理清单的公开样例')
    config=yaml.safe_load(Path(__file__).with_name('ai_config.yaml').read_text(encoding='utf-8'))
    tools=ReadTools(directory)
    messages=[{'role':'system','content':'只能依据只读工具。返回JSON对象，格式{claims:[{text,object_ids:[],values:{}}],reason:null}。values键为<对象ID>.<字段>或summary.space_count。对象或审查结果ID必须来自工具；可用list_findings得到结果id及result/reason等字段；get_changes(type=space)读取房间变更，get_impacts读取影响、旧确认和灯组失效；可引用change_或impact_change_结果id及其标量字段。Review只能说待复核，无法判定不能说通过。无法找到对象时claims为空并说明原因。'}, {'role':'user','content':question}]
    transcript=[];answer=None;validation=None;retries=0
    with httpx.Client(timeout=45.0) as client:
        for round_no in range(config['max_tool_rounds']+3):
            request={'model':config['model'],'messages':messages,'tools':DEFINITIONS,'temperature':0,'max_tokens':config['max_tokens'],'thinking':{'type':config['thinking']},'response_format':{'type':'json_object'}}
            response=client.post(config['base_url']+'/chat/completions',headers={'Authorization':'Bearer '+key},json=request)
            response.raise_for_status();raw=response.json()
            transcript.append({'request':json.loads(json.dumps(request)),'response':raw})
            msg=raw['choices'][0]['message'];messages.append(msg)
            if msg.get('tool_calls'):
                if round_no>=config['max_tool_rounds']:raise ValueError('只读工具轮次达到预算，请缩短问题')
                for call in msg['tool_calls']:
                    result=tools.call(call['function']['name'],json.loads(call['function']['arguments']))
                    messages.append({'role':'tool','tool_call_id':call['id'],'content':json.dumps(result,ensure_ascii=False)})
                continue
            try:answer=json.loads(msg.get('content') or '{}')
            except json.JSONDecodeError:answer={}
            validation=({'valid':False,'errors':['输出被截断（finish_reason=length），不能作为完整回答']} if raw['choices'][0].get('finish_reason')=='length' else validate(answer,tools.truth(answer)))
            if validation['valid'] or retries>=2:break
            retries+=1;messages.append({'role':'user','content':'引用校验失败，请重答JSON：'+json.dumps(validation['errors'],ensure_ascii=False)})
    if answer is None:raise ValueError('预算内未得到最终回答')
    file=directory/'building-semantics.v1.json'
    if not file.is_file():file=file.with_name(file.name+'.gz')
    dataset_hash=hashlib.sha256(file.read_bytes()).hexdigest()
    changes_hash=hashlib.sha256(tools.changes_bytes()).hexdigest() if tools.changes_path.is_file() else None
    cache_id=hashlib.sha256((dataset_hash+str(changes_hash)+config['model']+question).encode()).hexdigest()[:24]
    cache=Path(cache_dir)/f'{cache_id}.json';cache.parent.mkdir(parents=True,exist_ok=True)
    record={'origin':'REAL_API','model':config['model'],'dataset_sha256':dataset_hash,'changes_sha256':changes_hash,'question':question,'transcript':transcript,'answer':answer,'validation':validation,'retry_count':retries}
    cache.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    return {'origin':'REAL_API','cache_file':cache.name,'answer':answer,'validation':validation,'display':'正常' if validation['valid'] else '标红：引用校验仍未通过'}
