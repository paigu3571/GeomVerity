# 构建与测试

Python 3.11+：

```powershell
python -m pip install -e ".[dxf,mcp]"
python -m unittest discover -s python/tests -v
python -m cst.demo
```

离线演示不联网，模型实验通过公开缓存重放。新输入或新提示词需要重新生成匹配缓存；不得替换数据来绕过引用校验。

C#需.NET SDK及.NET Framework 4.8开发包。`powershell -ExecutionPolicy Bypass -File scripts/verify_cs.ps1 -CoreOnly`运行核心测试；插件编译另需合法AutoCAD程序集，见[CAD构建](cad-build.md)。

测试数据与合成控制在samples、eval和python/tests。生成输出放dist；日志、环境文件、私人讨论及临时工单不提交。改动保持小范围，先运行相关测试，提交前运行已有完整测试。
