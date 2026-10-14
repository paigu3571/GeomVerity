# SPDX-License-Identifier: MPL-2.0
"""只核查引用完整性，不把来源存在当识别正确。"""
from collections import Counter, defaultdict
from pathlib import Path
import hashlib
import json
import re
from .model import L1, L2, L3, load

HANDLE_KINDS = {"layer", "rxclass", "idispatch_property", "geometry", "geometry_policy", "hatch_property", "native_type", "layer_and_native_geometry", "geometry_topology", "spatial_text", "source_identity", "geometry_relation"}
CONFIG_KINDS = {"profile_policy", "profile_rule", "profile_rule_pack"}

def trace_geometry(geometry_id, geometries, primitives):
    fact = geometries.get(geometry_id)
    if fact is None:
        return False, "L2几何ID不存在"
    if not fact.source_primitive_ids:
        return False, "L2没有L1引用"
    for pid in fact.source_primitive_ids:
        primitive = primitives.get(pid)
        if primitive is None:
            return False, "L1图元ID不存在：" + pid
        if not primitive.source.handle:
            return False, "L1源Handle为空：" + pid
    return True, "L3→L2→L1→Handle引用存在"

def verify(directory, dwg=None):
    directory = Path(directory)
    l1, l2, l3 = load(directory,L1), load(directory,L2), load(directory,L3)
    primitives = {p.primitive_id:p for p in l1.primitives}
    geometries = {g.geometry_id:g for g in l2.facts}
    objects = {o.semantic_id:o for o in l3.objects}
    handles = {p.source.handle for p in l1.primitives if p.source.handle}
    texts = defaultdict(set)
    for primitive in l1.primitives:
        texts[primitive.source.handle].add(primitive.raw_text)
    stable_paths = {p.source.stable_path for p in l1.primitives}
    categories = defaultdict(Counter)
    issues = []
    def record(category,status,owner,reason=""):
        categories[category][status]+=1
        if status == "failed" or (status == "unverified" and categories[category][status] == 1):
            issues.append({"owner_id":owner,"category":category,"status":status,"reason":reason})
    for label,sequence,key in [("L1",l1.primitives,"primitive_id"),("L2",l2.facts,"geometry_id"),("L3",l3.objects,"semantic_id"),("L3关系",l3.relations,"relation_id")]:
        ids=[getattr(o,key) for o in sequence]
        ok=len(ids)==len(set(ids)) and all(ids)
        record("ID唯一性","passed" if ok else "failed",label,"ID重复或空")
    for fact in l2.facts:
        ok,reason=trace_geometry(fact.geometry_id,geometries,primitives)
        record("L2→L1→Handle","passed" if ok else "failed",fact.geometry_id,reason)
    complete=0
    for obj in l3.objects:
        refs=[e.value for e in obj.evidence if e.kind=="geometry_fact" and e.code=="GEOMETRY_FACT_SOURCE"]
        outcomes=[trace_geometry(ref,geometries,primitives) for ref in refs]
        ok=bool(refs) and all(value[0] for value in outcomes)
        reason="缺少GEOMETRY_FACT_SOURCE" if not refs else ";".join(value[1] for value in outcomes if not value[0])
        record("对象完整引用链","passed" if ok else "failed",obj.semantic_id,reason)
        complete+=int(ok)
    for owner in l3.objects+l3.relations:
        owner_id=getattr(owner,"semantic_id",getattr(owner,"relation_id",""))
        for e in owner.evidence:
            category="证据/"+e.kind
            if e.kind=="geometry_fact":
                ok,reason=trace_geometry(e.value,geometries,primitives)
                record(category,"passed" if ok else "failed",owner_id,reason)
            elif e.kind in CONFIG_KINDS:
                record(category,"unverified",owner_id,"配置/规则说明是记录，不是对象ID；未提供原配置，内容未核验")
            elif e.kind in HANDLE_KINDS:
                ok=bool(e.source_handle) and e.source_handle in handles
                reason="源Handle不在L1"
                if ok and e.kind=="source_identity":
                    ok=e.value in stable_paths
                    reason="源实例路径不在L1"
                if ok and e.kind=="spatial_text":
                    ok=e.value in texts[e.source_handle]
                    reason="源Handle存在但房名文字未匹配L1"
                record(category,"passed" if ok else "failed",owner_id,reason)
            else:
                record(category,"unverified",owner_id,"未支持的证据类别，未静默通过")
    for relation in l3.relations:
        ok=relation.from_semantic_id in objects and relation.to_semantic_id in objects
        record("L3关系端点","passed" if ok else "failed",relation.relation_id,"关系端点不存在")
    same_hash=len({s.drawing.sha256.upper() for s in (l1,l2,l3)})==1
    record("三层源文件标识","passed" if same_hash else "failed","drawing","三层源哈希不一致")
    upstream=l2.source_primitive_content_hash==l1.deterministic_content_hash
    sanitized=(directory/"manifest.json").is_file()
    record("上游内容哈希记录","unverified" if sanitized and upstream else "passed" if upstream else "failed","L2","公开文件经过清理：原内容哈希仅是记录" if sanitized else "L2记录的L1摘要不一致；未重算原canonical-binary-v2")
    if sanitized:
        manifest=json.loads((directory/"manifest.json").read_bytes())
        for filename in ("cad-primitives.v1.json","building-geometry.v1.json","building-semantics.v1.json"):
            path=directory/filename
            if not path.is_file(): path=path.with_name(path.name+".gz")
            expected=manifest.get("files",{}).get(path.name,{}).get("sha256")
            ok=hashlib.sha256(path.read_bytes()).hexdigest()==expected
            record("公开文件字节摘要","passed" if ok else "failed",filename,"清理后文件与清单不对应")
    for layer in (l1,l2,l3):
        i=layer.integrity
        ok=i.source_hash_before.upper()==i.source_hash_after.upper()==layer.drawing.sha256.upper() and i.source_bytes_unchanged
        record("扫描时哈希记录","passed" if ok else "failed",layer.schema_version,"记录显示扫描前后源字节改变或记录冲突")
    source_bytes = verify_source_bytes(directory,l3.drawing,dwg)
    failures=sum(c["failed"] for c in categories.values())+int(source_bytes["status"]=="failed")
    return {"status":"failed" if failures else "partial" if source_bytes["status"]=="unverified" or any(c["unverified"] for c in categories.values()) else "passed",
            "object_chains":{"total":len(l3.objects),"passed":complete,"pass_rate":complete/len(l3.objects) if l3.objects else None},
            "categories":{k:dict(v) for k,v in sorted(categories.items())},"source_file_bytes":source_bytes,"failure_count":failures,"issues":issues,
            "scope":"按类别核查引用/Handle/房名与哈希记录；不验证所有几何/属性数值、配置真值、原内容哈希或识别正确性。"}

def verify_source_bytes(directory,drawing,dwg=None):
    directory=Path(directory)
    source=Path(dwg) if dwg else directory/drawing.file_name
    if not dwg and not source.is_file():
        source=directory.parent/drawing.file_name
    if not source.is_file():
        return {"status":"unverified","message":"公开包未附原图，跳过源字节核验；不计为失败，也不计入已核验通过"}
    digest=hashlib.sha256(source.read_bytes()).hexdigest().upper()
    ok=digest==drawing.sha256.upper()
    return {"status":"passed" if ok else "failed","message":"当前源文件字节已核验" if ok else "当前源文件与扫描不对应"}
