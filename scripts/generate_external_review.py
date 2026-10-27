# SPDX-License-Identifier: MPL-2.0
"""W13公开样例外部复核：准备离线，正式生成须维护者批准提示词。"""
import argparse
import hashlib
import json
import os
import httpx
from datetime import datetime, timezone
from pathlib import Path
import yaml
from cst import api
from cst.model import FILENAMES

ROOT=Path(__file__).resolve().parents[1]
PROMPTS=[
    '请依据以下公开图纸两版的文字摘要，写一份给建筑机电工程师的改图复核意见。分清已知事实、影响候选和待核实事项，保留你使用的对象或变化编号。只能使用摘要，不使用工具。不要补造尺寸、面积或工程师确认。',
    '你收到一份公开图纸换版摘要。请按变化、可能影响、待办复核事项组织一份自然语言复核意见，引用相关编号；请自行判断摘要支持到什么程度。不得调用工具，不得把资料缺失当作通过，不要编造专业规范。',
    '请根据下列文字摘要，为项目工程师写一份换版交接复核意见，关注旧版结论和确认是否仍可适用，并说明依据与不确定性。引用摘要中的编号；不使用工具，不生成或假设工程师签字。'
]


def check_public(directory):
    manifest=json.loads((directory/'manifest.json').read_bytes())
    if manifest.get('sanitized') is not True:raise ValueError('只接受有清理清单的公开样例')
    hashes={}
    for stem in FILENAMES.values():
        path=directory/stem
        if not path.is_file():path=directory/(stem+'.gz')
        actual=hashlib.sha256(path.read_bytes()).hexdigest()
        if manifest.get('files',{}).get(path.name,{}).get('sha256')!=actual:
            raise ValueError('公开样例文件与清理清单不一致')
        hashes[path.name]=actual
    return hashes


def render_summary(delta):
    lines=['公开样例A→A-change；调用者提供同一图纸两版；不是DWG原图。',
           '旧版哈希：'+delta['old_hash'],'新版哈希：'+delta['new_hash'],
           '变化对象数：'+str(delta['change_count']),
           '影响为已识别范围候选，不保证覆盖未识别对象。以下为工具的摘要记录，不是模型已经核验的结论。']
    for change in delta['changes']:
        lines.append('变化编号：'+change['id']+'；类别：'+'、'.join(change['kinds']))
        for key,label in [('old','旧'),('new','新')]:
            ref=change.get(key)
            lines.append(label+'对象：'+json.dumps(ref,ensure_ascii=False) if ref else label+'对象：无对应记录')
        lines.append('影响记录：'+json.dumps(change['impact'],ensure_ascii=False))
        lines.append('工作建议（是否批准='+str(change['suggested_work']['approved'])+'）：'+'；'.join(change['suggested_work']['items']))
    lines.append('决策确认继承：'+json.dumps(delta.get('decision_inheritance',[]),ensure_ascii=False))
    lines.append('房间输入复核继承：'+json.dumps(delta.get('review_inheritance',[]),ensure_ascii=False))
    return '\n'.join(lines)


def prepare(output):
    old,new=ROOT/'samples/A',ROOT/'samples/A-change'
    hashes={'A':check_public(old),'A-change':check_public(new)}
    output=Path(output)
    if (output/'preparation.json').exists():raise ValueError('已有准备记录，请使用新输出目录以保留历史')
    output.mkdir(parents=True,exist_ok=True)
    api.diff(old,new,output/'comparison')
    raw=(output/'comparison/diff.json').read_bytes()
    summary=render_summary(json.loads(raw))
    (output/'summary.txt').write_text(summary,encoding='utf-8')
    config=yaml.safe_load((ROOT/'python/cst/ai_config.yaml').read_text(encoding='utf-8'))
    requests=[]
    for index,prompt in enumerate(PROMPTS,1):
        request={'model':config['model'],'temperature':config['temperature'],'max_tokens':config['max_tokens'],
                 'thinking':{'type':config['thinking']},
                 'messages':[{'role':'system','content':'你是改图复核意见撰写助手，只使用所给纯文字摘要，不能访问工具或外部资料。'},
                             {'role':'user','content':prompt+'\n\n'+summary}]}
        name=f'proposed-request-{index}.json'
        (output/name).write_text(json.dumps(request,ensure_ascii=False,indent=2),encoding='utf-8')
        requests.append(name)
    record={'stage':'PREPARED_NOT_GENERATED','network_used':False,'approval':'待张田确认提示词',
            'prepared_at_utc':datetime.now(timezone.utc).isoformat(),'model_from_config':config['model'],
            'dataset_sha256':hashes,'comparison_sha256':hashlib.sha256(raw).hexdigest(),
            'summary_sha256':hashlib.sha256(summary.encode()).hexdigest(),'summary_hash_mode':'UTF8_LF','proposed_requests':requests,
            'notice':'没有读取API Key，没有模型回复，不计为真实样本。批准后另行实现正式生成及原始请求/响应留存。'}
    (output/'preparation.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    return record

def generate(preparation, approval):
    """只发送已批准的三个提问；每个请求最多调用一次，不以工具核验纠错回复。"""
    directory=Path(preparation)
    record=json.loads((directory/'preparation.json').read_bytes())
    if not approval.strip():raise ValueError('需要记录维护者对本次三份提示词的批准')
    if record['stage']!='PREPARED_NOT_GENERATED':raise ValueError('不是待生成的准备记录')
    summary=(directory/'summary.txt').read_text(encoding='utf-8').encode('utf-8')
    comparison=(directory/'comparison/diff.json').read_bytes()
    if hashlib.sha256(summary).hexdigest()!=record['summary_sha256'] or hashlib.sha256(comparison).hexdigest()!=record['comparison_sha256']:
        raise ValueError('冻结摘要或比较结果发生变化，须重新准备并确认')
    if record['dataset_sha256']!={'A':check_public(ROOT/'samples/A'),'A-change':check_public(ROOT/'samples/A-change')}:
        raise ValueError('公开输入发生变化，须重新准备并确认')
    config=yaml.safe_load((ROOT/'python/cst/ai_config.yaml').read_text(encoding='utf-8'))
    if record['proposed_requests']!=[f'proposed-request-{i}.json' for i in range(1,4)]:raise ValueError('准备请求清单异常')
    requests=[]
    for index,name in enumerate(record['proposed_requests']):
        request=json.loads((directory/name).read_bytes())
        expected={'model':config['model'],'temperature':config['temperature'],'max_tokens':config['max_tokens'],
                  'thinking':{'type':config['thinking']},'messages':[
                  {'role':'system','content':'你是改图复核意见撰写助手，只使用所给纯文字摘要，不能访问工具或外部资料。'},
                  {'role':'user','content':PROMPTS[index]+'\n\n'+summary.decode('utf-8')}]}
        if request!=expected:raise ValueError('请求与已批准提示词、摘要或配置不一致')
        requests.append(request)
    key=os.getenv('DEEPSEEK_API_KEY')
    if not key:raise ValueError('未设置DEEPSEEK_API_KEY，未调用模型')
    results=[]
    for index,request in enumerate(requests,1):
        sample=directory/f'sample-{index}'
        if sample.exists():raise ValueError('样本目录已存在，拒绝重复调用或覆盖；逐份检查原始记录')
    for index,request in enumerate(requests,1):
        sample=directory/f'sample-{index}';sample.mkdir()
        request_bytes=json.dumps(request,ensure_ascii=False,indent=2).encode('utf-8')
        (sample/'request.json').write_bytes(request_bytes)
        meta={'origin':'REAL_API','approval':approval,'request_sha256':hashlib.sha256(request_bytes).hexdigest(),
              'dataset_sha256':record['dataset_sha256'],'summary_sha256':record['summary_sha256'],
              'comparison_sha256':record['comparison_sha256'],'summary_hash_mode':'UTF8_LF','model_requested':request['model'],
              'started_at_utc':datetime.now(timezone.utc).isoformat(),'network_used':True,'tools_enabled':False,
              'response_modified':False,'retry_count':0,'status':'attempted'}
        try:
            with httpx.Client(timeout=180.0) as client:
                response=client.post(config['base_url']+'/chat/completions',headers={'Authorization':'Bearer '+key},json=request)
            # 不保存Authorization头；失败体不输出到控制台。
            (sample/'response.raw.json').write_bytes(response.content)
            meta['http_status']=response.status_code
            meta['response_sha256']=hashlib.sha256(response.content).hexdigest()
            response.raise_for_status()
            raw=response.json();choice=raw['choices'][0];message=choice['message']
            meta.update(model_returned=raw.get('model'),finish_reason=choice.get('finish_reason'),usage=raw.get('usage'))
            content=message.get('content')
            complete=choice.get('finish_reason')=='stop' and isinstance(content,str) and bool(content.strip()) and not message.get('tool_calls')
            meta['status']='complete' if complete else 'incomplete'
            if isinstance(content,str):(sample/'response.txt').write_text(content,encoding='utf-8')
        except Exception as exc:
            meta['status']='failed';meta['error_type']=type(exc).__name__
        meta['finished_at_utc']=datetime.now(timezone.utc).isoformat()
        (sample/'record.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
        results.append({'sample':sample.name,'status':meta['status'],'model_returned':meta.get('model_returned')})
    result={'origin':'REAL_API','approval':approval,'samples':results,'complete_count':sum(r['status']=='complete' for r in results)}
    (directory/'generation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='准备公开摘要；维护者批准提示词后可显式生成，不启用工具')
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare',action='store_true',help='只准备，不联网')
    mode.add_argument('--generate',metavar='PREPARATION_DIR',help='从冻结的准备目录生成，仅限维护者已明确批准')
    parser.add_argument('--approval',default='',help='本轮维护者批准记录（不接受模型自我批准）')
    parser.add_argument('--output',default='dist/external-samples/preparation')
    args=parser.parse_args()
    result=prepare(args.output) if args.prepare else generate(args.generate,args.approval)
    print(json.dumps(result,ensure_ascii=False,indent=2))
