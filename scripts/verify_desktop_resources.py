# SPDX-License-Identifier: MPL-2.0
"""检查桌面包顶层源码与全部UI资源，输出逐文件摘要，不修改运行包。"""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    source = root / "python/cst"
    package = Path(args.package).resolve() / "_internal/cst"
    paths = [p for p in source.iterdir() if p.is_file() and p.suffix in {".py", ".html", ".yaml", ".json"}]
    paths.extend(p for p in (source / "assets").rglob("*") if p.is_file())
    rows = []
    for path in sorted(paths):
        relative = path.relative_to(source)
        target = package / relative
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        actual = hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else None
        rows.append({"path": relative.as_posix(), "source_sha256": digest, "package_sha256": actual, "same": actual == digest})
    expected_assets = {p.relative_to(source / "assets").as_posix() for p in (source / "assets").rglob("*") if p.is_file()}
    package_assets = {p.relative_to(package / "assets").as_posix() for p in (package / "assets").rglob("*") if p.is_file()}
    unexpected = sorted(package_assets - expected_assets)
    result = {"all_same": all(row["same"] for row in rows) and not unexpected, "files": rows, "unexpected_assets": unexpected}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"resources": len(rows), "all_same": result["all_same"], "unexpected_assets": unexpected}))
    if not result["all_same"]:
        raise SystemExit("桌面包资源不一致，停止交付")


if __name__ == "__main__":
    main()
