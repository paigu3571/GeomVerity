# 引擎与证据结构

输入边界为cs/contracts中的v1 JSON契约。AutoCAD/T20适配器生成L1图元、L2几何和L3工程对象；Python读取这些快照，执行规则、版本比较与证据导出。

Python核心由model、verify、l4、changes、lighting、decisions等模块组成。cst.api提供薄接口；CLI串起已有模块。view.py/view.html负责呈现后端结果，desktop.py是可选外壳。移除Viewer与Desktop不会移除解析、规则或变更计算。

模型负责受约束的术语提议、问答、规则草案和协作通知。引用校验检查可验证字段；专业用途和规则的批准由工程师完成。开发辅助工具与这些产品功能是两类不同用途。

Decision记录输入对象及指纹、规则版本与哈希、结果、优先级、来源引用、模型缓存和人工确认范围。换版依赖变化后，旧确认失效；此前未确认的记录不会继承签字。

证据包包含快照、决策、规则及清单。哈希证明文件对应关系和完整性，不证明识别正确，也不是数字签名。没有原DWG时，源文件字节检查单独标为未核验。

[字段](../api/schema.md) · [证据包操作](../acceptance/evidence.md)
