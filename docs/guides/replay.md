# L1离线重算

现有C#契约测试控制台支持--layers-replay，复用生产核心的AnalyzeLayers和输入适配。运行需要.NET SDK及.NET Framework 4.8开发包，不需要AutoCAD。

```powershell
powershell -ExecutionPolicy Bypass -File scripts/replay_l1.ps1 -L1Json "<原始L1 JSON路径>"
```

可用-Profile指定对应公开配置。输出LAYER_REPLAY、空间数量和L2/L3内容哈希。对同一原始快照重复运行时，比较内容哈希；生成时间可能不同，不要求文件字节逐一相同。

既有原始A/B来源测试分别重算73/48个空间、状态Review，两次内容哈希相同。公开samples经过脱敏，原扫描canonical摘要仅作来源记录，不能直接当清理后内容的旧C#重算输入；当前公开演示采用Python读取和后续分析。

此入口提供统计与内容哈希，未承诺完整成果导出或跨平台重建。内容哈希不符时检查输入和配置，不绕过校验。
