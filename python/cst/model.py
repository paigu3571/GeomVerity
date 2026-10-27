# SPDX-License-Identifier: MPL-2.0
"""对应生产JSON字段；拒绝未知字段，不通过默认值掩盖格式漂移。"""
from typing import Literal
from pathlib import Path
import gzip
from contextlib import contextmanager
from contextvars import ContextVar
from pydantic import BaseModel, ConfigDict

Decision = Literal["accepted", "review", "rejected"]
RunStatus = Literal["accepted", "review", "failed"]

class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

class Point(Model):
    x: float
    y: float
    z: float

class Bounds(Model):
    min_x: float
    min_y: float
    min_z: float
    max_x: float
    max_y: float
    max_z: float
    is_valid: bool

class Geometry(Model):
    kind: str
    is_closed: bool
    is_exact: bool
    extraction_method: str
    paths: list[list[Point]]
    bounds: Bounds

class Source(Model):
    drawing_hash: str
    handle: str
    stable_path: str
    raw_layer: str
    effective_layer: str
    normalized_layer: str
    native_dxf_name: str
    native_class_name: str
    block_path: list[str]
    xref_path: list[str]
    xref_hashes: list[str]
    wcs_transform: list[float]

class Evidence(Model):
    code: str
    kind: str
    value: str
    source_handle: str
    weight: float

class Drawing(Model):
    drawing_id: str
    file_name: str
    sha256: str
    file_length: int
    source_last_write_utc: str
    coordinate_system: str
    geometry_units: str

class Profile(Model):
    project_id: str
    profile_version: str
    sha256: str

class Integrity(Model):
    source_hash_before: str
    source_hash_after: str
    source_bytes_unchanged: bool
    scan_input_mode: str
    input_database_read_only: bool
    dbmod_before: int
    dbmod_after: int
    dbmod_clean_at_start: bool
    dbmod_unchanged: bool

class Diagnostic(Model):
    severity: str
    reason_code: str
    message: str
    stable_path: str

class Proxy(Model):
    stable_path: str
    handle: str
    original_dxf_name: str
    original_class_name: str
    application_description: str
    effective_layer: str
    disposition: str
    reason_code: str

class Snapshot(Model):
    schema_version: str
    producer: str
    producer_version: str
    producer_binary_sha256: str
    generated_at_utc: str
    status: RunStatus
    reason_codes: list[str]
    drawing: Drawing
    profile: Profile
    integrity: Integrity
    fact_provider_id: str
    deterministic_content_hash: str
    metrics: dict[str, int]
    provider_diagnostics: list[Diagnostic]

class Primitive(Model):
    primitive_id: str
    source_fact_id: str
    kind: str
    adapter_role_hint: str
    is_semantic_candidate: bool
    source: Source
    raw_text: str
    raw_geometry: Geometry
    extraction_confidence: float
    raw_properties: dict[str, str]
    evidence: list[Evidence]
    reason_codes: list[str]

class L1(Snapshot):
    schema_version: Literal["cad-primitives.v1"]
    extraction_configuration_hash: str
    deterministic_hash_algorithm: str
    primitives: list[Primitive]
    proxy_ledger: list[Proxy]

class Measurements(Model):
    length_millimeters: float
    area_square_millimeters: float
    area_is_available: bool
    area_method: str
    width_millimeters: float
    height_millimeters: float
    representative_point_wcs_millimeters: Point

class GeometryFact(Model):
    geometry_id: str
    compatibility_fact_id: str
    source_primitive_ids: list[str]
    feature_kind: str
    adapter_role_hint: str
    is_semantic_candidate: bool
    source: Source
    geometry: Geometry
    measurements: Measurements
    raw_text: str
    extraction_confidence: float
    raw_properties: dict[str, str]
    evidence: list[Evidence]
    reason_codes: list[str]

class GeometryRelation(Model):
    relation_id: str
    type: str
    from_geometry_id: str
    to_geometry_id: str
    distance_millimeters: float
    confidence: float
    reason_codes: list[str]

class L2(Snapshot):
    schema_version: Literal["building-geometry.v1"]
    source_primitive_content_hash: str
    geometry_configuration_hash: str
    deterministic_hash_algorithm: str
    facts: list[GeometryFact]
    relations: list[GeometryRelation]

class SemanticObject(Model):
    semantic_id: str
    type: Literal["storey", "space", "wall", "column", "opening", "door", "window", "shaft", "stair", "ramp", "zone", "roof_line"]
    classification: str
    raw_label: str
    use_code: str
    status: Decision
    confidence: float
    source: Source
    geometry: Geometry
    evidence: list[Evidence]
    reason_codes: list[str]

class Relation(Model):
    relation_id: str
    type: str
    from_semantic_id: str
    to_semantic_id: str
    status: Decision
    confidence: float
    evidence: list[Evidence]
    reason_codes: list[str]

class Finding(Model):
    finding_id: str
    severity: str
    reason_code: str
    message: str
    semantic_id: str
    source_handle: str

class L3(Snapshot):
    schema_version: Literal["building-semantics.v1"]
    objects: list[SemanticObject]
    relations: list[Relation]
    findings: list[Finding]
    proxy_ledger: list[Proxy]

FILENAMES = {L1: "cad-primitives.v1.json", L2: "building-geometry.v1.json", L3: "building-semantics.v1.json"}

_snapshot_cache = ContextVar('snapshot_cache', default=None)


@contextmanager
def snapshot_session(shared_cache=None):
    """默认仅单任务复用；跨任务由工作台输入哈希守卫显式提供私有缓存。"""
    current=_snapshot_cache.get()
    if current is not None and shared_cache is not None and current is not shared_cache:
        raise ValueError("不能混用两个只读快照会话")
    if current is not None:
        yield
        return
    token = _snapshot_cache.set({} if shared_cache is None else shared_cache)
    try:yield
    finally:_snapshot_cache.reset(token)


def session_memo(namespace,key,signature,build):
    """只读任务内的派生依赖复用；由调用者复制可变结果，依赖变化时拒绝混用。"""
    cache=_snapshot_cache.get()
    if cache is None:return build()
    cache_key=(namespace,key)
    if cache_key in cache:
        prior,value=cache[cache_key]
        if prior!=signature:raise ValueError('计算过程中依赖文件发生变化，请重新运行')
        return value
    value=build();cache[cache_key]=(signature,value)
    return value


def load(directory: str | Path, model= L3):
    directory = Path(directory)
    if not directory.is_dir():
        raise ValueError("数据目录不存在")
    path=directory / FILENAMES[model]
    compressed = not path.is_file()
    if compressed:path=path.with_name(path.name+".gz")
    stat=path.stat();signature=(str(path.resolve()),stat.st_mtime_ns,stat.st_size)
    cache=_snapshot_cache.get();key=(str(directory.resolve()),model)
    if cache is not None and key in cache:
        prior,value=cache[key]
        if prior!=signature:raise ValueError("计算过程中扫描文件发生变化，请重新运行")
        return value
    payload=path.read_bytes()
    if compressed:payload=gzip.decompress(payload)
    value=model.model_validate_json(payload)
    stat=path.stat()
    if (str(path.resolve()),stat.st_mtime_ns,stat.st_size)!=signature:raise ValueError("读取过程中扫描文件发生变化，请重新运行")
    if cache is not None:cache[key]=(signature,value)
    return value


def snapshot_digest(directory,model,data):
    """已验证模型的序列化摘要；文件签名变化时仍拒绝在同一会话混用。"""
    from .naming import digest
    path=Path(directory)/FILENAMES[model]
    if not path.is_file():path=path.with_name(path.name+'.gz')
    stat=path.stat();signature=(str(path.resolve()),stat.st_mtime_ns,stat.st_size)
    return session_memo('snapshot_digest',(str(Path(directory).resolve()),model),signature,lambda:digest(data.model_dump()))
