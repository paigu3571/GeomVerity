# 扩展解析器、规则与核验

核心代码独立于桌面/Viewer。现有扩展点为 `ResolverRegistry.register(prefix, resolver, version=...)`；每次核验可传入自己的registry，不改默认全局状态。注册的是证据解析/取值函数，不是“返回accepted就能批准工程”的入口。增加新专业验证方法时，还须在claims核心增加检查、依赖记录和测试，界面只调用它。

## 一个可执行的只读扩展示例

在仓库根目录，安装本包或设置PYTHONPATH=python后执行：

```python
from cst.claims import check_claims
from cst.evidence import default_registry, Resolution

def space_count(tools, ref):
    if ref != 'summary:spaces':
        return Resolution(ref, 'external', False)
    count = sum(o.type == 'space' for o in tools.data.objects)
    return Resolution(ref, 'external', True, {'space_count': count})

registry = default_registry()
registry.register('summary:', space_count, version='SYNTHETIC-count.1')
text = '当前扫描含73个空间。'
document = {'schema_version': 'claims.v1', 'original_text': text,
    'claims': [{'id': 'count', 'text': text, 'span': {'start': 0, 'end': len(text)},
        'refs': ['summary:spaces'], 'values': {'summary:spaces.space_count': 73},
        'kind': 'reference', 'extraction': 'manual', 'generated_by': 'SYNTHETIC扩展示例'}]}
result = check_claims('samples/A', document, registry=registry)
assert result['valid']
print(result['rows'][0]['checks'])
```

这是对公开扫描对象计数的读取核对，不证明空间识别正确，也不是外部模型样本。返回值里的数值会进入引用依赖指纹；变更数量会在重核时影响相应主张。这里的methods仍为引用查找/数值读取，不冒充额外独立的专业验证。

## 解析器约定和测试

函数接收ReadTools与引用字符串，返回Resolution。已知前缀内确实不存在才给found=False；尚不支持的证据返回found=None、execution='无验证器'与原因。异常会记录为执行失败，不能吞掉异常返回支持。名称按最长前缀匹配，重复前缀拒绝注册；新方法必须更换version。数据和生成方自报不能写人工确认字段。

至少用SYNTHETIC小数据覆盖：支持、真实矛盾、缺资料未知、执行异常；无关对象变化不失效、实际依赖变化需复核、身份不确定不继承；若新增报告文件，显式收录bundle并验证篡改可检出。参考 `python/tests/test_claims.py`。运行 `python -m unittest discover -s python/tests -v` 与离线demo，再据实写验收边界。

## 新增规则

规则YAML放rules，写明id、版本、条款/参数来源与审批状态；未核实的值必须标演示/未批准。专业判断放Python核心，通过现有规则调用路径输出证据、依赖对象与缺资料原因，再增加公开/SYNTHETIC测试。不要往已有严格扫描模型追加UI或AI字段，也不要修改CAD识别以使评测“通过”。

规则/验证器版本变化应使相关确认需复核。模型提议、取值、几何重算与工程师签字属于不同方法；缺验证器不是错误，读取一致不是设计合规。

自定义registry需在SDK调用时显式传入；当前CLI默认使用内置解析器，不会自动加载任意Python插件。
