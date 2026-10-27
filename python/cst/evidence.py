# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 张田
"""引用解析扩展点。未知命名空间与已知空间内的缺失引用分别返回。"""
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class Resolution:
    ref: str
    kind: str
    found: bool | None
    value: dict | None = None
    raw: Any = None
    execution: str = '已执行'
    reason: str = ''
    resolver: str = ''
    version: str = ''


class ResolverRegistry:
    def __init__(self):
        self._entries = {}

    def register(self, prefix: str, resolver: Callable, version='1'):
        if not prefix or prefix in self._entries:
            raise ValueError('解析器前缀为空或已注册：' + prefix)
        self._entries[prefix] = (resolver, version)

    def resolve(self, tools, ref):
        prefix = next((p for p in sorted(self._entries, key=len, reverse=True) if ref.startswith(p)), None)
        # 兼容历史对象ID，但不把陌生命名空间误报成编造对象。
        if prefix is None and ref in tools.objects:
            prefix = 'sem_'
        if prefix is None:
            return Resolution(ref, 'unknown', None, execution='无验证器', reason='没有此引用命名空间的解析器')
        resolver, version = self._entries[prefix]
        try:
            result = resolver(tools, ref)
            if not isinstance(result, Resolution):
                raise TypeError('解析器必须返回Resolution')
        except Exception as exc:
            result = Resolution(ref, 'unknown', None, execution='执行失败', reason='解析失败：' + type(exc).__name__)
        result.resolver, result.version = prefix, version
        return result


def _object(tools, ref):
    obj = tools.objects.get(ref)
    if obj is not None:return Resolution(ref, 'object', True, tools.get_object(ref), obj)
    delta=tools.changes_data or {}
    for change in delta.get('changes',[])+delta.get('identity_changes',[]):
        old=change.get('old')
        if old and old['id']==ref:
            return Resolution(ref,'historical_object',True,dict(old,version_side='old'),old,reason='旧版引用存在（仅diff保存的字段，不代表新版对象存在）')
    for change in delta.get('changes',[]):
        for room in change.get('impact',{}).get('rooms',[]):
            if room['id']==ref:
                return Resolution(ref,'historical_object',True,dict(room,version_side='comparison'),room,reason='比较影响范围中引用存在，版本侧以原记录为准')
    return Resolution(ref, 'object', False)


def _finding(tools, ref):
    row = tools._findings().get(ref);side='new'
    if row is None:
        side='old'
        row=next((f for f in (tools.changes_data or {}).get('old_check',{}).get('findings',[]) if f['id']==ref),None)
    return Resolution(ref, 'finding', row is not None, dict(tools._finding_reference(row),version_side=side) if row else None, row,reason='旧版引用存在' if row and side=='old' else '')


def _change(tools, ref):
    changes = getattr(tools, 'changes_data', None)
    if changes is None:
        return Resolution(ref, 'change', None, execution='无验证器', reason='未提供两版变更结果')
    row = next((r for r in changes['changes']+changes.get('identity_changes',[]) if r['id'] == ref), None)
    return Resolution(ref, 'change', row is not None, tools._change_reference(row) if row else None, row)


def _impact(tools, ref):
    result = _change(tools, ref.removeprefix('impact_'))
    if result.found and 'impact' not in result.raw:
        return Resolution(ref,'impact',None,execution='无验证器',reason='该记录仅有来源身份变化，未提供影响证据，不能补造')
    if result.found:
        return Resolution(ref, 'impact', True, tools.get_impacts(ref.removeprefix('impact_'))['items'][0], result.raw)
    result.ref, result.kind = ref, 'impact'
    return result


def _decision(tools, ref):
    import json
    path = tools.directory / 'decisions.json'
    if path.is_file():
        rows = json.loads(path.read_bytes())['decisions']
    else:
        rows = [f['decision'] for f in tools._findings().values() if f.get('decision')]
    row = next((r for r in rows if r['id'] == ref), None);side='new'
    if row is None:
        side='old'
        row=next((f['decision'] for f in (tools.changes_data or {}).get('old_check',{}).get('findings',[]) if f.get('decision',{}).get('id')==ref),None)
    if row is None and not rows:
        return Resolution(ref, 'decision', None, execution='无验证器', reason='没有可读取的决策记录')
    value = dict(row, version_side=side, status='accepted' if row.get('engineer', {}).get('confirmed_by') else 'review') if row else None
    return Resolution(ref, 'decision', row is not None, value, row,reason='旧版引用存在' if row and side=='old' else '')


def default_registry():
    registry = ResolverRegistry()
    for prefix, resolver in [('sem_', _object), ('finding_', _finding), ('change_', _change),
                             ('impact_change_', _impact), ('decision_', _decision)]:
        registry.register(prefix, resolver, version='2')
    return registry
