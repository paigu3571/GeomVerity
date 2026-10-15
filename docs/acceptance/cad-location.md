# CAD源图定位验收

2026-10-15，本轮只修复查看器与CAD的定位适配，不改L1～L3识别、规则判定、原始JSON和已有标签。

## 发现与修复

旧按钮输出 `(sssetfirst nil (ssadd (handent "25507")))`。25507是外层块AcDbBlockReference，不是2#公变配电房，也没有缩放逻辑。命令没有报错不代表用户已经看到房间。

新命令从源WCS坐标生成窗口，自动缩放到房间或门洞范围；不改变图元，不切换布局或修改PICKFIRST。源Handle不可解析时提示打开对应扫描源图及版本。Handle只能做本图中的引用检查，不能独立证明打开的图纸版本正确。

2#公变配电房的房名文字Handle为51631。公开空间来自程序围合，不存在可以当作“CAD原生房间实体”的程序空间ID。嵌套文字与实例路径仍保留在来源字段；新命令不把选中整块当作选中了内部文字。未落入CAD的灯具候选不提供原图实体选择，用户可点“查看来源房间”。

## 分层验证

|验证|结果与边界|
|---|---|
|CAD只读查询|AutoCAD 2016/T20会话中的base001及V1副本均能解析51631为TDbText，25507为AcDbBlockReference；源文字包围盒与扫描WCS位置相符。|
|工程师实测|张田粘贴ZoomWindow命令后确认已跳到2#公变配电房。|
|修复命令宿主执行|同会话执行完整带保护的生成命令，返回LISP_OK；DBMOD执行前后均为20，没有增加图元修改标志。|
|嵌套文字高亮|单独测试vla-Highlight后，张田反馈没有明显变化；不计为通过，不宣称已经支持精确嵌套图元选中。|
|回归|大WCS与屏幕Y反向还原、32位整数溢出规避、嵌套块不整块选中、生成灯具不冒充原图实体、非法坐标与Handle注入保护均有测试。|

当前可用于演示的是“从查看器定位到CAD源图对应范围”；精确选中嵌套图元尚未完成。既有v0.3.2标签和附件不覆盖，本轮修复以新生成的查看器及main源码为准。


完整Python回归94项通过。后台浏览器实际点击复制按钮：命令引用房名文字51631、包含ZoomWindow、不再选择外层块25507；灯具候选页无原图实体选择按钮，来源房间入口可用，页面异常0项。

接口依据：[Autodesk：ZoomWindow使用WCS](https://help.autodesk.com/cloudhelp/2018/DEU/AutoCAD-ActiveX-Reference/files/GUID-179C3EF0-4F3F-4555-AD74-3489A21FA035.htm)、[Handle只在本图中解析](https://help.autodesk.com/cloudhelp/2024/ENU/AutoCAD-AutoLISP-Reference/files/GUID-AF6DD533-1A24-4687-96EB-F03F26050C07.htm)。
