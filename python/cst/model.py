# SPDX-License-Identifier: MPL-2.0
"""对应生产JSON字段；拒绝未知字段，不通过默认值掩盖格式漂移。"""
from typing import Literal
from pathlib import Path
import gzip
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

def load(directory: str | Path, model= L3):
    directory = Path(directory)
    if not directory.is_dir():
        raise ValueError("数据目录不存在")
    path=directory / FILENAMES[model]
    if path.is_file():
        payload=path.read_bytes()
    else:
        payload=gzip.decompress(path.with_name(path.name+".gz").read_bytes())
    return model.model_validate_json(payload)
