# SPDX-License-Identifier: MPL-2.0
import argparse,json
from pathlib import Path
from cst.blind_labels import prepare,summarize
p=argparse.ArgumentParser();sub=p.add_subparsers(dest='action',required=True)
a=sub.add_parser('prepare');a.add_argument('claims');a.add_argument('--output',required=True)
a=sub.add_parser('summarize');a.add_argument('directory');a.add_argument('frozen');a.add_argument('labels');a.add_argument('--changes');a.add_argument('--status-basis',choices=['current','frozen_record'],default='current');a.add_argument('--process-notes');a.add_argument('--output',required=True)
a=p.parse_args()
if a.action=='prepare':
    destination=Path(a.output)
    if (destination/'盲标表.csv').exists() or (destination/'冻结主张.json').exists():raise ValueError('已有盲标表或冻结主张，请选择新输出目录，禁止覆盖人工回填')
    result=prepare(json.loads(Path(a.claims).read_bytes()),a.output)
else:result=summarize(a.directory,a.frozen,a.labels,a.output,a.changes,a.process_notes,a.status_basis)
print(json.dumps({k:v for k,v in result.items() if k!='components'},ensure_ascii=False,indent=2))
