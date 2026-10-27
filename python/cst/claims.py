# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 张田
"""原文旁挂主张契约及离线核验；只核对已声明的结构化事实，不作专业签字。"""
from collections import Counter
import json
import math
from pathlib import Path
from typing import Literal
from pydantic import Field, model_validator
from .model import Model, L1, L2, L3, load, snapshot_digest
from .naming import digest
from .ai import ReadTools, affirmative
from .evidence import default_registry
from .decisions import object_fingerprint, rule_metadata

VERSION = 'claims-check.4'


class AreaTolerance(Model):
    """项目核验默认值，不冒充工程规范；相对误差以各方法观测面积为基准。"""
    absolute_m2: float = Field(default=0.01, ge=0, strict=True)
    relative: float = Field(default=0.005, ge=0, lt=1, strict=True)


def _area_check(method, asserted, observed, tolerance, **extra):
    if type(observed) not in (int, float) or not math.isfinite(observed) or observed < 0:
        return _check(method, '未知', '面积观测不是有效的有限非负值，无法应用容差', '执行失败',
                      area_comparison=True, asserted=asserted, observed=None, tolerance_m2=None,
                      relative_tolerance=tolerance.relative, absolute_tolerance_m2=tolerance.absolute_m2, **extra)
    threshold = max(tolerance.absolute_m2, tolerance.relative * abs(observed))
    numeric = type(asserted) in (int, float) and math.isfinite(asserted)
    difference = asserted - observed if numeric else None
    overflow = numeric and not math.isfinite(difference)
    if overflow:difference = None
    return _check(method, '支持' if numeric and asserted >= 0 and not overflow and abs(difference) <= threshold else '矛盾',
                  '按记录的面积容差核对；不证明轮廓识别正确', area_comparison=True,
                  asserted=asserted, observed=observed, difference_m2=difference,
                  absolute_difference_m2=abs(difference) if difference is not None else None,
                  difference_overflow=bool(overflow),
                  tolerance_m2=threshold, relative_tolerance=tolerance.relative,
                  absolute_tolerance_m2=tolerance.absolute_m2, **extra)


def _summarize_areas(checks):
    # 两种方法均有结果才能综合；分歧留待复核，不由任一来源独占真值。
    fields = dict.fromkeys(c['field'] for c in checks if c.get('area_comparison'))
    for field in fields:
        methods = [c for c in checks if c.get('area_comparison') and c['field']==field]
        outcomes = {c['conclusion'] for c in methods}
        conclusion = ('未知' if len(methods)!=2 or '未知' in outcomes else
                      '需复核' if outcomes=={'支持','矛盾'} else
                      '矛盾' if '矛盾' in outcomes else '支持')
        checks.append(_check('面积综合', conclusion,
            '读取与重算不一致，请复核两种依据' if conclusion=='需复核' else '汇总两种方法，未覆盖的依据仍为未知', field=field))



class Span(Model):
    start: int = Field(ge=0)
    end: int = Field(ge=0)


class Claim(Model):
    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    span: Span
    refs: list[str]
    values: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    kind: Literal['reference', 'area', 'status', 'unsupported'] = 'reference'
    extraction: Literal['manual', 'model', 'producer'] = 'manual'
    generated_by: str | None = None


class ClaimsDocument(Model):
    schema_version: Literal['claims.v1'] = 'claims.v1'
    original_text: str
    original_text_origin: Literal['full_original', 'legacy_claim_texts'] = 'full_original'
    claims: list[Claim]
    legacy_reason: str | None = None
    model_name: str | None = None
    transcript_refs: list[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def check_spans(self):
        if len({claim.id for claim in self.claims}) != len(self.claims):
            raise ValueError('主张编号重复')
        for claim in self.claims:
            if claim.span.end <= claim.span.start or self.original_text[claim.span.start:claim.span.end] != claim.text:
                raise ValueError('主张位置与原文不一致：' + claim.id)
        return self


def parse_document(payload):
    if isinstance(payload, ClaimsDocument):
        return payload
    if not isinstance(payload, dict):
        raise ValueError('主张输入必须是结构化对象')
    if payload.get('schema_version') == 'claims.v1':
        return ClaimsDocument.model_validate(payload)
    # 旧Answer没有全文；拼接内容明确标为旧主张文本，不能伪称恢复了完整原文。
    from .ai import Answer
    answer = Answer.model_validate(payload)
    original, claims, offset = '\n'.join(c.text for c in answer.claims), [], 0
    for index, claim in enumerate(answer.claims):
        kind = 'area' if any(k.endswith('.area_m2') for k in claim.values) else 'status' if affirmative(claim.text, '已确认|确认无误|确定合规|已通过|判定通过|审查通过|仍有效|仍然有效') else 'reference'
        claims.append(Claim(id=f'claim_{index+1}', text=claim.text, span=Span(start=offset, end=offset+len(claim.text)), refs=claim.object_ids, values=claim.values, kind=kind, extraction='producer', generated_by='legacy Answer（自报）'))
        offset += len(claim.text)+1
    return ClaimsDocument(original_text=original, original_text_origin='legacy_claim_texts', claims=claims, legacy_reason=answer.reason)


def _check(method, conclusion, reason, execution='已执行', **extra):
    return dict(method=method, conclusion=conclusion, execution=execution, reason=reason, **extra)


def _locator(obj):
    return {'handle': obj.source.handle, 'block_path': list(obj.source.block_path), 'xref_path': list(obj.source.xref_path),
            'type': getattr(obj, 'type', getattr(obj, 'feature_kind', None))}


def _fact_fingerprint(fact):
    return digest({'geometry': fact.geometry.model_dump(), 'measurements': fact.measurements.model_dump(), 'reason_codes': fact.reason_codes})


def _dependencies(resolution, tools):
    if resolution.kind == 'object':
        obj = resolution.raw
        return [{'kind': 'object', 'id': resolution.ref, 'fingerprint': object_fingerprint(obj), 'locator': _locator(obj)}]
    row = resolution.raw or {}
    ids = row.get('object_ids', []) if resolution.kind == 'finding' else [i['object_id'] for i in row.get('inputs', [])] if resolution.kind == 'decision' else []
    dependencies = [{'kind': 'object', 'id': oid, 'fingerprint': object_fingerprint(tools.objects[oid]), 'locator': _locator(tools.objects[oid])} for oid in ids if oid in tools.objects]
    rule = row.get('decision', {}).get('rule') if resolution.kind == 'finding' else row.get('rule')
    if rule is None and resolution.kind == 'finding' and row.get('rule_id'):
        try:rule = rule_metadata(row['rule_id'])
        except ValueError:rule = {'id':row['rule_id'],'sha256':None}
    if rule:
        dependencies.append({'kind': 'rule', 'id': rule['id'], 'fingerprint': rule['sha256']})
    value = resolution.value or {}
    if resolution.kind=='historical_object':
        dependencies.append({'kind':'comparison','id':resolution.ref,'fingerprint':digest({'old_hash':tools.changes_data['old_hash'],'record':row})})
    if resolution.kind in ('change', 'impact'):
        dependencies.append({'kind':'comparison','id':resolution.ref,'fingerprint':digest({'old_hash':tools.changes_data['old_hash'],'new_hash':tools.changes_data['new_hash'],'change':row})})
    # 引用自身状态是依赖，去掉随版本重编号的ID；普通对象用内容指纹覆盖。
    stable = {k: v for k, v in value.items() if k not in ('id', 'object_ids', 'source_handles', 'values', 'old', 'new', 'inputs', 'run_id', 'evidence_refs', 'finding_id')}
    dependencies.append({'kind': 'reference', 'id': resolution.ref, 'fingerprint': digest(stable)})
    return dependencies


def _aggregate(checks):
    conclusion = '矛盾' if any(c['conclusion']=='矛盾' for c in checks if not c.get('area_comparison')) else '未知' if not checks or any(c['conclusion']=='未知' for c in checks) else '需复核' if any(c['conclusion']=='需复核' for c in checks) else '支持'
    execution = '执行失败' if any(c['execution']=='执行失败' for c in checks) else '无验证器' if any(c['execution']=='无验证器' for c in checks) or not checks else '已执行'
    return conclusion, execution


def check_claims(directory, document, changes=None, output=None, registry=None, area_tolerance=None, review_records=None, status_basis='current'):
    if status_basis not in ('current','frozen_record'):raise ValueError('状态依据必须为current或frozen_record')
    document = parse_document(document)
    area_tolerance = AreaTolerance.model_validate({} if area_tolerance is None else area_tolerance)
    tools = ReadTools(directory, changes)
    review_records=[] if review_records is None else review_records
    if review_records:
        from .reviews import validate_review_events,apply_reviews
        validate_review_events(review_records)
        apply_reviews(list(tools._findings().values()),tools.data.drawing.sha256,review_records)
    snapshots = {L1:load(directory,L1), L2:load(directory,L2), L3:tools.data}
    if len({layer.drawing.sha256 for layer in snapshots.values()}) != 1:
        raise ValueError('扫描各层图纸哈希不一致')
    l2 = snapshots[L2]
    tools.facts = {fact.geometry_id:fact for fact in l2.facts}
    registry = registry or default_registry()
    rows = []
    for claim in document.claims:
        checks, dependencies, versions = [], [], {}
        resolved = {ref: registry.resolve(tools, ref) for ref in dict.fromkeys(claim.refs)}
        for ref, result in resolved.items():
            if result.resolver:
                versions[result.resolver] = result.version
            if result.found is None:
                checks.append(_check('引用查找', '未知', result.reason, result.execution, ref=ref))
            else:
                checks.append(_check('引用查找', '支持' if result.found else '矛盾', (result.reason or '引用存在') if result.found else '已知命名空间内引用不存在', ref=ref))
                if result.found:
                    try:
                        current_dependencies = _dependencies(result, tools)
                        dependencies.extend(current_dependencies)
                        if any(d['fingerprint'] is None for d in current_dependencies):
                            checks.append(_check('状态比对','未知','规则依赖文件不可用','无验证器',ref=ref))
                    except Exception as exc:
                        checks.append(_check('引用查找','未知','依赖记录失败：'+type(exc).__name__,'执行失败',ref=ref))
        if not claim.refs:
            checks.append(_check('引用查找', '未知', '没有结构化引用', '无验证器'))
        area_count = 0
        from .claim_status import state_checks,INHERITANCE_FIELDS
        for key, asserted in claim.values.items():
            owner, _, field = key.rpartition('.')
            if field in INHERITANCE_FIELDS:continue
            resolution = resolved.get(owner)
            if not resolution or not resolution.found:
                checks.append(_check('数值读取', '未知', '字段所属引用未解析或未声明', '无验证器', field=key))
                continue
            value = resolution.value or {}
            if field not in value:
                checks.append(_check('数值读取', '未知', '没有此字段的读取验证器', '无验证器', field=key))
                continue
            expected = value[field]
            if field == 'area_m2' and (l2.status == 'failed' or tools.data.status == 'failed' or l2.drawing.geometry_units != 'mm' or tools.data.drawing.geometry_units != 'mm'):
                expected = None
            if expected is None:
                checks.append(_check('数值读取', '未知', '依据字段缺失或不可用', '无验证器', field=key, area_comparison=field=='area_m2'))
            else:
                if field == 'area_m2' and type(expected) in (int, float):
                    checks.append(_area_check('数值读取', asserted, expected, area_tolerance, field=key))
                else:
                    equal = math.isclose(asserted, expected, rel_tol=0, abs_tol=1e-6) if type(asserted) in (int, float) and type(expected) in (int, float) else type(asserted)==type(expected) and asserted==expected
                    checks.append(_check('数值读取', '支持' if equal else '矛盾', '字段读取核对', field=key, asserted=asserted, observed=expected))
            if field == 'area_m2' and resolution.kind == 'object':
                area_count += 1
                obj = resolution.raw
                if l2 is None:
                    l2 = load(directory, L2)
                facts = {fact.geometry_id: fact for fact in l2.facts}
                for evidence in obj.evidence:
                    if evidence.kind == 'geometry_fact' and evidence.value in facts:
                        fact = facts[evidence.value]
                        dependencies.append({'kind':'geometry_fact','id':fact.geometry_id,'fingerprint':_fact_fingerprint(fact),'locator':_locator(fact)})
                from .light_calc import outline_polygon
                try:
                    polygon = outline_polygon(obj.geometry)
                    if l2.status == 'failed' or tools.data.status == 'failed' or l2.drawing.geometry_units != 'mm' or tools.data.drawing.geometry_units != 'mm':
                        raise ValueError('快照失败或单位不是毫米')
                    observed = polygon.area / 1e6
                    checks.append(_area_check('几何重算', asserted, observed, area_tolerance, field=key))
                except ValueError as exc:
                    checks.append(_check('几何重算', '未知', str(exc), '无验证器', field=key, area_comparison=True))
        if claim.kind == 'area' and not area_count:
            checks.append(_check('几何重算', '未知', '没有可核验的对象.area_m2主张', '无验证器'))
        status_checks,status_dependencies=state_checks(claim,resolved,tools,status_basis,_check)
        checks.extend(status_checks);dependencies.extend(status_dependencies)
        if claim.kind == 'unsupported':
            checks.append(_check('人工','未知','此主张类型没有验证器','无验证器'))
        _summarize_areas(checks)
        conclusion, execution = _aggregate(checks)
        rows.append({'claim':claim.model_dump(),'conclusion':conclusion,'execution':execution,'methods':list(dict.fromkeys(c['method'] for c in checks)), 'manual_review':'无','validity':'需复核' if conclusion=='需复核' else '有效','checks':checks,'dependencies':list({(d['kind'],d['id']):d for d in dependencies}.values()),'resolver_versions':versions})
    datasets = {model.__name__:snapshot_digest(directory,model,data) for model,data in snapshots.items()}
    result = {'schema_version':'claims-check.v1','validator_version':VERSION,'status_basis':status_basis,'review_records':review_records,'manual_context_sha256':digest(review_records),'area_tolerance':area_tolerance.model_dump(),'network_used':False,'document':document.model_dump(), 'full_original_preserved':document.original_text_origin=='full_original', 'drawing_hash':tools.data.drawing.sha256,'dataset_sha256':datasets,'changes_sha256':digest(tools.changes_data) if tools.changes_data else None,'rows':rows,'valid':bool(rows) and all(r['conclusion']=='支持' and r['execution']=='已执行' for r in rows), 'scope':('生成时冻结记录读取，只判断原文是否描述所给资料，不代表当前工程有效。' if status_basis=='frozen_record' else '')+'仅核验所声明的引用、结构化数值与有限状态措辞；不验证全部自然语言，不等于识别正确或专业通过。'}
    if output:
        path=Path(output)/'claims-check.json';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result



def validate_report_context(report, directory, delta=None):
    if report.get('schema_version') != 'claims-check.v1' or report.get('validator_version') != VERSION:
        raise ValueError('核验报告格式或验证器版本不匹配')
    parse_document(report['document'])
    if report.get('manual_context_sha256') is not None:
        from .reviews import validate_review_events
        records=report.get('review_records',[])
        validate_review_events(records)
        if digest(records)!=report['manual_context_sha256']:raise ValueError('核验报告的人工复核上下文不匹配')
    AreaTolerance.model_validate(report['area_tolerance'])
    actual = {model.__name__:digest(load(directory,model).model_dump()) for model in (L1,L2,L3)}
    if actual != report['dataset_sha256']:
        raise ValueError('核验报告与扫描数据不对应')
    if report.get('changes_sha256') != (digest(delta) if delta else None):
        raise ValueError('核验报告与所依据的变更结果不对应')


def recheck_claims(directory, previous, changes=None, output=None, registry=None, area_tolerance=None, review_records=None):
    """在给定同图两版的上下文中按引用依赖重核，不以整包hash变化使所有主张失效。"""
    previous_document = parse_document(previous.get('effective_document', previous['document']))
    original_document = parse_document(previous['document'])
    tools = ReadTools(directory, changes)
    registry = registry or default_registry()
    if previous['drawing_hash'] != tools.data.drawing.sha256:
        if not tools.changes_data or tools.changes_data.get('old_hash') != previous['drawing_hash']:
            raise ValueError('跨图纸哈希重核需要对应旧版→新版的变更结果')
    facts = {f.geometry_id:f for f in load(directory,L2).facts}
    object_mapping, fact_mapping, unresolved = {}, {}, set()
    old_rows = {r['claim']['id']:r for r in previous['rows']}
    if set(old_rows) != {c.id for c in previous_document.claims}:
        raise ValueError('旧报告的主张与结果行不一致')
    same_drawing = previous['drawing_hash'] == tools.data.drawing.sha256
    explicit_pairs = {}
    for change in (tools.changes_data or {}).get('changes', []):
        if change.get('old'):
            explicit_pairs.setdefault(change['old']['id'], []).append((change.get('new') or {}).get('id'))
    target_counts = Counter(values[0] for values in explicit_pairs.values() if len(values)==1 and values[0])
    for row in previous['rows']:
        for dependency in row['dependencies']:
            kind, identifier = dependency['kind'], dependency['id']
            if kind not in ('object', 'geometry_fact'):
                continue
            current = tools.objects if kind == 'object' else facts
            paired = explicit_pairs.get(identifier) if kind == 'object' else None
            if paired is not None:
                target = paired[0] if len(paired) == 1 and paired[0] in current and target_counts[paired[0]] == 1 else None
            else:
                target = identifier if same_drawing and identifier in current else None
            if target is None and paired is None:
                candidates = [o for o in current.values() if _locator(o) == dependency.get('locator')]
                if len(candidates) == 1:
                    target = candidates[0].semantic_id if kind == 'object' else candidates[0].geometry_id
            mapping = object_mapping if kind == 'object' else fact_mapping
            mapping[identifier] = target
            if target is None:
                unresolved.add(identifier)
    reference_mapping = dict(object_mapping)
    delta = tools.changes_data or {}
    for row in delta.get('conclusion_changes', []):
        if row.get('old_id'):
            reference_mapping[row['old_id']] = row.get('new_id')
    for row in delta.get('decision_inheritance', []):
        reference_mapping[row['old_decision_id']] = row.get('new_decision_id')
    effective = previous_document.model_copy(deep=True)
    for claim in effective.claims:
        claim.refs = [reference_mapping.get(ref) or ref for ref in claim.refs]
        values = {}
        for key, value in claim.values.items():
            owner, _, field = key.rpartition('.')
            values[(reference_mapping.get(owner) or owner)+'.'+field] = value
        claim.values = values
    result = check_claims(directory, effective, changes, registry=registry, area_tolerance=area_tolerance, review_records=review_records if review_records is not None else previous.get('review_records',[]))
    for row in result['rows']:
        old = old_rows[row['claim']['id']]
        new_deps = {(d['kind'], d['id']):d['fingerprint'] for d in row['dependencies']}
        changed, reasons = False, []
        for dependency in old['dependencies']:
            kind, identifier = dependency['kind'], dependency['id']
            target = fact_mapping.get(identifier) if kind == 'geometry_fact' else reference_mapping.get(identifier, identifier)
            if kind == 'rule':
                target = identifier
            if target is None or new_deps.get((kind,target)) != dependency['fingerprint']:
                changed = True
                reasons.append(kind+':'+identifier+' 变化或无法唯一匹配')
        if previous['validator_version'] != VERSION or previous.get('area_tolerance') != result['area_tolerance'] or old.get('resolver_versions') != row['resolver_versions']:
            changed = True
            reasons.append('验证器版本变化')
        if any(ref in unresolved or (ref in reference_mapping and reference_mapping[ref] is None) for ref in old['claim']['refs']):
            row['checks'].append(_check('状态比对','未知','旧版引用无法唯一映射到新版','无验证器'))
            row['conclusion'], row['execution'] = '未知', '无验证器'
            changed = True
        row['validity'] = '需复核' if changed or row['conclusion']=='需复核' else '有效'
        row['recheck_reasons'] = reasons
        row['original_claim'] = old['claim']
    result['effective_document'] = result['document']
    result['document'] = original_document.model_dump()
    result['recheck'] = {'previous_report_sha256':digest(previous),'context_updated':previous['dataset_sha256'] != result['dataset_sha256'] or previous.get('changes_sha256') != result['changes_sha256'], 'mapping_method':'同图两版上下文＋唯一来源实例；不确定则需复核','reference_mapping':reference_mapping}
    result['valid'] = bool(result['rows']) and all(r['conclusion']=='支持' and r['execution']=='已执行' and r['validity']=='有效' for r in result['rows'])
    if output:
        path=Path(output)/'claims-check.json';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result
