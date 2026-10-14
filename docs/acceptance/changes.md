# 变化、候选出图与查看器

```powershell
python -m cst diff samples/A samples/A-change --output dist/changes/example
python -m cst cloud dist/changes/example/diff.json --output dist/changes/example/impact_cloud.dxf
python -m cst view samples/A-change --changes dist/changes/example/diff.json --generated dist/changes/example/lighting_candidates.json --output dist/changes/example/semantic_view.html
```

应生成变化清单、专业影响、旧确认和灯组失效资料。程序对象候选数量与8次人工修改分别统计。优先显示出口减少与水泵房贴邻风险；云线合并核心范围，细部用颜色和清单表达。

点击房间、灯具、门洞或邻房，应能看到对应输入、规则与源Handle。旧门和失效灯组用灰色虚线，新灯组为红色。壁灯候选贴墙并按已提取开口避让，独立DXF不改原图。

漏房诊断：`powershell -ExecutionPolicy Bypass -File scripts/run_room_recovery.ps1 -InputDirectory samples/A`。结果在dist/recovery；重建候选带源引用，不移动文字或补画墙。不同图纸不套用旧样例人工确认。公开脱敏快照的房名覆盖可能不同于原扫描。

匹配不足、资料缺失或不规整轮廓按结果核对，不把有限范围无候选说成整套设计无影响。
