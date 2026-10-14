# Python SDK

安装：`python -m pip install .`。示例规则随包安装；分析输入由调用者提供。

```python
from cst import api

snapshot = api.load("samples/A")
findings = api.check("samples/A")
changes = api.diff("samples/A", "samples/A-change", "dist/sdk/changes")
package = api.bundle("samples/A-change", "dist/sdk/bundle", "dist/sdk/changes/diff.json")
```

| 接口 | 输入与返回 |
|---|---|
| load(directory, model=L3) | 读取配套快照；返回Pydantic模型。L1/L2可通过model参数选择 |
| check(directory) | 返回规则结果、证据和汇总；不修改原快照 |
| diff(old_dir, new_dir, output) | 对比两版，返回汇总并将详细结果写入output |
| notify(old, new, ...) | 使用版本登记和变化生成通知；replay=True读取公开缓存 |
| bundle(directory, output, changes=None) | 导出快照、规则、决策和哈希清单 |

输出使用既有结构化契约。SDK不依赖Viewer或桌面窗口；AI缓存、版本登记、工程师确认及输入文件仍需与分析任务匹配。仓库附带的完整演示和术语实验使用源码可编辑安装：`python -m pip install -e ".[dxf]"`。
