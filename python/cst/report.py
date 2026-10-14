# SPDX-License-Identifier: MPL-2.0
"""A single offline report; real evidence and missing inputs remain visible."""
from html import escape
from pathlib import Path
from .l4 import check
from .model import load

def e(value):return escape(str(value),quote=True)

def write_report(directory,output=None):
    directory=Path(directory);result=check(directory);data=load(directory)
    objects={o.semantic_id:o for o in data.objects}
    output=Path(output) if output else directory/'l4_report.html';output.parent.mkdir(parents=True,exist_ok=True)
    body='<h1>电气机房条件辅助审查</h1><p>从CAD工程语义到规则结果，再回到图中来源。</p>'
    body+='<p class="notice">本报告为设计辅助审查，不替代设计人员与审图机构的判断。</p>'
    body+=f'<p>真实数据 · 语义版本 {e(data.producer_version)} · 来源摘要 <code>{e(data.drawing.sha256)}</code></p>'
    body+='<p>L3待复核状态与工程师局部核对分别显示；不适用不计为通过。</p><div class="stats">'
    for title,result_name in [('需复核风险','不通过'),('已满足（候选）','通过'),('资料缺口与提资问题','无法判定')]:
        rows=[f for f in result['findings'] if f['result']==result_name]
        body+=f'<div><strong>{len(rows)}</strong><span>{title}</span><ul>'
        for f in rows:
            body+=f'<li><a href="#{e(f["id"])}">{e(f.get("object_name",f.get("rule_title",f["rule_id"])))}</a>'
            if f.get('request_question'):body+=f'<p>{e(f["request_question"])}</p>'
            body+='</li>'
        body+='</ul></div>'
    body+='</div><h2>规则汇总</h2><table><tr><th>规则</th><th>批准范围</th><th>结论数量</th></tr>'
    for rule in result['rules']:
        counts={name:sum(f['rule_id']==rule['id'] and f['result']==name for f in result['findings']) for name in ('通过','不通过','无法判定','不适用')}
        body+=f'<tr><td>{e(rule["id"])}</td><td>{"辅助检查范围已确认" if rule["approved"] else "未批准"}</td><td>{e(counts)}</td></tr>'
    body+='</table><h2>逐条查看</h2><p>点击房名展开数值、定位轮廓、图元Handle及条文。</p>'
    for f in result['findings']:
        body+=f'<details id="{e(f["id"])}"><summary><b>{e(f.get("rule_title",f["rule_id"]))}</b> {e(f.get("object_name","没有纳入的对象"))}<span class="badge" data-result="{e(f["result"])}">{e(f["result"])}</span></summary>'
        body+=f'<p>{e(f["reason"])}</p><p>{e(f["input_confidence"])} · {e(f["level"])} · {e(f["scope"])}</p>'
        review=f['engineer_reviewed']
        body+=f'<p>工程师复核：{e(review["reviewed_by"] or "尚未复核")} · {e(review["reviewed_date"] or "")} · {e(review["record_file"] or "无记录")}</p>'
        if f.get('request_question'):body+=f'<p class="notice">提资问题：{e(f["request_question"])}</p>'
        v=f['values']
        if v.get('candidate_dimensions'):
            d=v['candidate_dimensions'];body+=f'<p>轮廓外包矩形候选长边 <b>{d["long_side_m"]:.3f} m</b>，短边 {d["short_side_m"]:.3f} m；{e(d["method"])}</p>'
        if 'candidate_opening_count' in v:body+=f'<p>去重门洞候选 <b>{v["candidate_opening_count"]}</b> 个，不能当作已确认有效出口。Handle：{e(", ".join(v["candidate_opening_handles"]))}</p>'
        if 'opening_candidate_audit' in v:
            body+=f'<p>原关系 {v["raw_opening_relation_count"]} 条 → 重合去重 {v["coincident_opening_count"]} 处 → 近边候选 {v["candidate_opening_count"]} 处。</p><table><tr><th>Handle</th><th>重复记录</th><th>距实际轮廓mm</th><th>L4处理</th></tr>'
            for row in v['opening_candidate_audit']:
                body+=f'<tr><td>{e(row["handle"])}</td><td>{len(row["object_ids"])}</td><td>{e(row["boundary_distance_mm"])}</td><td>{e(row["reason"])}</td></tr>'
            body+='</table>'
        if v.get('manual_confirmation'):
            m=v['manual_confirmation']
            body+=f'<p class="notice">工程师 {e(m["reviewed_by"])} 于 {e(m["reviewed_date"])} 人工核对：室内净长是否超过7米：{"是" if m["net_length_gt_7"] else "否"}；实际出入口 {m["entrance_count"]} 处。{e(m["note"])}</p>'
        if 'adjacent_candidates' in v:
            text='；'.join(n['name']+f'（隔墙重叠{n["overlap_mm"]:.1f}mm，墙Handle {n["wall_handle"]}）'+(' · 用水候选' if n['water_candidate'] else '') for n in v['adjacent_candidates'])
            body+='<p>隔墙贴邻候选：'+e(text or '未找到；关系覆盖不足，不能证明没有贴邻')+'</p>'
            body+=f'<p class="muted">{e(v["adjacency_method"])}</p>'
        if f['object_ids']:
            obj=objects.get(f['object_ids'][0]);g=obj.geometry if obj else None
            if g and g.bounds.is_valid:
                b=g.bounds;w=b.max_x-b.min_x;h=b.max_y-b.min_y;pad=max(w,h)*0.05
                if w>0 and h>0:
                    body+=f'<svg role="img" aria-label="来源空间轮廓示意" viewBox="{-pad} {-pad} {w+2*pad} {h+2*pad}" style="width:100%;max-height:240px;background:#eef3f8">'
                    for path in g.paths:
                        pts=' '.join(f'{p.x-b.min_x:.4f},{b.max_y-p.y:.4f}' for p in path)
                        body+=f'<polygon points="{pts}" fill="#d7e8ff" stroke="#1c56a0" stroke-width="{max(w,h)/200}"/>'
                    body+='</svg><p class="muted">原识别轮廓定位示意，不是室内净长证明。</p>'
        else:body+='<p>没有已识别的适用对象，不能显示对应Handle。</p>'
        for sub in f.get('subchecks',[]):body+=f'<p>隔墙防水（{e(sub["strength"])}）：{e(sub["result"])}，{e(sub["reason"])}</p><p>{e(sub.get("request_question",""))}</p>'
        body+='<h3>来源追溯</h3>'
        for item in f['evidence']:
            body+=f'<details class="chain"><summary>对象 <code>{e(item["object_id"])}</code> · Handle <b>{e(item["source_handle"])}</b></summary>'
            for chain in item['chains']:
                body+=f'<p>L3 <code>{e(chain["l3_id"])}</code> → L2 <code>{e(chain["l2_id"])}</code> · {"引用完整" if chain["complete"] else "断链，需检查"}</p>'
                body+='<table><tr><th>L1图元</th><th>源图Handle</th></tr>'
                for p in chain['l1_sources']:body+=f'<tr><td><code>{e(p["l1_id"])}</code></td><td>{e(p["handle"] or "缺失")}</td></tr>'
                body+='</table>'
            body+='</details>'
        body+='<h3>规范引用</h3>'
        for clause in f['clauses']:body+=f'<p><b>{e(clause["code"])} · {e(clause["article"])} · {e(clause["strength"])}</b><br>{e(clause["text"])}</p>'
        body+='</details>'
    css='body{font:16px/1.65 "Microsoft YaHei",sans-serif;color:#21334c;background:#f5f7fb;margin:0}main{max-width:1060px;margin:auto;padding:28px}h1{font-size:29px;margin:0}h2{font-size:21px;margin-top:30px}.notice{padding:12px 16px;background:#fff0ce;border-left:4px solid #cd9100}.stats{display:flex;align-items:flex-start;gap:16px;margin:20px 0}.stats div{flex:1;overflow-wrap:anywhere;background:white;padding:14px 24px;border-radius:10px;min-width:90px}.stats strong{display:block;font-size:30px}.stats span,.muted{color:#65758c}table{width:100%;border-collapse:collapse;background:white;margin:12px 0}td,th{text-align:left;border-bottom:1px solid #e0e6ed;padding:10px;overflow-wrap:anywhere}details{background:white;border:1px solid #dae2ec;border-radius:10px;margin:12px 0;padding:14px}summary{cursor:pointer;min-height:30px}.badge{float:right;background:#fff0ce;padding:1px 10px;border-radius:5px}.badge[data-result="通过"]{background:#d9f1e3}.badge[data-result="不通过"]{background:#fbe0df}.chain{background:#f7faff}code{font-size:12px;overflow-wrap:anywhere}svg{border-radius:8px}@media(max-width:600px){main{padding:14px}.stats{gap:7px}.stats div{padding:10px;min-width:60px}h1{font-size:24px}.stats{flex-direction:column}.stats div{width:100%;box-sizing:border-box}.badge{float:none;margin-left:10px}}'
    html='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>电气机房条件辅助审查</title><style>'+css+'</style><main>'+body+'</main></html>'
    output.write_text(html,encoding='utf-8')
    return {'output':output.as_posix(),'findings':len(result['findings']),'summary':result['summary'],'network_required':False}
