# 规则与报告验收

```powershell
python -m cst check samples/A
python -m cst check samples/B
python -m cst report samples/A --output dist/reports/A.html
python -m cst light-calc samples/A
python -m cst light-calc --synthetic
```

原A/B的R1分别有2/1项凭人工核对满足本项条件。单层R3返回缺上一层资料；R4区别贴邻风险与防水资料缺口。“宜”的不满足为提示。未触发条件记不适用，不计通过；用途未知是缺输入。

矩形SYNTHETIC算例9m×7m，演示估算15盏、200lx、4.762W/㎡；30个几何候选回算400lx、9.524W/㎡。真实异形机房显示需人工计算。h=2.4m、U=0.7等为演示参数；完整灯具功耗与规范表格值仍需核实。

规则起草可运行`python -m cst draft-rule --replay --cache ai_cache/draft_8207071988f47e84b2e38bca.json --output dist/rule-drafts`。草案保留approved:false，由工程师核对；另一缓存draft_4b4985074e1ddb72c9558a79.json应返回needs_new_predicate。

HTML中应看到结论、条款和源Handle。规则依据见[出处](../guides/rule-references.md)，新增规则不自动审批。
