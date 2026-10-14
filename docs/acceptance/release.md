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

## 本次结果

Python既有85项通过，C#核心69项通过。Ubuntu CI、Pages均已通过；具体记录见eval/runtime.md。源码元数据版本变动后运行既有Python回归，结果以工作流为准。源图字节未核验单列，不算设计通过。

## v0.3.1

保留v0.3.0及现有仓库身份，只建立新标签v0.3.1。新版包含类型明确的来源字段、5房间＋5灯具导出对象抽查、正式通知、闭合异形房间LPD与估算照度、全图前后截图、两页作品PDF和SHA256。人工计时为两人各一次用户报告，与自动冻结检出记录分开。
