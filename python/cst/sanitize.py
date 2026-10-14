# SPDX-License-Identifier: MPL-2.0
"""公开样例去标识化；保留几何和引用，不声称布局匿名化。"""
import hashlib
import gzip
import json
from pathlib import Path
import re
from .model import FILENAMES, L3

PATH = re.compile(r"[A-Za-z]:[\\/][^\r\n\"<>|]*|/(?:home|Users)/[^\r\n\"<>|]*")
FILENAME = re.compile(r"(?<![\w])[\w.-]+\.(?:dwg|dxf|rvt|bak|dll)\b",re.I)

class Cleaner:
    def __init__(self,semantic,label):
        self.label=label
        self.allowed={o["raw_label"] for o in semantic["objects"] if o["raw_label"]}
        self.allowed.update(e["value"] for o in semantic["objects"] for e in o["evidence"] if e["kind"]=="spatial_text")
        names=set()
        for o in semantic["objects"]:
            for item in o["source"]["block_path"]:
                if ":" in item: names.add(item.split(":",1)[1])
        self.mapping={name:f"BLOCK_{i:04d}" for i,name in enumerate(sorted(names),1)}
        self.mapping[semantic["drawing"]["file_name"]]=f"Sample{label}.dwg"
        self.mapping[semantic["drawing"]["drawing_id"]]=f"sample-{label}"
        self.mapping[semantic["profile"]["project_id"]]=f"sample-{label}"
        self.mapping.update({"zhangtian":"AUTHOR","张田":"AUTHOR","001项目":"PROJECT"})
        self.pattern = re.compile("|".join(re.escape(k) for k in sorted(self.mapping,key=lambda k:(-len(k),k)) if k))
        self.replacements=0

    def text(self,value):
        original=value
        value=self.pattern.sub(lambda match:self.mapping[match.group(0)],value)
        value=PATH.sub("[REDACTED_PATH]",value)
        value=FILENAME.sub(f"Sample{self.label}.dwg",value)
        self.replacements+=int(original!=value)
        return value

    def walk(self,value,key=""):
        if isinstance(value,dict):
            result={}
            for k,v in value.items():
                if k=="raw_text" and isinstance(v,str) and v and v not in self.allowed and not re.fullmatch(r"[\d\s.,+-]+(?:m2|m²|㎡|平方米)?",v):
                    result[k]="[REDACTED_ANNOTATION]";self.replacements+=1
                elif k=="raw_properties":
                    # Properties may contain arbitrary names/paths. Only retain values already
                    # exposed as allowed semantic room labels or simple numbers/material flags.
                    result[k]={pk:self.text(pv) if pv in self.allowed or re.fullmatch(r"[-+\d.eE ]+|ByLayer|ByBlock|ByColor",pv) else "[REDACTED_PROPERTY]" for pk,pv in v.items()}
                else: result[k]=self.walk(v,k)
            return result
        if isinstance(value,list): return [self.walk(v,key) for v in value]
        if isinstance(value,str): return self.text(value)
        return value

def sanitize(source,target,label,allowed_labels=()):
    source,target=Path(source),Path(target)
    if not any(target.resolve().is_relative_to(Path(__file__).resolve().parents[2]/folder) for folder in ("samples","dist")):
        raise ValueError("清理输出必须位于本仓库samples或dist目录")
    target.mkdir(parents=True,exist_ok=True)
    semantic=json.loads((source/FILENAMES[L3]).read_bytes())
    cleaner=Cleaner(semantic,label)
    cleaner.allowed.update(allowed_labels)
    # L1 also has non-semantic block instances: de-identify their names consistently.
    l1raw=json.loads((source/"cad-primitives.v1.json").read_bytes())
    names={item.split(":",1)[1] for primitive in l1raw["primitives"] for item in primitive["source"]["block_path"] if ":" in item}
    names.update(k for k in cleaner.mapping if cleaner.mapping[k].startswith("BLOCK_"))
    for i,name in enumerate(sorted(names),1): cleaner.mapping[name]=f"BLOCK_{i:04d}"
    cleaner.pattern=re.compile("|".join(re.escape(k) for k in sorted(cleaner.mapping,key=lambda k:(-len(k),k)) if k))
    files={}
    for model,filename in FILENAMES.items():
        raw=l1raw if filename=="cad-primitives.v1.json" else json.loads((source/filename).read_bytes())
        clean=cleaner.walk(raw)
        clean["drawing"]["file_name"]=f"Sample{label}.dwg"
        clean["drawing"]["drawing_id"]=f"sample-{label}"
        clean["profile"]["project_id"]=f"sample-{label}"
        model.model_validate(clean)
        payload=(json.dumps(clean,ensure_ascii=False,separators=(",",":"))+"\n").encode("utf-8")
        compressed=gzip.compress(payload,mtime=0)
        output=filename+".gz"
        (target/output).write_bytes(compressed)
        if (target/filename).is_file():
            assert (target/filename).resolve().is_relative_to(target.resolve())
            (target/filename).unlink()
        files[output]={"sha256":hashlib.sha256(compressed).hexdigest(),"bytes":len(compressed)}
    manifest={"sample":label,"sanitized":True,"files":files,"replacement_count":cleaner.replacements,
              "source_dwg_included":False,"original_producer_version":semantic["producer_version"],
              "notice":"元数据中的原扫描内容哈希只作原始记录；去标识化后文件摘要见本清单。不证明布局匿名或识别正确；原DWG未公开，字节未核验。"}
    (target/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return manifest
