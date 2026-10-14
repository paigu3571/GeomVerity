# 只读MCP接口

安装`python -m pip install ".[mcp]"`，启动：

```powershell
python -m cst.mcp_server samples/A-change --changes dist/changes/example/diff.json
```

stdio接口提供summary、list_objects、get_object、get_evidence、list_findings、get_changes、get_impacts七个工具。get_changes可按type筛选；get_impacts分页仅返回当前页相关确认和灯组资料。

服务只读取指定快照及对应变更文件，不执行CAD编辑、模型调用或工程审批。工具的JSON参数以服务器暴露的Schema为准。

官方Python客户端验证命令：

`python scripts/mcp_client_check.py samples/A-change --changes dist/changes/example/diff.json`

结果写入dist/mcp。客户端与服务器使用同一份已支持输入；未提供变更文件时，变化查询没有两版上下文。
