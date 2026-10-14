# SPDX-License-Identifier: MPL-2.0
import argparse
import json
from cst.sanitize import sanitize
p=argparse.ArgumentParser(description="清理公开三层样例，原始文件只读")
p.add_argument("source");p.add_argument("target");p.add_argument("--label",required=True,choices=["A","B"])
a=p.parse_args()
print(json.dumps(sanitize(a.source,a.target,a.label),ensure_ascii=False,indent=2))
