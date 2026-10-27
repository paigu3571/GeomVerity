# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 张田
"""扫描目录的只读体检；严格加载各层，格式缺口与扫描失败分别报告。"""
from collections import Counter
from pathlib import Path
from pydantic import ValidationError
from . import api
from .model import L1, L2, L3, FILENAMES


def _load_error(exc):
    if isinstance(exc, ValidationError):
        errors = exc.errors(include_input=False, include_url=False)
        details = '; '.join('.'.join(map(str, e['loc'])) + ': ' + e['msg'] for e in errors[:5])
        return f'字段不兼容（{len(errors)}项）：{details}'
    if isinstance(exc, FileNotFoundError):
        return '缺少文件：' + Path(exc.filename).name
    if isinstance(exc, PermissionError):
        return '没有读取权限'
    return f'{type(exc).__name__}：{exc}'


def inspect_scan(directory):
    """供脚本与工作台共用。不修补字段，不写回扫描，不执行专业审查。"""
    directory = Path(directory)
    loaded, layers = {}, {}
    for model in (L1, L2, L3):
        name = FILENAMES[model]
        try:
            loaded[model] = api.load(directory, model)
            layers[model.__name__] = {'loaded': True, 'error': None}
        except (OSError, ValueError, EOFError) as exc:
            layers[model.__name__] = {'loaded': False, 'error': _load_error(exc)}
    snapshot = loaded.get(L3) or loaded.get(L2) or loaded.get(L1)
    l3 = loaded.get(L3)
    objects = dict(sorted(Counter(o.type for o in l3.objects).items())) if l3 else None
    findings = dict(sorted(Counter(f.reason_code for f in l3.findings).items())) if l3 else None
    proxies = l3.proxy_ledger if l3 else (loaded[L1].proxy_ledger if L1 in loaded else None)
    unknown = sum(p.disposition == 'review_unknown' for p in proxies) if proxies is not None else None
    reason_codes = sorted({code for data in loaded.values() for code in data.reason_codes})
    # 格式可加载不等于扫描成功，0房间也不能显示为通过。
    load_ok = all(layer['loaded'] for layer in layers.values())
    rooms = objects.get('space', 0) if objects is not None else None
    failed = any(data.status == 'failed' for data in loaded.values())
    if not load_ok:
        conclusion = '数据不完整或格式不兼容：请查看各层加载原因'
    elif failed:
        conclusion = '扫描失败：需要天正解释器，本版不能用于分析' if 'T20_INTERPRETER_REQUIRED' in reason_codes else '扫描失败：请查看原因代码，本版不能用于分析'
    elif rooms == 0:
        conclusion = '未识别到房间：需复核图纸类型、名称与围合，不能视为通过'
    else:
        gaps = (unknown or 0) + findings.get('INVALID_GEOMETRY', 0) + findings.get('KNOWN_SPACE_LABEL_UNRESOLVED', 0)
        conclusion = f'可用于分析（有{gaps}条缺口记录需复核；不代表专业通过）'
    gap_total = unknown + findings.get('INVALID_GEOMETRY',0) + findings.get('KNOWN_SPACE_LABEL_UNRESOLVED',0) if unknown is not None and findings is not None else None
    tone = 'unknown' if not load_ok else 'failed' if failed else 'warning' if rooms==0 or gap_total or any(d.status!='accepted' for d in loaded.values()) else 'available'
    return {
        'tone':tone, 'gap_record_count':gap_total,
        'directory': str(directory), 'load_ok': load_ok, 'layers': layers,
        'drawing_file': snapshot.drawing.file_name if snapshot else None,
        'drawing_sha256': snapshot.drawing.sha256 if snapshot else None,
        'drawing_sha256_short': snapshot.drawing.sha256[:10] if snapshot else None,
        'generated_at_utc': snapshot.generated_at_utc if snapshot else None,
        'producer_version': snapshot.producer_version if snapshot else None,
        'profile_version': snapshot.profile.profile_version if snapshot else None,
        'fact_provider_id': snapshot.fact_provider_id if snapshot else None,
        'status': snapshot.status if snapshot else None, 'reason_codes': reason_codes,
        'layer_status': {model.__name__: data.status for model, data in loaded.items()},
        'objects_by_type': objects, 'room_count': rooms,
        'display_metrics': [
            {'label':label, 'count':sum(objects.get(t,0) for t in types) if objects is not None else None}
            for label,types in [('房间',['space']),('墙',['wall']),('门窗洞口',['door','window','opening'])]],
        'opening_count_note':'门窗洞口合计独立门对象、窗和opening记录；天正门可能记为opening。是对象记录数，不是实体门数量，不能相加推断识别准确率。',
        'primitive_count': len(loaded[L1].primitives) if L1 in loaded else None,
        'geometry_fact_count': len(loaded[L2].facts) if L2 in loaded else None,
        'unreadable_proxy_count': unknown, 'findings_by_reason': findings,
        'invalid_geometry_count': findings.get('INVALID_GEOMETRY', 0) if findings is not None else None,
        'unresolved_space_label_count': findings.get('KNOWN_SPACE_LABEL_UNRESOLVED', 0) if findings is not None else None,
        'conclusion': conclusion,
        'note': '缺口计数是记录条数，可能重叠，不是漏识别率；加载成功不代表扫描成功或专业通过。',
    }


def inventory(root):
    """以任一正式层文件发现扫描目录；.raw不是独立扫描，支持压缩公开样例。"""
    root = Path(root)
    if not root.is_dir():
        raise ValueError('扫描根目录不存在或不是目录')
    names = {name + suffix for name in FILENAMES.values() for suffix in ('', '.gz')}
    directories = sorted({p.parent for p in root.rglob('*') if p.name in names and p.is_file()})
    return [inspect_scan(directory) for directory in directories]
