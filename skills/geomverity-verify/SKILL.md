---
name: geomverity-verify
description: 使用GeomVerity只读MCP或CLI逐条核验工程AI文字的引用、面积及确认有效性，保留原文与不确定性；不用于直接识读DWG或替代工程师签字。
---

# 工程文字核验

输入为完整原文、用户授权的扫描目录，涉及换版还需该扫描作为新版的diff.json。只读本机JSON，不编辑CAD、不写人工确认、不发送公司扫描。另行调用外部模型须有用户授权。受控错误标SYNTHETIC，真实样本不改写。

先读summary和实际对象ID。用list_objects/list_findings取当前对象和规则结论；get_changes取新旧字段。get_impacts用于读限定影响候选、建议工作及相关房间复核，不是批准或整图影响分析。list_decision_inheritance分页读取旧/新决策ID及继承状态。仅handle不能唯一定位对象：同一图中可能对应多个语义对象，须同时核对semantic ID、类型、来源实例、版本；禁止直接按handle合并。

get_object只读当前扫描semantic ID。get_evidence可读sem_、finding_、decision_、change_、impact_change_：旧版对象仅返回diff保存的字段，缺少旧几何时保留未知；支持旧引用存在不证明该对象仍在新版。未给diff时，不能查旧版命名空间。未知命名空间为无验证器，已知范围确实不存在才是矛盾。

保留完整原文，按可独立判断的句/表格行建立claims.v1。每条text须等于original_text[span.start:span.end]，位置为Unicode字符数，不是UTF-16。模型划分extraction=model、generated_by填划分模型名；原文生成方model_name与划分方分开，不伪称人工。kind选reference/area/status/unsupported，refs是实际工具ID，values只填原文中明确声称的值，不从工具答案倒填主张。

## 状态主张的写法

先用list_decision_inheritance取唯一对应记录。推荐显式values，而非猜自然语言：

- `实际decision_ID.inherited`: true/false，核对该条原范围确认是否已带入新版。
- `实际decision_ID.inheritance_status`: inherited / pending_identity / invalidated / unconfirmed。
- `实际sem_ID.review_inheritance_status`: 对应房间输入确认状态。
- `实际decision_ID.result`: 原文声称的通过/不通过/无法判定；`实际decision_ID.status`是accepted/review的数据状态，不是inheritance_status。
- `实际对象ID.area_m2`: 原文声称的数值；工具分别读取与几何重算。

只有原文说了相应状态才填values。当前有限措辞也识别`inherited: true/false`、“可继承原范围确认”、“仍有效”、“原确认因变化失效”及“不能视为新版已确认”；复杂多房间、多规则及全量断言应拆开并明确引用。引用存在检查支持不证明其余句意。

完整最小例（将decision_ID替换成列表中的真实新决策ID；SYNTHETIC接口示例）：

```json
{"schema_version":"claims.v1","original_text":"原确认仍有效。","claims":[{"id":"c1","text":"原确认仍有效。","span":{"start":0,"end":7},"refs":["decision_ID"],"values":{"decision_ID.inherited":true},"kind":"status","extraction":"model","generated_by":"填写划分模型名"}]}
```

调用`claims_check(document=..., rows_only=true)`可只返回逐条结果、版本、valid和范围，不回带全文document；每行仍有原句及其依据。默认false返回完整报告。状态默认`status_basis="current"`重算当前策略，旧策略记录不冒充新策略；只有明确评估“AI是否忠实描述生成时冻结资料”才选`frozen_record`并提供已核对哈希的旧diff。该模式只读取历史记录，不证明旧算法正确，不是当前工程有效性。

## 解释结果

分别报告结论、执行、方法、人工复核、有效性。无验证器不等于错误；执行失败不等于矛盾；面积一致不证明识别正确或设计合规。

顶层valid表示此次所有行均支持且已执行（重核还要求行适用性有效），不是设计批准。每行validity表示该行报告在当前核验上下文的适用性；“有效”不等于其conclusion为支持，矛盾结果也可以是当前有效的工具结果。`pending_identity`的正面继承主张为需复核；`requires_confirmation=true`指尚缺工程师来源对应确认；`confirmation_available`指核心是否取得可带入的原确认材料，不表示新签字已完成。inherited仅限原记录范围，不能宣称整间房或整图通过。

没有MCP时，在仓库根目录用`python -m cst claims-check samples/A-change dist/claims.json --changes 实际diff.json --output dist/claims-result`；历史资料核验显式加`--status-basis frozen_record`。启动MCP：`python -m cst.mcp_server samples/A-change --changes 实际diff.json`。不要为结果好看增大容差、改原文或替工程师确认。
