# 离线演示验收

仓库根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_demo.ps1
```

Linux/macOS使用`sh scripts/run_demo.sh`。已安装依赖时，可加-SkipInstall或--skip-install。首次安装需要网络；演示禁止网络访问，不需要CAD或API key。

应完成A/B读取、引用检查、规则、灯具候选、查看器，以及A→A-change的diff、云线、证据包和通知重放。真实问答重放8例、规则草案2例，合成错误引用控制另计。

A/B空间数为73/48，R1已核对条件分别2/1项通过。断链不得静默通过；公开包无DWG时跳过源字节核验，不计失败。查看dist/demo/manifest.json核对本次结果。

打开dist/demo/changes/semantic_view.html，查看改动清单和优先风险；dist/demo/notifications/notice.md为待签字通知。报错先检查Python版本、依赖、完整输入目录和缓存绑定。
