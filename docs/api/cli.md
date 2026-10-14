# 命令行

在仓库根目录安装`python -m pip install -e ".[dxf]"`。入口为`python -m cst`，参数以`python -m cst --help`及各子命令的`--help`为准。

| 子命令 | 用途 |
|---|---|
| summary / classify | 对象数量、状态和用途 |
| verify | 快照引用或证据包哈希检查 |
| check / report | 规则结果和离线HTML报告 |
| diff / cloud | 版本变化、影响清单和独立云线DXF |
| recover | 漏房候选、围合问题和文字位置诊断 |
| lights / light-calc | 布置候选及限定矩形的演示回算 |
| view | 生成离线SVG查看器 |
| ask / draft-rule / naming / notify | 受约束AI及缓存重放 |
| bundle / rule-impact | 决策证据包及规则版本影响 |

分析示例见[演示验收](../acceptance/demo.md)。DWG先由CAD宿主导出JSON；CLI没有独立DWG读取内核。输出集中dist，原始输入与人工确认记录保持独立。
