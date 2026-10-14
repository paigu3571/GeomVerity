# 工程决策记录与外部接入

让机器去读、去算、去做重复的工作；让人去判断、去负责；让每一个判断都有出处。

## 当前实现与愿景

当前输入来自AutoCAD/T20中的天正插件，输出公开L1/L2/L3 JSON；Python执行规则、版本分析和候选布置，生成Decision与Trace Bundle。输入校验不按生产者名称放行或拒绝，按版本、类型、单位、引用和来源一致性读取。

外部生成方未来可把设计转换成同一JSON契约后接入。不同软件不会因为写了相同文件名而自动兼容：它必须提供真实对象、坐标、关系和来源证据。其他CAD、AI生成设计、审图/施工/运维适配均为愿景，目前没有第二种已实测输入适配器。

## 三层出处

数据层保存源版本、对象ID、Handle与实例路径；规则层保存规范条款、规范版本、审批人与规则文件SHA256；AI层保存原模型提议、引用校验、真实调用缓存和工程师修改。起草信息独立保存在rules/provenance.yaml，由元数据层补入Decision，不改判定表达式。

已有R1～R4的首次起草者没有独立登记，明确记录“历史未留存”，不补造模型、缓存ID或人为起草经历。共井规则有真实DeepSeek缓存；照明规则的参数与公式来自张田。SHA256按规则文件实际字节计算，写在导出记录/核对表，不把文件自身哈希循环写回原文件。

## Decision字段

|字段|含义|
|---|---|
|id / kind / result|决策记录标识、类型和本项结果；不等于工程签字|
|priority|后端生成的风险排序、处理动作与适用范围|
|inputs|依赖对象ID、快照SHA256、内容指纹和原输入状态|
|rule.id / version / sha256|规则标识、版本及文件字节摘要|
|rule.clauses|规范号、条号、正文和code_version|
|rule.drafted_by / approved_by|起草来源及审批人；未知历史来源如实登记|
|rule.provenance_sha256|独立起草元数据目录的内容哈希|
|engine_version / run_id|引擎版本与运行记录标识；完整来源见bundle-manifest|
|llm|本项是否使用模型、模型名及缓存ID；不代表所有判定由模型完成|
|engineer / sign_off_state|确认人、日期、范围和待签字状态；不是电子签名|
|evidence_refs|L3→L2→L1及规则/发现项引用|
|layout_sha256|照明计算使用的候选灯组摘要（有该输入时）|

确认继承：按跨版匹配映射比较原确认的依赖集合及内容指纹；规则SHA256、依赖内容、映射或集合有变化，原范围确认失效。无原确认不继承签字；不能把有歧义的匹配当成同一实体。当前工程出口确认样例已跑通，通用失效机制有测试；跨专业完整签字制度为发展方向。

规则溯源查询：`python -m cst rule-impact --code "GB 55024-2022" --bundle dist/demo/bundle --synthetic`。这是按规范引用找规则和Decision的假设修订演示，不断言规范已实际修订。

## 外部生成方接入步骤

1. 按[JSON字段契约](../api/schema.md)及cs/contracts中的Schema输出三层快照，保留schema_version、producer、时间、图纸来源摘要、单位和坐标系。
2. 为每个源对象提供ID和完整实例路径。天正来源使用Handle；外部适配器可在同一字符串字段记录稳定源对象标识，但必须标明来源种类，不能伪造CAD可定位性。
3. 补齐几何事实到原图元、空间到几何与文字的引用；空间用途、邻房关系和未核验信息分别记录，不用AI猜测填成已确认。
4. 三层必须对应同一来源版本。运行 `cst summary` 与 `cst verify` 检查类型、引用及来源一致性，再运行 `cst check` 或 `cst diff`，导出 `cst bundle` 并校验清单。
5. 通过[SDK](../api/sdk.md)、[CLI](../api/cli.md)或[MCP](../api/mcp.md)消费同一结果；下游保留源对象/规则/运行引用，不从Viewer文字反向生成工程事实。

有几何但缺源对象证据时，可以记录候选，不宣称已具备同等来源强度。转换后对象标识变化时，跨版身份须重新匹配。当前接口不是通用任意格式上传入口，也没有外部适配器能力自动协商模块。

## 开源方法的参照

SBOM记录软件组件和依赖，SLSA构建溯源记录产物从何处、何时、怎样产生。本项目借鉴“让来源随产物一起交付”的思路，面向工程结论记录依据、审批与换版后的有效性。这里是方法类比，项目没有宣称符合SLSA等级、使用数字签名或通过安全认证。

- [CISA：SBOM组件透明性](https://www.cisa.gov/sites/default/files/2024-10/SBOM%20Framing%20Software%20Component%20Transparency%202024.pdf)
- [SLSA：Provenance](https://slsa.dev/spec/v1.2/provenance)
- [愿景图](vision.svg)
