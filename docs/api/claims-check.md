# 逐条主张核验（离线）

`python -m cst claims-check` 读取已有扫描与结构化主张，不调用模型、不读取DWG、不代替工程师确认。`claims.v1` 是旁挂契约，未修改L1/L2/L3或旧Answer模型。

## 可直接复现

在仓库根目录设置 `PYTHONPATH=python` 后执行：

```
python -m cst claims-check samples/A samples/claims/A-supported.claims.json --output dist/claims-example
python -m cst bundle samples/A --claims-check dist/claims-example/claims-check.json --output dist/claims-example-bundle
python -m cst verify dist/claims-example-bundle
```

主张文本由人工构造并标SYNTHETIC，不是外部AI响应；底层使用原有公开样例。首条命令核查一个实际对象引用。面积双层示例为 `samples/claims/A-area.claims.json`，可替换输入路径执行；它保留L2读取与派生轮廓之间的实际差异，默认工程核验容差下两者支持，预期退出0；未修补公开冻结数据。正确面积的独立合成正例与受控错误见 `python/tests/test_claims.py`。核验支持仅限声明字段，不证明识别正确或专业通过。

输入格式见 `python/cst/claims.v1.schema.json`。`original_text`保留全文；每条主张有id、text、span、refs、values、kind、extraction、generated_by。span使用Python/Unicode字符的左闭右开位置，不是UTF-8字节偏移；必须与原文切片完全一致。kind为reference/area/status/unsupported，extraction为manual/model/producer。生成者与模型名只作自报信息。模型抽取后须人工核对原文，不把未抽取内容当已核验。

旧 `Answer` 的 `text/object_ids/values` 可直接导入；原模型没有全文时，仅保存原有主张拼接文本，`original_text_origin=legacy_claim_texts`、`full_original_preserved=false`，拒答原因保留在legacy_reason。不能伪称恢复了黑盒模型全文或原始推理。

## 结果和退出码

每条结果分开记录conclusion（支持/矛盾/未知/需复核）、execution（已执行/无验证器/执行失败）、methods、manual_review（初始为无）和validity（有效/需复核/已失效）。`checks`保留各方法结果与观测值，`dependencies`保留对象、几何事实、规则与引用状态指纹。有效性描述记录在当前上下文的适用性，不代表主张为真或获得专业批准。

已知命名空间内不存在的引用是矛盾；未知命名空间/缺少上下文是未知；解析器异常是执行失败。面积先从L2读取，再复用照度模块的单一闭合轮廓转Polygon约束独立重算。缺面积、开放轮廓、多路径、无效轮廓、扫描失败或非毫米单位不能被默认为通过。重算使用现有路径，可能仍是原几何的近似；没有重做CAD识别。

确认措辞与现有输入条件复核记录比对；accepted数据状态不是工程师签字，更不是整间房设计合规。仍有效类措辞需有旧/新决策与唯一继承记录，调用inherit_decision重算；缺记录为未知，记录与重算不一致则需复核。

0＝本次核验全部支持且适用；1＝核验已执行，但包含矛盾、未知、执行失败或需复核；2＝参数/读取/格式错误。`valid`仅为上述兼容汇总，不是专业“通过率”。空主张列表不算核验通过。

## 换版重核与证据包

```
python -m cst claims-check <新版扫描> <原claims.json> --previous <旧claims-check.json> --changes <diff.json> --output dist/recheck
```

原文始终保留，引用映射单独记录。优先使用给定两版比较的唯一对象配对；否则仅在同图上下文按唯一来源实例匹配。依赖指纹/规则/使用的解析器版本变化、身份无法唯一匹配时需复核。整包或无关对象变化只提示上下文更新，不自动使所有主张失效。跨图纸哈希必须提供对应old_hash→new_hash的比较结果。

`bundle --claims-check` 显式收录核验报告，并核对它与扫描/变更上下文一致；原始核验用比较另存 `claims-context-changes.json`，避免证据包对changes.json的补充改变其哈希。`verify`校验清单和核验上下文；改动核验文件或漏列入清单会失败。哈希能检出清单覆盖的文件变化，不提供签名或原结论正确证明。

当前只核对声明的引用、标量值与有限状态措辞，不检出全文所有遗漏，也不核验任意专业结论。扩展解析器见[扩展指南](../guides/extending.md)。

## 面积容差（自claims-check.2起）

默认对每种观测来源独立使用max(0.01m², 观测面积绝对值×0.005)，这是可配置的产品核验参数，不声称来自工程规范。CLI用`--area-config <配置.json>`，文件如`{"absolute_m2":0.01,"relative":0.005}`；SDK用area_tolerance同名参数。非面积标量保持原有比较方式。

每个面积方法保留asserted/observed、带符号difference_m2、absolute_difference_m2、实际tolerance_m2和配置，未把差值四舍五入为0。两种方法都支持才综合支持；一支持一矛盾为“需复核（读取与重算不一致）”，不直接认定主张错误；两种都不支持才综合矛盾；任一来源缺失仍为未知。其他独立的引用或状态矛盾仍能使该主张矛盾。原始方法结果保留，不以综合结果覆盖。

报告记录area_tolerance及验证器版本。旧claims-check.1报告不能直接收录为当前报告，需要重核；版本或容差变动会使旧主张适用性需复核，避免静默继承旧结论。数据集和输入原文保持不变。

面积观测必须是有限非负值；重算非有限值返回未知/执行失败，不允许无限容差造成假支持。负面积主张不支持。有限输入的差值若超出浮点范围，difference_m2为null且difference_overflow=true，不能把Infinity写成有效JSON数字。


## 当前版本与迁移

validator_version 为 claims-check.4；比较为 changes.v2，继承策略为 inheritance.2。旧报告需重新核验，旧 diff 需重新比较，不静默修改历史报告或原扫描。

status_basis 默认 current；frozen_record 仅判断原文与冻结资料的一致性，不证明旧算法或当前工程正确。对象仅在比较旧侧存在时保留旧侧引用说明，缺少旧几何时不借用新版数值。状态值可显式使用 ref.inherited、ref.inheritance_status、ref.review_inheritance_status。

review_records 保存冻结人工上下文与摘要；确认或驳回不改专业 result。MCP 不提供写人工记录工具。工作台仅复用同一输入的只读模型与索引，每次重新核验主张；扫描、规则、比较或人工上下文变化后旧结果不能冒充当前结果。
