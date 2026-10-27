# SPDX-License-Identifier: MPL-2.0
"""带核验/人工履历的本地证据包导出与只读重开。"""
import csv,hashlib,json
from html import escape
from pathlib import Path
from .decisions import bundle,verify_bundle
from .claims import recheck_claims
from .model import snapshot_session

def export_review_bundle(directory,output,project_name,version_name,*,workspace=None,changes=None,review_records=None):
    output=Path(output)
    if output.exists() and any(output.iterdir()):raise ValueError('导出目录已有内容，请选择新的空目录，避免覆盖历史证据')
    if workspace and (workspace.get('report') or {}).get('status_basis')=='frozen_record':raise ValueError('生成时冻结记录仅供资料忠实度盲标；请按当前比较重新核验后导出工程证据包')
    records=review_records or [];claims_path=None;report=None
    with snapshot_session():
        if workspace and workspace.get('document',{}).get('claims'):
            if not workspace.get('report'):raise ValueError('当前主张尚未核验或上下文已变化，请先重新核验')
            report=recheck_claims(directory,workspace['report'],changes=changes,review_records=records)
            staging=output.parent/('.gv-claims-'+__import__('secrets').token_hex(8));staging.mkdir(parents=True)
            claims_path=staging/'claims-check.json';claims_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        try:result=bundle(directory,output,changes=changes,claims_check=claims_path,review_records=records)
        finally:
            if claims_path:claims_path.unlink(missing_ok=True);claims_path.parent.rmdir()
    context={'schema_version':'workbench-bundle.v1','project':project_name,'version':version_name,'read_only':True,'scope':'文件完整性与核验留痕，不代表识别正确或设计通过'}
    (output/'workbench-context.json').write_text(json.dumps(context,ensure_ascii=False,indent=2),encoding='utf-8')
    if workspace:(output/'claims-edit-history.json').write_text(json.dumps({'schema_version':'claims-edit-history.v1','events':workspace.get('history',[])},ensure_ascii=False,indent=2),encoding='utf-8')
    rows=[]
    if report:
        for row in report['rows']:
            rows.append([project_name,version_name,', '.join(row['claim']['refs']),row['conclusion'],'、'.join(row['methods']),'; '.join(x['reason'] for x in row['checks']),row.get('manual_review','无'),row['validity']])
    findings=json.loads((output/'findings.json').read_bytes())['findings']
    for f in findings:
        manual=f.get('manual_review',{});engineer=f.get('decision',{}).get('engineer',{})
        rows.append([project_name,version_name,f.get('object_name') or f['id'],f['result'],'规则检查',f['reason'],manual.get('name') or engineer.get('confirmed_by') or '无','本条工具结果已核对' if manual.get('action')=='confirm' else '本条已驳回' if manual.get('action')=='reject' else '未作新人工确认'])
    header=['项目','版本','对象','结论','方法','依据','确认人','有效性']
    def cell(value):
        text=str(value)
        return "'"+text if text.startswith(('=','+','-','@')) else text
    with (output/'review-checklist.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(header);writer.writerows([[cell(v) for v in row] for row in rows])
    html='<!doctype html><meta charset="utf-8"><title>工程复核清单</title><style>body{font:14px/1.7 Microsoft YaHei;margin:28px;color:#203b48}table{border-collapse:collapse;width:100%}td,th{padding:8px;border:1px solid #dce5e9;text-align:left;vertical-align:top}</style><h1>工程复核清单</h1><p>'+escape(context['scope'])+'</p><table><thead><tr>'+''.join('<th>'+escape(c)+'</th>' for c in header)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+escape(str(c))+'</td>' for c in row)+'</tr>' for row in rows)+'</tbody></table>'
    (output/'review-checklist.html').write_text(html,encoding='utf-8')
    manifest_path=output/'bundle-manifest.json';manifest=json.loads(manifest_path.read_bytes())
    manifest['files']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file() and p.name!='bundle-manifest.json'}
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return dict(result,verification=verify_bundle(output),checklist_count=len(rows))

def open_review_bundle(directory):
    directory=Path(directory)
    try:
        with snapshot_session():verified=verify_bundle(directory)
    except (ValueError,KeyError,TypeError,OSError):return {'verification':{'status':'failed','failures':['证据包结构/文件或上下文校验失败']},'path':str(directory)}
    if verified['status']!='verified':return {'verification':verified,'path':str(directory)}
    manifest=json.loads((directory/'bundle-manifest.json').read_bytes())
    def read(name,default=None):return json.loads((directory/name).read_bytes()) if name in manifest['files'] else default
    return {'path':str(directory),'verification':verified,'context':read('workbench-context.json',{}),'claims_report':read('claims-check.json'),
            'findings':read('findings.json',{}),'review_records':read('engineer-reviews.json',{}),'history':read('claims-edit-history.json',{}),'read_only':True}
