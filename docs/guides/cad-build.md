# CAD插件构建与加载

需要.NET SDK、.NET Framework 4.8开发包，以及合法安装的AutoCAD 2016；读取天正原生对象还需T20 V8。自定义安装路径使用ACAD2016_DIR或MSBuild属性AutoCAD2016Dir。

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_cs.ps1
```

没有AutoCAD时可加-CoreOnly，仅运行核心契约测试。完整构建输出位于cs/src/JZBP.BuildingSemantics/bin/x64/Release/net48；DLL旁应有profiles/generic.project-profile.v1.json。商业宿主程序集不随本项目分发。

## 加载与扫描

1. 保存图纸，启动新的CAD进程；同名程序集不做热替换。
2. 输入NETLOAD，选择构建生成的JZBP.BuildingSemantics.dll。
3. 打开已保存DWG，输入JZBPSCAN。
4. 输出在图纸目录的building-semantics-artifacts中；将配套L1/L2/L3文件夹交给Python读取器。

可用`powershell -ExecutionPolicy Bypass -File scripts/prepare_cad_test.ps1`生成dist/cad-load/load-plugin.scr，再在CAD输入SCRIPT加载。

通用配置随插件提供，不要求图纸固定名称或目录。显式配置文件使用JZBP_PROFILE，配置目录使用JZBP_PROFILE_ROOT；配置仍决定词典、单位和识别参数。缺少配置时重新构建并检查profiles，不复制配置到每张图旁边。

JZBPREGION是预设观察区回执工具；通用配置未登记观察区时，日常扫描不需要它。Windows构建和核心测试通过不代替真实CAD加载验收。

[历史宿主记录](../acceptance/cad-host-validation.md) · [原生契约](../api/schema.md)

## 使用其他制图标准或版本

AutoCAD 2016＋T20 V8是当前实测组合。默认generic配置包含具体图层和房名约定；换单位标准需核对映射、围合和样例，换宿主版本需另外验证插件加载与对象读取。配置可自定路径，使用步骤、已有诊断的补齐动作和社区贡献入口见[图纸适配指南](drawing-adaptation.md)。
