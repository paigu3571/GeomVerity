# SPDX-License-Identifier: MPL-2.0
import argparse
import json
import sys
from .model import load
from .summary import summary

def main(argv=None):
    parser = argparse.ArgumentParser(prog="geomverity",description="GeomVerity：扫描体检、项目管理和离线逐条核验")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("inventory",help="只读普查扫描各层兼容性与缺口")
    p.add_argument("directory",help="扫描根目录（递归发现L1/L2/L3）")
    p.add_argument("--output",help="可选JSON输出目录；默认只输出JSON")
    p = sub.add_parser("project",help="新建项目、添加/选用版本或查看项目")
    project_sub=p.add_subparsers(dest="project_action",required=True)
    for operation,description in [("new","新建旁挂项目"),("add","添加扫描版本"),("select","选用项目中的版本"),("show","读取项目与版本")]:
        item=project_sub.add_parser(operation,help=description)
        item.add_argument("path",help="项目文件夹或geomverity-project.json")
        if operation in ("new","add"):item.add_argument("--name",required=True,help="项目名或版本名")
        if operation=="add":
            item.add_argument("scan_directory",help="已有扫描目录")
            item.add_argument("--note",default="",help="版本说明")
        if operation=="select":item.add_argument("version_id",help="show中读取的版本ID")
    p = sub.add_parser("claims-check",help="离线逐条核对AI主张、引用、面积与确认状态")
    p.add_argument("directory",help="扫描结果目录")
    p.add_argument("claims_json",help="claims.v1或旧Answer JSON")
    p.add_argument("--changes",help="对应的两版diff.json")
    p.add_argument("--previous",help="旧claims-check.json；按依赖重核")
    p.add_argument("--status-basis",choices=["current","frozen_record"],default="current",help="frozen_record只核对生成时冻结的旧记录，不作为当前工程结论")
    p.add_argument("--area-config",help="面积容差JSON：absolute_m2与relative；默认0.01m²/0.005")
    p.add_argument("--output",default="dist/claims-check",help="结果输出目录")
    p = sub.add_parser("light-calc",help="按演示参数回算照明（不作正式合规结论）")
    p.add_argument("directory",nargs="?",help="扫描结果目录")
    p.add_argument("--output",help="输出文件或目录（默认见命令说明）")
    p.add_argument("--synthetic",action="store_true",help="运行明确标记的SYNTHETIC合成演示")
    p = sub.add_parser("bundle",help="导出可校验的决策与核验证据包")
    p.add_argument("directory",help="扫描结果目录")
    p.add_argument("--output",default="dist/bundle",help="输出文件或目录")
    p.add_argument("--changes",help="与当前新版对应的diff.json")
    p.add_argument("--claims-check",help="显式收录的claims-check.json")
    p = sub.add_parser("rule-impact",help="查询规范引用影响哪些规则/决策")
    p.add_argument("--code",required=True,help="规范或规则引用编号")
    p.add_argument("--bundle",default="dist/bundle",help="已有证据包目录")
    p.add_argument("--synthetic",action="store_true",help="运行明确标记的SYNTHETIC合成演示")
    p = sub.add_parser("notify",help="生成两版变化的复核通知")
    p.add_argument("old_directory",help="旧版扫描目录")
    p.add_argument("new_directory",help="新版扫描目录")
    p.add_argument("--replay",action="store_true",help="离线重放已保存结果，不调用模型")
    p.add_argument("--output",default="dist/notify",help="输出文件或目录")
    p.add_argument("--changes",help="与当前新版对应的diff.json")
    p.add_argument("--registry",default="versions.yaml",help="版本登记YAML")
    p = sub.add_parser("naming",help="术语提议及已保存结果重放")
    p.add_argument("directories",nargs="+",help="一个或多个扫描目录")
    p.add_argument("--replay",action="store_true",help="离线重放已保存结果，不调用模型")
    p = sub.add_parser("recover",help="生成漏房与围合诊断候选")
    p.add_argument("directory",help="扫描结果目录")
    p.add_argument("--room",action="append",default=[],help="待诊断房间ID，可重复指定")
    p.add_argument("--output",required=True,help="输出文件或目录")
    p.add_argument("--public-label",required=True,choices=["A","B"],help="公开样例标签")
    p.add_argument("--baseline",help="已有基线目录")
    p.add_argument("--all-unresolved",action="store_true",help="诊断所有未形成围合的已知房名")
    p = sub.add_parser("lights",help="生成灯具布置候选")
    p.add_argument("directory",help="扫描结果目录")
    p.add_argument("--output",help="输出文件或目录（默认见命令说明）")
    p.add_argument("--mode",choices=["auto","grid","wall"],default="auto",help="auto/grid/wall布置候选模式")
    p = sub.add_parser("view",help="生成离线图面查看器")
    p.add_argument("directory",help="扫描结果目录")
    p.add_argument("--output",help="输出文件或目录（默认见命令说明）")
    p.add_argument("--generated",help="已有生成候选JSON")
    p.add_argument("--changes",help="与当前新版对应的diff.json")
    p.add_argument("--review",help="可选人工修改记录对照JSON；不参与自动识别")
    p.add_argument("--issues",help="当前扫描对应的房间问题定位JSON")
    p = sub.add_parser("cloud",help="把既有差异导出独立云线DXF")
    p.add_argument("diff_json",help="已有diff.json")
    p.add_argument("--output",default="dist/changes/impact_cloud.dxf",help="输出文件或目录")
    p = sub.add_parser("diff",help="比较调用者提供的同图两版扫描")
    p.add_argument("old_directory",help="旧版扫描目录")
    p.add_argument("new_directory",help="新版扫描目录")
    p.add_argument("--output",default="dist/changes",help="输出文件或目录")
    p.add_argument("--reviews",help="显式人工复核旁挂JSON；默认不读取或创建确认")
    p = sub.add_parser("summary",help="汇总已识别对象及复核状态")
    p.add_argument("directory",help="扫描结果目录")
    p = sub.add_parser("verify",help="校验源引用或证据包文件完整性")
    p.add_argument("directory",help="扫描结果目录")
    p.add_argument("--dwg",help="可选原DWG路径，仅作源字节核验")
    p = sub.add_parser("gold",help="生成房间人工标注空表")
    p.add_argument("directory",help="扫描结果目录")
    p.add_argument("--label",required=True,choices=["A","B"],help="公开样例标签A或B")
    p.add_argument("--output",default="eval",help="输出文件或目录")
    p = sub.add_parser("classify",help="读取或计算房间用途分类")
    p.add_argument("directory",help="扫描结果目录")
    p.add_argument("--draft",action="store_true",help="启用待审核用途草案")
    p.add_argument("--output",help="输出文件或目录（默认见命令说明）")
    p = sub.add_parser("gold-groups",help="合并房间用途分组标注表")
    p.add_argument("directories",nargs="+",help="一个或多个扫描目录")
    p.add_argument("--output",default="eval/room-use-review.csv",help="输出文件或目录")
    p = sub.add_parser("neighbors",help="查找隔墙贴邻候选")
    p.add_argument("directory",help="扫描结果目录")
    p.add_argument("--output",help="输出文件或目录（默认见命令说明）")
    p = sub.add_parser("coedges",help="查看共享墙面候选")
    p.add_argument("directory",help="扫描结果目录")
    p = sub.add_parser("check",help="运行规则并保留未知/待复核状态")
    p.add_argument("directory",help="扫描结果目录")
    p = sub.add_parser("report",help="生成规则审查HTML")
    p.add_argument("directory",help="扫描结果目录")
    p.add_argument("--output",help="输出文件或目录（默认见命令说明）")
    p = sub.add_parser("draft-rule",help="生成待审核规则草稿")
    p.add_argument("text",nargs="?",help="待处理文字")
    p.add_argument("--code",default="待核",help="规范或规则引用编号")
    p.add_argument("--article",default="待核",help="条文编号")
    p.add_argument("--replay",action="store_true",help="离线重放已保存结果，不调用模型")
    p.add_argument("--cache",help="已保存的公开缓存JSON")
    p.add_argument("--output",default="rules/drafts",help="输出文件或目录")
    p = sub.add_parser("ask",help="受约束AI问答或离线缓存重放")
    p.add_argument("directory",nargs="?",default="samples/A",help="扫描结果目录")
    p.add_argument("--question",default="请报告空间数量与复核状态",help="向受约束AI提出的问题")
    p.add_argument("--replay",action="store_true",help="离线重放已保存结果，不调用模型")
    p.add_argument("--cache",default="ai_cache/SYNTHETIC_validator.json",help="已保存的公开缓存JSON")
    args = parser.parse_args(argv)
    try:
        if args.command == "project":
            from .project import Project,read_project,write_project,project_path
            if args.project_action=="new":
                project=Project(name=args.name.strip())
                filename=write_project(project,args.path,overwrite=False)
            else:
                project=read_project(args.path)
                filename=str(project_path(args.path))
                if args.project_action=="add":project.add_version(args.name,args.scan_directory,args.note)
                elif args.project_action=="select":project.select(args.version_id)
                if args.project_action!="show":write_project(project,filename)
            result={'project_file':filename,'project':project.model_dump()}
        elif args.command == "inventory":
            from .inventory import inventory
            rows=inventory(args.directory)
            result={'scan_count':len(rows),'loaded_count':sum(row['load_ok'] for row in rows),'scans':rows,'note':'加载成功不等于扫描成功、识别正确或专业通过'}
            if args.output:
                from pathlib import Path
                path=Path(args.output)/'inventory.json';path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        elif args.command == "claims-check":
            from pathlib import Path
            from .claims import check_claims,recheck_claims,parse_document
            tolerance=json.loads(Path(args.area_config).read_bytes()) if args.area_config else None
            document=json.loads(Path(args.claims_json).read_bytes())
            if args.previous:
                previous=json.loads(Path(args.previous).read_bytes())
                if parse_document(document).model_dump()!=parse_document(previous['document']).model_dump():raise ValueError('重核原文与旧报告不一致')
                result=recheck_claims(args.directory,previous,args.changes,args.output,area_tolerance=tolerance)
            else:result=check_claims(args.directory,document,args.changes,args.output,area_tolerance=tolerance,status_basis=args.status_basis)
        elif args.command == "light-calc":
            from .light_calc import calculate_directory,synthetic_probe
            if args.synthetic:result=synthetic_probe(args.output or "dist/calculations/SYNTHETIC/lighting_calculations.json")
            elif args.directory:result=calculate_directory(args.directory,args.output)
            else:raise ValueError("请指定数据目录或--synthetic演示")
        elif args.command == "bundle":
            from .decisions import bundle
            result = bundle(args.directory,args.output,args.changes,args.claims_check)
        elif args.command == "rule-impact":
            from .decisions import rule_impact
            result = rule_impact(args.code,args.bundle,args.synthetic)
        elif args.command == "notify":
            from .notify import notify
            result = notify(args.old_directory,args.new_directory,args.replay,args.output,args.registry,args.changes)
        elif args.command == "naming":
            from .naming import experiment
            result = experiment(args.directories,args.replay)
        elif args.command == "recover":
            from .recovery import recover
            result = recover(args.directory,args.room,args.output,args.public_label,args.baseline,args.all_unresolved)
        elif args.command == "lights":
            from .lighting import lights
            result = lights(args.directory,args.output,args.mode)
        elif args.command == "view":
            from .view import write_view
            result = write_view(args.directory,args.output,args.generated,args.changes,args.review,args.issues)
        elif args.command == "cloud":
            from .cloud import cloud
            result = cloud(args.diff_json,args.output)
        elif args.command == "diff":
            from .changes import diff
            from .reviews import read_reviews
            result = diff(args.old_directory,args.new_directory,args.output,review_records=read_reviews(args.reviews) if args.reviews else None)
        elif args.command == "draft-rule":
            from .draft import draft_rule
            result = draft_rule(args.text,args.code,args.article,args.cache,args.replay,args.output)
        elif args.command == "report":
            from .report import write_report
            result = write_report(args.directory,args.output)
        elif args.command == "ask":
            from .ai import ask,replay
            result = replay(args.cache,args.directory) if args.replay else ask(args.directory,args.question,"ai_cache")
        elif args.command == "neighbors":
            from .adjacency import neighbors
            result = neighbors(args.directory,args.output)
        elif args.command == "coedges":
            from .l4 import coedges
            result = coedges(args.directory)
        elif args.command == "check":
            from pathlib import Path
            from .l4 import check
            load(args.directory)
            result = check(args.directory)
        elif args.command == "classify":
            from .uses import classify,write_csv
            result = classify(args.directory,draft=args.draft)
            if args.output:
                write_csv(result,args.output)
                result.pop("rows")
        elif args.command == "gold-groups":
            from .gold import group_gold
            result = group_gold(args.directories,args.output)
        elif args.command == "gold":
            from .gold import gold
            result = gold(args.directory,args.label,args.output)
        elif args.command == "verify":
            from .verify import verify
            from pathlib import Path
            if (Path(args.directory)/"bundle-manifest.json").is_file():
                from .decisions import verify_bundle
                result = verify_bundle(args.directory)
            else:result = verify(args.directory,args.dwg)
        else:
            result = summary(load(args.directory))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        from pydantic import ValidationError
        if isinstance(exc,ValidationError):
            message='；'.join('.'.join(map(str,e['loc']))+': '+e['msg'] for e in exc.errors(include_input=False,include_url=False)[:3])
        else:message=str(exc)
        print(f"操作未完成：{message}",file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result.get("status") == "failed" or (args.command == "claims-check" and not result["valid"]) else 0

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
