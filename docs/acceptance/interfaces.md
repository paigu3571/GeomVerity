# SDK与MCP验收

普通安装`python -m pip install .`，用cst.api.load/check读取samples/A，应有73个Space及规则结果。包内示例规则不依赖源码工作目录的rules文件夹。

MCP需`python -m pip install ".[mcp]"`。生成[两版diff](changes.md)后运行：

`python scripts/mcp_client_check.py samples/A-change --changes dist/changes/example/diff.json`

七个工具应均调用成功，结果写入dist/mcp。get_changes(type=space)按类型返回，get_impacts分页带本页对应复核与灯组资料。不是CAD自动监视或编辑服务。

参数说明见[SDK](../api/sdk.md)和[MCP](../api/mcp.md)。规则资源缺失时重新安装本项目；两版哈希不对应时重新生成正确diff，不套用其他任务结果。
