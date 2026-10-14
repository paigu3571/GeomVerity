# SPDX-License-Identifier: MPL-2.0
"""只读真实模型缓存，生成命名覆盖对照；不调用API，不批准术语。"""
import csv,json
from pathlib import Path
import yaml

root=Path(__file__).resolve().parents[1]
table=yaml.safe_load((root/'rules/space-uses.draft.yaml').read_text(encoding='utf-8'))
experiment=json.loads((root/'eval/llm_naming_results.json').read_bytes())
records={}
for path in sorted((root/'ai_cache/naming').glob('*.json')):
    record=json.loads(path.read_bytes())
    if record.get('origin')!='REAL_API' or not record.get('valid'):continue
    for row in record['answer']['rows']:records.setdefault(row['name'],row)
rows=[records[n] for n in experiment['names'] if n in records and n not in table['confirmed_names']]
labels={e['code']:e['label'] for e in table['classes']};labels['UNKNOWN']='无法判断'
def baseline(name):
    for entry in table['classes']:
        if name in entry.get('exact',[]) or any(w in name for w in entry.get('contains',[])):
            return entry['code']
    return None
proposals=yaml.safe_load((root/'rules/naming_proposals.yaml').read_text(encoding='utf-8'))
approved={r['name']:r for r in proposals['entries'] if r.get('approved') and r.get('approved_by')}
counts={'model_returned_unique_names':len(records),'experiment_input_names':len(experiment['names']),
        'outside_manual_names':len(rows),'keyword_covered':sum(baseline(r['name']) is not None for r in rows),
        'keyword_uncovered':sum(baseline(r['name']) is None for r in rows),
        'model_unknown':sum(r['category']=='UNKNOWN' for r in rows),
        'proposals_for_keyword_uncovered':sum(baseline(r['name']) is None and r['category']!='UNKNOWN' for r in rows),
        'approved':sum(r['name'] in approved for r in rows),
        'basis':'REAL_API valid answer rows intersected with experiment input; baseline uses only original exact/contains rules; no prompt tuning; no adoption rate'}
(root/'eval/naming-coverage.json').write_text(json.dumps(counts,ensure_ascii=False,indent=2),encoding='utf-8')
with (root/'eval/naming-review.csv').open('w',encoding='utf-8-sig',newline='') as f:
    writer=csv.writer(f)
    writer.writerow(['房名','现有词表结果','模型提议','模型理由','模型信心','已批准类别','核对：采纳/修改/不采纳','修改后的用途','备注'])
    for r in rows:
        writer.writerow([r['name'],labels.get(baseline(r['name']),'未命中原关键词'),labels[r['category']],r['reason'],r['confidence'],labels.get(approved.get(r['name'],{}).get('category'),''),'','',''])
print(json.dumps(counts,ensure_ascii=False,indent=2))
