# 图纸问题与房名审核验收

在线演示的“图纸问题”显示原扫描未关联房间的房名定位点、边界端点候选和文字位置建议。数据由现有Python诊断生成，绑定当前扫描文件哈希，不修改L1～L3，不新增房间。

1. 运行 `python -m cst.demo --changes-only`，打开 `dist/demo/changes/semantic_view.html`。
2. 点击“图纸问题”：房名下拉框应有问题项，图上有红色定位点。选择项目后右栏显示房名、Handle和中文原因；有端点或文字位置建议时显示橙色虚线。
3. 如提示诊断不对应当前扫描，请重新生成演示，不复制其他版图纸的诊断文件。

已有诊断可显式传入：`python -m cst view samples/A-change --issues dist/demo/changes/room_issues.json --output dist/demo/changes/semantic_view.html`。

工程师审核63项：43项采纳、20项修改；56项用途启用，采光天井及6项上空名称本阶段暂缓启用。原模型类别、人工修改和审批分别保存在 `eval/naming-engineer-review.json` 与 `rules/naming_proposals.yaml`。35/49是原始对照，不因审核更新而重算。

本轮实测：A-change显示30项定位提示（包含1项采光井暂缓说明），下拉选项与定位标记各30个，点击显示房名、文字Handle、建议与源墙Handle；浏览器脚本错误0项。Python完整测试86项通过，诊断侧车不改源输入，证据包哈希核验0项失败。
