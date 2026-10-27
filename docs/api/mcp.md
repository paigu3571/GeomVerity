# 只读MCP接口

安装`python -m pip install ".[mcp]"`，启动`python -m cst.mcp_server samples/A-change --changes 实际diff.json`。仅处理指定快照及对应比较；不调用模型、不写人工确认、不改CAD。

提供9个工具：summary、list_objects、get_object、get_evidence、list_findings、get_changes、get_impacts、list_decision_inheritance、claims_check。分页offset≥0、limit为1–100。get_changes可按type筛选；get_impacts读取限定影响候选/建议工作、当前页相关房间复核和灯组，不等于批准；list_decision_inheritance可按status筛选，返回原记录和策略版本，不为旧记录补造新状态。

get_object只接受当前扫描对象ID。get_evidence支持sem_、finding_、decision_、change_、impact_change_；当前对象返回source/evidence，其他类型返回kind/record/raw/note。比较旧侧的对象/决策也可读取；旧对象仅有diff冻结字段，不能在没有旧几何的情况下计算旧面积。claims_check与CLI使用同一解析器；支持旧引用存在不代表它在新版存在。陌生命名空间未知，不误报矛盾。handle可能对应多个对象，必须结合semantic ID、类型、来源实例及版本。

`claims_check(document, area_tolerance=None, rows_only=False, status_basis="current")`使用claims.v1全文、Unicode字符位置及显式refs/values。rows_only=true省略document及全文，只返回rows、validator_version、status_basis、valid、scope；每行保留原句与依赖。默认返回完整原文报告。调用固定output=None，不写文件。状态values与例子见仓库skills/geomverity-verify/SKILL.md。

默认current按inheritance.2重算；旧diff不当当前策略。显式frozen_record只判断AI是否忠实描述冻结资料，读取旧记录状态，不证明旧算法或当前工程正确。当前pending_identity的正面继承主张返回需复核；原确认内容变化为invalidated；无旧签字为unconfirmed。requires_confirmation说明尚需来源对应确认；confirmation_available说明是否取得可带入新版的原确认材料，不代表新签字已完成。

顶层valid是本次所有行支持且已执行的综合布尔（重核还要求每行有效性有效），不是工程通过。行validity是工具结果在所给上下文的适用性；有效的矛盾结果仍然是矛盾，不可解释为主张正确。结论/执行/方法/人工复核/有效性应分别展示。有限状态检查和引用存在不覆盖全文所有语义。
