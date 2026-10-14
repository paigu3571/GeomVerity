# SPDX-License-Identifier: MPL-2.0
"""只报告位置和类别，不打印敏感原文；本地敏感词表不进入仓库。"""
from __future__ import annotations
import argparse
import gzip
import os
from pathlib import Path
import re
import subprocess
import sys
from zipfile import ZipFile, BadZipFile

IGNORED_DIRS = {".git", ".local", ".venv", "dist", "bin", "obj", "__pycache__", ".pytest_cache"}
FORBIDDEN_SUFFIXES = {".dll", ".pdb", ".dwg", ".bak", ".dwl", ".dwl2"}
PATTERNS = {
    "疑似密钥": re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b|\b(?:DEEPSEEK_API_KEY|OPENAI_API_KEY)\s*[:=]\s*[\"']?[A-Za-z0-9_-]{16,}"),
    "本机绝对路径": re.compile(r"(?<![A-Za-z0-9])(?:[A-Za-z]:[\\/]|/(?:home|Users)/[A-Za-z0-9])"),
    "内网接口": re.compile(r"https?://(?:localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+)(?=[:/\s]|$)", re.I),
}

def files(root: Path):
    if (root / ".git").exists():
        result = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"], capture_output=True, check=True)
        names = sorted(set(result.stdout.decode("utf-8").split("\0")) - {""})
        for name in names:
            p = root / name
            if not (set(p.relative_to(root).parts) & IGNORED_DIRS) and p.is_file():
                yield p
    else:
        for directory, dirs, names in os.walk(root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in IGNORED_DIRS)
            for name in sorted(names):
                yield Path(directory) / name

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--words-file", type=Path, default=os.getenv("CST_SENSITIVE_WORDS_FILE"))
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if not root.is_dir():
        parser.error("扫描目录不存在")
    words = []
    if args.words_file:
        try:
            words = [line.strip() for line in Path(args.words_file).read_text(encoding="utf-8-sig").splitlines() if line.strip() and not line.lstrip().startswith("#")]
        except (OSError, UnicodeError):
            parser.error("无法读取本地敏感词文件，请检查路径及UTF-8编码")
    findings = []
    count = 0
    try:
        for p in files(root):
            rel = p.relative_to(root).as_posix()
            count += 1
            if not p.resolve().is_relative_to(root):
                findings.append((rel, 0, "链接指向仓库外"))
                continue
            if p.suffix.lower() in FORBIDDEN_SUFFIXES:
                findings.append((rel, 0, "禁止分发的图纸/二进制"))
                continue
            if p.name == ".env" or (p.name.startswith(".env.") and p.name != ".env.example"):
                findings.append((rel, 0, "真实环境配置"))
                continue
            try:
                data = p.read_bytes()
                if p.suffix.lower()==".xlsx":
                    # Read text-bearing OOXML members without extracting files.
                    with ZipFile(p) as archive:
                        data="\n".join(archive.read(name).decode("utf-8-sig") for name in archive.namelist()
                                       if name.endswith((".xml",".rels"))).encode("utf-8")
                if p.name.endswith(".json.gz"):
                    data=gzip.decompress(data)
                if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".gif"}:
                    valid = data.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"GIF87a", b"GIF89a"))
                    if not valid: findings.append((rel, 0, "图像扩展名与内容不符"))
                    continue
                if b"\0" in data:
                    findings.append((rel, 0, "二进制文件需人工核查"))
                    continue
                text = data.decode("utf-8-sig")
            except (OSError, UnicodeError, EOFError, BadZipFile):
                findings.append((rel, 0, "不可读取或非UTF-8文件需人工核查"))
                continue
            for line_no, line in enumerate(text.splitlines(), 1):
                for label, pattern in PATTERNS.items():
                    if pattern.search(line):
                        findings.append((rel, line_no, label))
                if any(word in line for word in words):
                    findings.append((rel, line_no, "自定义敏感词"))
    except (OSError, subprocess.CalledProcessError):
        print("扫描失败：检查Git安装及文件读取权限", file=sys.stderr)
        return 2
    for rel, line_no, label in findings:
        print(f"{rel}:{line_no} [{label}]")
    print(f"扫描完成：文件 {count} 个，发现 {len(findings)} 项；自定义敏感词 {len(words)} 条")
    if not words:
        print("未提供敏感词表：公司内部名称/项目名称的词表检查未运行，不代表已全面脱敏。")
    return 1 if findings else 0

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
