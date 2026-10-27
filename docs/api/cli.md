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

## 正式入口与项目/体检

安装本包后可用 `geomverity`，保留 `python -m cst` 完全等价入口；分发包名暂仍为cad-semantic-trace。`--help`列出每个子命令及中文用途，各命令参数说明见相应`--help`。

新增：

- `geomverity project new <已有项目文件夹> --name <项目名>`：新建旁挂文件，已有项目拒绝覆盖。
- `geomverity project add <项目文件或文件夹> <扫描目录> --name <版本名> [--note <说明>]`：添加引用，不复制扫描。
- `geomverity project select <项目文件或文件夹> <版本ID>`：使用show输出的ID切换并保存。
- `geomverity project show <项目文件或文件夹>`：读取项目、版本和当前选择。
- `geomverity inventory <扫描根目录> [--output <目录>]`：递归普查，逐层报告加载失败、扫描失败和零房间；默认仅输出JSON，指定output额外写inventory.json。
- `geomverity claims-check <扫描目录> <claims.json> [--changes <diff.json>] [--previous <旧报告>] [--output <目录>]`：离线核验；见[主张核验](claims-check.md)。

GUI、项目CLI与体检CLI共用project.py、inventory.py，不包含另一套判断逻辑。内部扫描的体检输出保留在本机dist，不提交。

## 退出码

| 码 | 含义 |
|---|---|
| 0 | 命令计算/写出成功；通常不等于工程审查通过。inventory即使有扫描失败也输出报告并返回0 |
| 1 | verify检出失败；或claims-check含矛盾、未知、执行失败、需复核 |
| 2 | 参数错误，或文件/格式/操作错误 |

其他审查命令成功返回0时，仍须查看各条规则结果，不能据退出0把“无法判定”改成通过。JSON为缩进输出；错误摘要写stderr。单纯引用存在不等于全文正确。

日常烟测可在仓库运行 python -m cst.demo --quick，输出独立dist/demo-quick并列出跳过项；默认不加--quick仍运行完整演示。快速子集不能代替工单完整回归、换版/证据包或冻结验收。
