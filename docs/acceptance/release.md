# 0.3.0发布验收

在仓库根目录运行：

```powershell
python -m pip install -e ".[dxf]"
python -m unittest discover -s python/tests -v
python -m cst.demo --changes-only
python scripts/scan_secrets.py
```

预期：既有测试通过；生成dist/demo/changes/semantic_view.html及通知、证据包；安全检查0项。打开HTML查看删门风险、贴邻风险和灯具证据。

内存不足时直接打开Release离线演示包中的HTML，不要求重算。出现其他错误时保留命令及末尾输出提交Issue，不修改冻结快照或哈希来绕过检查。CAD扫描仍需合法宿主；本次不覆盖生产DLL。
