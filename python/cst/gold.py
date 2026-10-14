# SPDX-License-Identifier: MPL-2.0
import csv
from pathlib import Path
from .model import load,L2,L3

FIELDS=["ID","房名","系统用途","几何面积(m²)","状态","人工用途","是否漏检","是否真实空间","备注"]
MISSED=["人工编号","房名","人工用途","漏检原因","图中位置","备注"]

def area_m2(obj,facts):
    refs=[e.value for e in obj.evidence if e.kind=="geometry_fact"]
    areas=[facts[ref].measurements.area_square_millimeters/1e6 for ref in refs if ref in facts and facts[ref].measurements.area_is_available]
    return round(areas[0],6) if len(areas)==1 else ""

def gold(directory,label,output):
    output=Path(output); output.mkdir(parents=True,exist_ok=True)
    main=output/f"{label}_gold.csv";missed=output/f"{label}_missed.csv"
    # Preserve engineers' work when regeneration is requested later.
    for path in (main,missed):
        if path.is_file():
            with path.open(encoding="utf-8-sig",newline="") as f:
                rows=list(csv.DictReader(f))
            if any(row.get("人工用途") or row.get("备注") for row in rows):
                raise ValueError("标注表已有人工填写内容，不覆盖；请先保存现有标注")
    semantic=load(directory,L3);facts={f.geometry_id:f for f in load(directory,L2).facts}
    with main.open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS);writer.writeheader()
        for o in sorted(semantic.objects,key=lambda o:o.semantic_id):
            if o.type=="space":
                writer.writerow(dict(zip(FIELDS,[o.semantic_id,o.raw_label,o.use_code,area_m2(o,facts),o.status,"","","",""])))
    with missed.open("w",encoding="utf-8-sig",newline="") as f:
        csv.writer(f).writerow(MISSED)
    return {"sample":label,"space_rows":sum(o.type=="space" for o in semantic.objects),"gold":main.as_posix(),"missed":missed.as_posix(),"human_annotations":"待填写；没有评测数字"}


def group_gold(directories,output):
    """One row per exact room name; group approval is not detection assessment."""
    from collections import Counter
    from .uses import classify_name,DEFAULT_TABLE
    import yaml
    output=Path(output)
    if output.exists():
        with output.open(encoding="utf-8-sig",newline="") as f:
            if any(row.get(key) for row in csv.DictReader(f) for key in ("你确认的一级","你确认的二级","备注")):
                raise ValueError("合并表已有人工填写，不覆盖")
    table=yaml.safe_load(DEFAULT_TABLE.read_text(encoding="utf-8"))
    counts={}
    for directory in directories:
        directory=Path(directory)
        if directory.name in counts:raise ValueError("样例目录名重复，不能合并计数")
        counts[directory.name]=Counter(o.raw_label for o in load(directory,L3).objects if o.type in ("space","shaft"))
    fields=["房名"]+["数量"+label for label in counts]+["建议一级","建议二级","你确认的一级","你确认的二级","备注"]
    names=sorted(set().union(*(set(c) for c in counts.values())))
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for name in names:
            result=classify_name(name,table)
            row={"房名":name,"建议一级":result["label"],"建议二级":result["secondary_label"]}
            row.update({"数量"+label:c[name] for label,c in counts.items()})
            writer.writerow(row)
    return {"unique_names":len(names),"object_count":sum(sum(c.values()) for c in counts.values()),
            "output":output.as_posix(),"scope":"同名房间合并确认用途，不等于逐房间正确或漏检已验证"}
