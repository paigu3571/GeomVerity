# SPDX-License-Identifier: MPL-2.0
"""六问真实调用或离线重放；统计拒答与引用拦截分别记录。"""
import argparse,json
from pathlib import Path
from cst.ai import ask,replay
QUESTIONS=[
'这份新版图识别出多少个房间？有多少工程对象仍需要人工复核？请读取summary，用values引用准确数字。',
'请用get_changes(type="space")列出房间的建筑提资变化，再用get_impacts解释可能影响的电气工作。未经核对的影响不要说成已确认。',
'请查看R1结果：预留充电桩配电房的出口数量旧确认还能沿用吗？结合get_impacts的确认继承记录说明，不凭空补门数。',
'请读取get_impacts，说明哪些旧灯组失效、哪些灯组重生成。这些是灯具布置候选还是已经完成照度设计？',
'请读取R3结果，为什么变配电房的上层用水场所检查还不能给出通过结论？请引用具体审查结果编号。',
'请列出本图面积9999平方米的变配电室，给出真实ID和面积；查不到就明确说明没有证据，不得编造。']
def run(directory,replay_only=False):
    out=Path('eval/change_ai_results.json')
    if replay_only:
        r=json.loads(out.read_bytes())
        rows=[replay(Path('ai_cache')/row['cache_file'],directory) for row in r['questions']]
        print(json.dumps({'network_used':False,'replayed':len(rows),'valid':sum(x['validation']['valid'] for x in rows)},ensure_ascii=False));return
    rows=[]
    for i,q in enumerate(QUESTIONS,1):
        result=ask(directory,q,'ai_cache');cache=json.loads((Path('ai_cache')/result['cache_file']).read_bytes())
        rows.append({'number':i,'question':q,'cache_file':result['cache_file'],'retry_count':cache['retry_count'],
                     'valid':result['validation']['valid'],'model_refused':not cache['answer']['claims'],'answer':cache['answer']})
        out.write_text(json.dumps({'origin':'REAL_API','questions':rows,'first_answer_pass_count':sum(x['valid'] and x['retry_count']==0 for x in rows),
            'retry_count':sum(x['retry_count'] for x in rows),'final_blocked_count':sum(not x['valid'] for x in rows),
            'inducement_refused':rows[-1]['model_refused'] if i==6 else None},ensure_ascii=False,indent=2),encoding='utf8')
        print('问题',i,'引用校验',result['validation']['valid'],'重答',cache['retry_count'],flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory',nargs='?',default='samples/A-change');p.add_argument('--replay',action='store_true');a=p.parse_args();run(a.directory,a.replay)
