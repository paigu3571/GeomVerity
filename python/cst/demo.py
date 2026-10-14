# SPDX-License-Identifier: MPL-2.0
"""离线演示：仅安装阶段需要取得依赖，运行阶段禁止网络。"""
import json
from pathlib import Path
from unittest.mock import patch
from .model import load
from .summary import summary
from .verify import verify
from .l4 import check
from .report import write_report
from .ai import replay
from .room_diagnostics import diagnose_directory
from .draft import draft_rule

def run(root=None,changes_only=False):
    root=Path(root) if root else Path(__file__).resolve().parents[2]
    output=root/'dist/demo';output.mkdir(parents=True,exist_ok=True)
    manifest={'network_used':False,'samples':{},'ai_replays':[],'rule_replays':[]}
    def save(name,value):
        path=output/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    with patch('httpx.Client',side_effect=RuntimeError('离线演示禁止联网')):
        for label in (() if changes_only else ('A','B')):
            directory=root/'samples'/label
            counts=summary(load(directory));save(label+'/summary.json',counts)
            verified=verify(directory);save(label+'/verify.json',verified)
            if verified['failure_count']:raise ValueError(label+'证据引用验证失败，请查看verify.json')
            checked=check(directory);save(label+'/check.json',checked)
            # 报告中复核记录用仓库相对路径，避免导出本机路径。
            for f in checked['findings']:
                if f['engineer_reviewed']['record_file']:f['engineer_reviewed']['record_file']='samples/'+label+'/l4_confirmations.yaml'
            save(label+'/check.json',checked)
            report=write_report(directory,output/label/'l4_report.html')
            from .lighting import lights
            from .adjacency import neighbors
            from .view import write_view
            lighting=lights(directory,output/label)
            neighbor_result=neighbors(directory,output/label)
            diagnose_directory(directory,output/label)
            viewed=write_view(directory,output/label/'semantic_view.html',output/label/'lighting_candidates.json',issues=output/label/'room_issues.json')
            manifest['samples'][label]={'objects':counts['objects_by_type'],'findings':checked['summary'],'verification_failures':0,'lighting_candidates':lighting['point_count'],'neighbor_pairs':neighbor_result['neighbor_pair_count'],'viewer':viewed['output']}
            print(label+'：读取完成，引用验证失败0项，审查'+json.dumps(checked['summary'],ensure_ascii=False))
        from .changes import diff
        from .cloud import cloud
        change_dir=root/'samples/A-change'
        if change_dir.is_dir():
            changed=diff(root/'samples/A',change_dir,output/'changes')
            cloud(output/'changes/diff.json',output/'changes/impact_cloud.dxf')
            from .view import write_view
            manifest['drawing_issues']=diagnose_directory(change_dir,output/'changes')
            write_view(change_dir,output/'changes/semantic_view.html',output/'changes/lighting_candidates.json',output/'changes/diff.json',root/'eval/change_test_results.json' if (root/'eval/change_test_results.json').is_file() else None,issues=output/'changes/room_issues.json')
            from .decisions import bundle,verify_bundle
            manifest['bundle']=bundle(change_dir,output/'bundle',output/'changes/diff.json',issues=output/'changes/room_issues.json')
            manifest['bundle_verification']=verify_bundle(output/'bundle')
            if manifest['bundle_verification']['failure_count']:raise ValueError('证据包哈希校验失败')
            from .light_calc import calculate_directory,synthetic_probe
            manifest['light_calculation']=calculate_directory(change_dir,output/'changes/lighting_calculations.json')
            manifest['synthetic_light_calculation']=synthetic_probe(output/'SYNTHETIC/lighting_calculations.json')
            from .notify import notify
            manifest['notice']=notify(root/'samples/A',change_dir,replay=True,output=output/'notifications',registry=root/'versions.yaml',changes=output/'changes/diff.json')
            if not manifest['notice']['valid']:raise ValueError('通知引用校验未通过')
            manifest['changes']=changed
        for path in ([] if changes_only else sorted((root/'ai_cache').glob('*.json'))):
            record=json.loads(path.read_bytes())
            if record.get('origin')!='REAL_API':continue
            if record.get('kind')=='RULE_DRAFT':
                value=draft_rule(cache=path,replay=True,output=output/'rule-drafts')
                manifest['rule_replays'].append({'cache':path.name,'status':value['status']})
            else:
                dataset=root/'samples/A-change' if record.get('changes_sha256') else root/'samples/A'
                value=replay(path,dataset)
                if value['validation']['valid']!=record['validation']['valid']:raise ValueError('AI缓存校验状态与实调记录不同：'+path.name)
                manifest['ai_replays'].append({'cache':path.name,'valid':value['validation']['valid'],'display':'正常' if value['validation']['valid'] else '已拦截：不采用此回答'})
            save('replay/'+path.name,value)
        controls=replay(root/'ai_cache/SYNTHETIC_validator.json')
        if any(c['valid']!=c['expected_valid'] for c in controls['cases']):raise ValueError('合成引用校验控制失败')
        save('replay/SYNTHETIC_validator.json',controls)
    save('manifest.json',manifest)
    print('真实问答重放'+str(len(manifest['ai_replays']))+'例，真实规则起草重放'+str(len(manifest['rule_replays']))+'例；未联网，不需要CAD或密钥。')
    print('请打开dist/demo/changes/semantic_view.html查看真实变更，或A/B同名查看器；同目录有审查报告、邻房表和灯具候选DXF。')
    return manifest

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--changes-only',action='store_true',help='仅A到A-change，跳过A/B独立输出与全组AI重放')
    args=parser.parse_args()
    try:run(changes_only=args.changes_only)
    except (OSError,ValueError,RuntimeError) as exc:raise SystemExit('演示未完成：'+str(exc))
