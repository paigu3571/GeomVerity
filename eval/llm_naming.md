# 房名术语解析实测

三份快照及同源原扫描房名补充清单共112种房名候选（含未围合及上空标注）。人工词表有49种，其中49种出现在本次输入。模型与工程师一级分类一致35/49；这是本批房名的对照结果，不外推到其他图纸。

真实接口请求7次，模型deepseek-flash。人工答案未发送给模型。模型只收到类别名称和房名候选；格式校验检查枚举、完整性和审批状态，不证明专业分类正确。

## 不一致明细

| 房名 | 工程师分类 | 模型提议 | 模型理由 |
|---|---|---|---|
| 三网合一机房上空 | EXCLUDED | WEAK_CURRENT_ROOM | 三网合一机房上空属于弱电房间空间 |
| 光厅 | ARCHITECTURAL_ROOM | UNKNOWN | 名称含义不明确，无法判断用途 |
| 前室上空 | EXCLUDED | ARCHITECTURAL_ROOM | 前室上空空间，属建筑房间 |
| 检修间 | ARCHITECTURAL_ROOM | UNKNOWN | 检修间用途不明确，无法判断 |
| 水井上空 | EXCLUDED | PLUMBING_ROOM | 水井上空，属给排水房间 |
| 消防控制室 | WEAK_CURRENT_ROOM | ARCHITECTURAL_ROOM | 消防控制室属于建筑功能房间，非电气竖井或配电室。 |
| 电井上空 | EXCLUDED | ELECTRICAL_SHAFT | 电井上空属于电气竖井的投影空间。 |
| 电梯井上空 | EXCLUDED | ARCHITECTURAL_ROOM | 电梯井上空属于建筑电梯井道空间。 |
| 电梯厅上空 | EXCLUDED | ARCHITECTURAL_ROOM | 电梯厅上空属于建筑公共空间投影。 |
| 电气进线间 | SMALL_ELECTRICAL_ROOM | DISTRIBUTION_ROOM | 电气进线间属于配电相关房间。 |
| 电气间上空 | EXCLUDED | SMALL_ELECTRICAL_ROOM | 电气间上空属于电气间投影空间。 |
| 采光井 | EXCLUDED | ARCHITECTURAL_ROOM | 采光井属于建筑采光空间。 |
| 预留设备用房 | ARCHITECTURAL_ROOM | UNKNOWN | 设备类型不明确，无法归类 |
| 预留设备间 | ARCHITECTURAL_ROOM | UNKNOWN | 设备类型不明确，无法归类 |

## 人工名称清单外的提议（部分已被关键词覆盖）

| 房名 | 提议类别 | 理由 |
|---|---|---|
| 1#公变配电房 | SUBSTATION | 名称含公变配电房，属变电所 |
| 1-1楼梯 | ARCHITECTURAL_ROOM | 楼梯属于建筑交通空间 |
| 2-1楼梯 | ARCHITECTURAL_ROOM | 楼梯为建筑房间 |
| 2-2楼梯 | ARCHITECTURAL_ROOM | 楼梯为建筑房间 |
| 3-1楼梯 | ARCHITECTURAL_ROOM | 楼梯为建筑房间 |
| 3-2楼梯 | ARCHITECTURAL_ROOM | 楼梯为建筑房间 |
| 3-2楼梯上空 | ARCHITECTURAL_ROOM | 楼梯上空属于建筑空间 |
| 5-1楼梯 | ARCHITECTURAL_ROOM | 楼梯属于建筑交通空间 |
| 5-2楼梯 | ARCHITECTURAL_ROOM | 楼梯属于建筑交通空间 |
| 6-1楼梯 | ARCHITECTURAL_ROOM | 楼梯属于建筑交通空间 |
| 6-2楼梯 | ARCHITECTURAL_ROOM | 楼梯属于建筑交通空间 |
| 7-1楼梯 | ARCHITECTURAL_ROOM | 楼梯属于建筑交通空间 |
| 8-1楼梯 | ARCHITECTURAL_ROOM | 楼梯属于建筑交通空间 |
| 9-1楼梯 | ARCHITECTURAL_ROOM | 楼梯属于建筑交通空间 |
| B-1坡道 | ARCHITECTURAL_ROOM | 坡道为建筑房间 |
| B-2坡道 | ARCHITECTURAL_ROOM | 坡道为建筑房间 |
| P-1楼梯 | ARCHITECTURAL_ROOM | 楼梯为建筑房间 |
| P-2楼梯 | ARCHITECTURAL_ROOM | 楼梯属于建筑交通空间 |
| P-3楼梯 | ARCHITECTURAL_ROOM | 楼梯属于建筑交通空间 |
| 井 | UNKNOWN | 井用途无法判断 |
| 人防楼梯 | ARCHITECTURAL_ROOM | 人防楼梯为建筑房间 |
| 储藏间 | ARCHITECTURAL_ROOM | 储藏间属于建筑使用房间 |
| 公变配电房上空 | SUBSTATION | 公变配电房上空，属变电所 |
| 冷媒井 | HVAC_SHAFT | 冷媒井属暖通井道 |
| 卫生服务站 | ARCHITECTURAL_ROOM | 卫生服务站为建筑房间 |
| 变配电室 | SUBSTATION | 变配电室，属变电所 |
| 图书室(人数不超30人) | ARCHITECTURAL_ROOM | 图书室为建筑房间 |
| 地下室 | ARCHITECTURAL_ROOM | 地下室为建筑房间 |
| 地下室上空 | ARCHITECTURAL_ROOM | 地下室上空为建筑房间 |
| 女卫 | ARCHITECTURAL_ROOM | 女卫为建筑房间 |
| 实施充电桩配电房 | DISTRIBUTION_ROOM | 充电桩配电房属配电室 |
| 密闭通道 | ARCHITECTURAL_ROOM | 密闭通道为建筑房间 |
| 封闭楼梯 | ARCHITECTURAL_ROOM | 封闭楼梯为建筑房间 |
| 弱电机房 | WEAK_CURRENT_ROOM | 名称明确为弱电机房 |
| 快递综合服务站(人数不超30人) | ARCHITECTURAL_ROOM | 属建筑功能房间 |
| 扩散室 | UNKNOWN | 用途不明确 |
| 排烟井 | HVAC_SHAFT | 排烟井属暖通井道 |
| 排烟机房 | HVAC_ROOM | 排烟机房属暖通房间 |
| 无障碍卫生间 | ARCHITECTURAL_ROOM | 属建筑功能房间 |
| 机动车坡道 | EXCLUDED | 坡道非房间 |
| 水井 | PLUMBING_ROOM | 水井属给排水井道 |
| 水泵房 | PLUMBING_ROOM | 水泵房，属给排水房间 |
| 消防水池 | PLUMBING_ROOM | 消防水池属给排水设施 |
| 消防水池一 | PLUMBING_ROOM | 消防水池属于给排水专业设施。 |
| 消防水池上空 | UNKNOWN | 上空区域用途不明确 |
| 消防水池二 | PLUMBING_ROOM | 消防水池属于给排水专业设施。 |
| 消防泵房上空 | UNKNOWN | 上空区域用途不明确 |
| 物业管理及服务用房(人数不超30人) | ARCHITECTURAL_ROOM | 属建筑功能房间 |
| 电井 | ELECTRICAL_SHAFT | 电井属电气竖井 |
| 电气间兼充电桩电表间 | DISTRIBUTION_ROOM | 电气间属配电室 |
| 男卫 | ARCHITECTURAL_ROOM | 卫生间属建筑功能房间 |
| 简易洗消区 | UNKNOWN | 用途不明确 |
| 补风井 | HVAC_SHAFT | 补风井属暖通井道 |
| 表间上空 | UNKNOWN | 上空区域用途不明确 |
| 进线间 | DISTRIBUTION_ROOM | 进线间属配电室 |
| 进风井 | HVAC_SHAFT | 进风井属暖通井道 |
| 通道 | ARCHITECTURAL_ROOM | 通用通行空间，属建筑房间 |
| 采光天井 | ARCHITECTURAL_ROOM | 采光用天井，属建筑空间 |
| 防毒通道 | ARCHITECTURAL_ROOM | 人防通行空间，属建筑房间 |
| 防火单元自然补风井 | HVAC_SHAFT | 补风井属暖通井道 |
| 除尘滤毒室 | HVAC_ROOM | 通风滤毒功能房间，属暖通房间 |
| 集气室 | UNKNOWN | 用途不明确，无法归类 |
| 预留水泵房 | PLUMBING_ROOM | 水泵房属给排水房间 |

当前提议共63项，其中2项已获工程师确认、61项待批准。模型原输出与人工采用类别分别保留；35/49对照不因事后审批重算。

新名称保存在rules/naming_proposals.yaml，未批准项不会参与用途分类。未知名称继续按现有词表处理。

## 重放

`python -m cst naming samples/A samples/B samples/A-change --replay`

补充清单仅按源图哈希关联实验输入，不限制扫描新图。缺失名称增量真实调用，已缓存名称不重跑。重放核对提示词、类别定义、模型及缓存身份，无网络请求。原始49种人工分类未覆盖的名称，不计算一致率。

## 模型提议覆盖（与审批分开）

实际模型返回去重名称112项；本次实验输入112项。人工精确清单外63项，其中原关键词规则已能覆盖17项，未覆盖46项；模型为未覆盖名称提出非UNKNOWN类别42项。这些是提议覆盖数量，不是专业准确率。已批准2项，其余采纳率待工程师逐项审核。

核对表：[房名核对CSV](naming-review.csv)。原词表外不等于现有关键词完全无法分类，不能写成“纯词表一个也分不出来”。
