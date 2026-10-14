# SPDX-License-Identifier: MPL-2.0
import argparse
import json
import sys
from .model import load
from .summary import summary

def main():
    parser = argparse.ArgumentParser(prog="python -m cst")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("light-calc")
    p.add_argument("directory",nargs="?")
    p.add_argument("--output")
    p.add_argument("--synthetic",action="store_true")
    p = sub.add_parser("bundle")
    p.add_argument("directory")
    p.add_argument("--output",default="dist/bundle")
    p.add_argument("--changes")
    p = sub.add_parser("rule-impact")
    p.add_argument("--code",required=True)
    p.add_argument("--bundle",default="dist/bundle")
    p.add_argument("--synthetic",action="store_true")
    p = sub.add_parser("notify")
    p.add_argument("old_directory")
    p.add_argument("new_directory")
    p.add_argument("--replay",action="store_true")
    p.add_argument("--output",default="dist/notify")
    p.add_argument("--changes")
    p.add_argument("--registry",default="versions.yaml")
    p = sub.add_parser("naming")
    p.add_argument("directories",nargs="+")
    p.add_argument("--replay",action="store_true")
    p = sub.add_parser("recover")
    p.add_argument("directory")
    p.add_argument("--room",action="append",default=[])
    p.add_argument("--output",required=True)
    p.add_argument("--public-label",required=True,choices=["A","B"])
    p.add_argument("--baseline")
    p.add_argument("--all-unresolved",action="store_true")
    p = sub.add_parser("lights")
    p.add_argument("directory")
    p.add_argument("--output")
    p.add_argument("--mode",choices=["auto","grid","wall"],default="auto")
    p = sub.add_parser("view")
    p.add_argument("directory")
    p.add_argument("--output")
    p.add_argument("--generated")
    p.add_argument("--changes")
    p.add_argument("--review",help="可选人工修改记录对照JSON；不参与自动识别")
    p.add_argument("--issues",help="当前扫描对应的房间问题定位JSON")
    p = sub.add_parser("cloud")
    p.add_argument("diff_json")
    p.add_argument("--output",default="dist/changes/impact_cloud.dxf")
    p = sub.add_parser("diff")
    p.add_argument("old_directory")
    p.add_argument("new_directory")
    p.add_argument("--output",default="dist/changes")
    p = sub.add_parser("summary")
    p.add_argument("directory")
    p = sub.add_parser("verify")
    p.add_argument("directory")
    p.add_argument("--dwg")
    p = sub.add_parser("gold")
    p.add_argument("directory")
    p.add_argument("--label",required=True,choices=["A","B"])
    p.add_argument("--output",default="eval")
    p = sub.add_parser("classify")
    p.add_argument("directory")
    p.add_argument("--draft",action="store_true")
    p.add_argument("--output")
    p = sub.add_parser("gold-groups")
    p.add_argument("directories",nargs="+")
    p.add_argument("--output",default="eval/room-use-review.csv")
    p = sub.add_parser("neighbors")
    p.add_argument("directory")
    p.add_argument("--output")
    p = sub.add_parser("coedges")
    p.add_argument("directory")
    p = sub.add_parser("check")
    p.add_argument("directory")
    p = sub.add_parser("report")
    p.add_argument("directory")
    p.add_argument("--output")
    p = sub.add_parser("draft-rule")
    p.add_argument("text",nargs="?")
    p.add_argument("--code",default="待核")
    p.add_argument("--article",default="待核")
    p.add_argument("--replay",action="store_true")
    p.add_argument("--cache")
    p.add_argument("--output",default="rules/drafts")
    p = sub.add_parser("ask")
    p.add_argument("directory",nargs="?",default="samples/A")
    p.add_argument("--question",default="请报告空间数量与复核状态")
    p.add_argument("--replay",action="store_true")
    p.add_argument("--cache",default="ai_cache/SYNTHETIC_validator.json")
    args = parser.parse_args()
    try:
        if args.command == "light-calc":
            from .light_calc import calculate_directory,synthetic_probe
            if args.synthetic:result=synthetic_probe(args.output or "dist/calculations/SYNTHETIC/lighting_calculations.json")
            elif args.directory:result=calculate_directory(args.directory,args.output)
            else:raise ValueError("请指定数据目录或--synthetic演示")
        elif args.command == "bundle":
            from .decisions import bundle
            result = bundle(args.directory,args.output,args.changes)
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
            result = diff(args.old_directory,args.new_directory,args.output)
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
    except (OSError, ValueError) as exc:
        print(f"无法读取数据：{exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result.get("status") == "failed" else 0

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
