# SPDX-License-Identifier: MPL-2.0
import csv
from collections import Counter
from pathlib import Path
import yaml
from .model import load

from .resources import rules_directory
DEFAULT_TABLE=rules_directory()/"space-uses.draft.yaml"

def classify_name(name,table):
    confirmed=table.get("confirmed_names",{}).get(name)
    if confirmed:
        label=next(entry["label"] for entry in table["classes"] if entry["code"]==confirmed["category"])
        return {"category":confirmed["category"],"label":label,"secondary_label":confirmed["secondary_label"],
                "reason":"张田已确认此房名的一二级用途；不证明原空间几何识别正确"}
    proposals_path=DEFAULT_TABLE.parent/"naming_proposals.yaml"
    if proposals_path.is_file():
        proposals=yaml.safe_load(proposals_path.read_text(encoding="utf-8")) or {}
        for proposal in proposals.get("entries",[]):
            if proposal.get("name")==name and proposal.get("approved") and proposal.get("approved_by"):
                label=next((e["label"] for e in table["classes"] if e["code"]==proposal["category"]),None)
                if label is not None:
                    return {"category":proposal["category"],"label":label,"secondary_label":name,"reason":"术语提议经"+proposal["approved_by"]+"批准","naming_provenance":{"model":proposals.get("model"),"cache_ids":proposals.get("cache_ids",[]),"cache_id":proposal.get("cache_id"),"approved_by":proposal["approved_by"],"approved_at":proposal.get("approved_at"),"model_proposed_category":proposal.get("model_proposed_category",proposal["category"]),"approved_category":proposal["category"],"engineer_note":proposal.get("engineer_note")}}
    for entry in table["classes"]:
        matched = next((word for word in entry.get("exact",[]) if name==word), None)
        if matched is None:
            matched = next((word for word in entry.get("contains",[]) if word in name), None)
        if matched is not None:
            return {"category":entry["code"],"label":entry["label"],"secondary_label":matched,
                    "reason":entry.get("reason","按房名词表归类；不代替图中实际用途核对")}
    return {"category":"NOT_INCLUDED","label":"未纳入","secondary_label":"",
            "reason":"未命中本轮建议词，不猜测用途"}

def classify(directory,table_path=DEFAULT_TABLE,draft=False):
    table=yaml.safe_load(Path(table_path).read_text(encoding="utf-8"))
    if table.get("approved") and not table.get("approved_by"):
        raise ValueError("批准表必须填写approved_by")
    if not table.get("approved") and not draft:
        raise ValueError("房名表未批准；仅可用--draft输出待确认草案")
    rows=[]
    for o in load(directory).objects:
        if o.type not in ("space","shaft"):continue
        result=classify_name(o.raw_label,table)
        water=table.get("water_candidates",{})
        rows.append({"object_id":o.semantic_id,"type":o.type,"name":o.raw_label,"l3_use_code":o.use_code,"l3_status":o.status,
                     **result,"water_candidate":any(word in o.raw_label for word in water.get("names",[])),
                     "water_needs_confirmation":any(word in o.raw_label for word in water.get("needs_confirmation",[])),
                     "handling":("已排除+"+result["reason"] if result["category"]=="EXCLUDED" else "房名用途已确认；规范结论另行判定") if table.get("approved") else "用途草案，未批准不参与规范结论",
                     "approved":bool(table.get("approved"))})
    return {"approved":bool(table.get("approved")),"scope":"L3 Space和Shaft；不修改L3，不代表规则结论", "counts":dict(sorted(Counter(row["label"] for row in rows).items())),"rows":rows}

def write_csv(result,path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8-sig",newline="") as f:
        fields=list(result["rows"][0]) if result["rows"] else ["object_id","name","label"]
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(result["rows"])
