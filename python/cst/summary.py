# SPDX-License-Identifier: MPL-2.0
from collections import Counter
from .model import L3

def summary(data: L3) -> dict:
    by_id = {o.semantic_id: o for o in data.objects}
    connections = [r for r in data.relations if {by_id.get(r.from_semantic_id).type if r.from_semantic_id in by_id else None, by_id.get(r.to_semantic_id).type if r.to_semantic_id in by_id else None} == {"opening", "space"}]
    return {
        "producer_version": data.producer_version,
        "run_status": data.status,
        "objects_by_type": dict(sorted(Counter(o.type for o in data.objects).items())),
        "object_status": dict(sorted(Counter(o.status for o in data.objects).items())),
        "space_use_codes": dict(sorted(Counter(o.use_code for o in data.objects if o.type == "space").items())),
        "shaft_use_codes": dict(sorted(Counter(o.use_code for o in data.objects if o.type == "shaft").items())),
        "opening_space_relation_edges": len(connections),
        "opening_space_relation_status": dict(sorted(Counter(r.status for r in connections).items())),
        "note": "对象和关系数量不是准确率；门洞关系边数不是安全出口数。",
    }
