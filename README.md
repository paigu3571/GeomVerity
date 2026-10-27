# GeomVerity · 几何求真

工程 AI 成果可追溯与多层核验：在本机对照 CAD 扫描、版本变化与工程意见，让工程师看图复核并记录处理依据。

[下载程序（Release）](https://github.com/paigu3571/GeomVerity/releases/tag/v0.4.0-beta.1) ｜ [演示视频（待录制）](#演示视频) ｜ [使用文档](docs/README.md)

**打开公开示例 → 按房间看改动 → 对照 AI 意见与图纸 → 记录人工复核 → 导出证据包。**

当前版本：**v0.4.0-beta.1 预览版**。维护者已授权发布；已知局限与未完成项继续公开记录。验收与待办见[发布检查记录](docs/acceptance/release-0.4.md)。

| 首页与公开示例 | 换版：按房间处理 |
|---|---|
| ![比赛候选包：首页](docs/images/v0.4/project.png) | ![比赛候选包：换版按房间](docs/images/v0.4/changes.png) |
| AI 说的与图纸实际 | 同一图纸改前与改后 |
| ![比赛候选包：AI意见对照](docs/images/v0.4/ai.png) | 改前/改后实拍待补（不使用已知灯具显示有误的旧图） |

以上三张为10/28既有比赛候选包的公开示例实拍，来源见[图片清单](docs/images/v0.4/provenance.json)。本次公开分支新包截图暂未取得，四张最终实拍仍待补，维护者已批准按当前资料发布预览版。程序条数是候选记录数，不能当作人工改动数、识别准确率或整图合规结论。

## 快速开始（Windows）

1. 从 Release 选择所需版本，下载程序 ZIP 和 SHA-256 清单；预览版标为 Pre-release。
2. 解压**整个**文件夹，双击 `GeomVerity/GeomVerity.exe`。EXE 与 `_internal` 等配套文件必须放在一起，不能单独复制 EXE。
3. 需要系统已安装 **Microsoft Edge WebView2 Runtime**。程序无法启动时，先检查运行时；也可运行 `GeomVerity.exe --browser` 使用本机浏览器工作台。
4. 在“项目与体检”打开公开示例，从 A 与 A-change 开始。B 是另一张图，不是 A 的新版。
5. 按“换版 → 图面 → AI核验 → 人工复核 → 导出”体验。首次生成和比较需要等待；不要把“无法判定”当成通过。

自己的图纸先在合法 CAD 宿主中采集成 JSON，再导入扫描目录。工作台不会直接读取 DWG；采集说明与适配边界见[上手指南](docs/guides/workbench.md)和[图纸适配](docs/guides/drawing-adaptation.md)。

## 这一版能做什么

- 扫描资料体检、源对象定位、两版变化和限定电气影响候选，按房间组织复核。
- 对照已有工程意见中的结构化主张、图纸记录与旧确认状态；不一致项可跳转到对应复核。
- 保存本机人工意见、待补资料和驳回履历，导出带文件摘要的证据包。
- 灯具布置与照度估算保留为实验候选，供看图研究，不能直接施工或视作专业批准。

[能力状态表](docs/status.md) ｜ [已知局限](limitations.md) ｜ [源码开发与接口](docs/README.md)

## 演示视频

**待维护者用最终比赛包录制并提供链接。** 当前不把旧演示冒充本版视频；发布前在这里补入视频或 Release 附件链接。

## 从源码运行

需要 Python 3.11 或更高版本。在仓库根目录安装 `python -m pip install -e ".[desktop,dxf]"`，使用 `python -m cst.desktop` 启动；无桌面壳时可加 `--browser`。完整离线演示为 `python -m cst.demo`，快速子集为 `python -m cst.demo --quick`，二者验收范围不同。

MCP 为可选只读接口，见[接口文档](docs/api/mcp.md)。项目分发包名保留 `cad-semantic-trace`。

## 作者、许可与贡献

作者与维护者：张田。源码采用 [MPL-2.0](LICENSE)，第三方组件及来源见 [NOTICE](NOTICE)。请保留原作者与许可证；贡献前阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。不提交原始项目图纸、客户资料、密钥或私人复核记录。
