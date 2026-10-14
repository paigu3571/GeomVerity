# L1/L2/L3数据结构说明

对应生产0.2.11 JSON与迁移C# v1契约；插件0.3.0-dev仍使用同一结构。字段严格读取，未知/缺失/类型错误报错，不静默补造字段。空字符串和空列表沿用原含义，不替代缺数据。

语义对象类型：storey/space/wall/column/opening/door/window/shaft/stair/ramp/zone/roof_line。用途代码实际词典35项，字段允许其他字符串，UNKNOWN表示未知。所有ID只保证本次快照对应，不是永久身份；SHA证明对应关系，不证明识别正确。原版本IsExact采样标记仍有局限。

## Bounds

| 字段 | 类型/取值 | 中文含义与边界 |
|---|---|---|
| min_x | `<class 'float'>` | WCS包围盒边界值，单位毫米 |
| min_y | `<class 'float'>` | WCS包围盒边界值，单位毫米 |
| min_z | `<class 'float'>` | WCS包围盒边界值，单位毫米 |
| max_x | `<class 'float'>` | WCS包围盒边界值，单位毫米 |
| max_y | `<class 'float'>` | WCS包围盒边界值，单位毫米 |
| max_z | `<class 'float'>` | WCS包围盒边界值，单位毫米 |
| is_valid | `<class 'bool'>` | 包围盒可用标志 |

## Diagnostic

| 字段 | 类型/取值 | 中文含义与边界 |
|---|---|---|
| severity | `<class 'str'>` | 发现项级别 |
| reason_code | `<class 'str'>` | 原因码 |
| message | `<class 'str'>` | 诊断说明 |
| stable_path | `<class 'str'>` | 源实例路径；派生对象可能带derived前缀 |

## Drawing

| 字段 | 类型/取值 | 中文含义与边界 |
|---|---|---|
| drawing_id | `<class 'str'>` | 本次图纸空间ID |
| file_name | `<class 'str'>` | 源文件名，公开样例会替换 |
| sha256 | `<class 'str'>` | 对应源文件/配置的哈希记录 |
| file_length | `<class 'int'>` | 源文件字节数 |
| source_last_write_utc | `<class 'str'>` | 源文件保存时间UTC |
| coordinate_system | `<class 'str'>` | 坐标系，目前WCS |
| geometry_units | `<class 'str'>` | 单位，目前mm |

## Evidence

| 字段 | 类型/取值 | 中文含义与边界 |
|---|---|---|
| code | `<class 'str'>` | 证据代码 |
| kind | `<class 'str'>` | 图元/几何类别，不等同工程用途 |
| value | `<class 'str'>` | 证据负载；按kind/code解释，不盲目当ID |
| source_handle | `<class 'str'>` | 证据涉及的源对象Handle，可为空 |
| weight | `<class 'float'>` | 证据权重 |

## Finding

| 字段 | 类型/取值 | 中文含义与边界 |
|---|---|---|
| finding_id | `<class 'str'>` | 生成器发现项ID |
| severity | `<class 'str'>` | 发现项级别 |
| reason_code | `<class 'str'>` | 原因码 |
| message | `<class 'str'>` | 诊断说明 |
| semantic_id | `<class 'str'>` | L3本次对象ID，不是跨版本永久身份 |
| source_handle | `<class 'str'>` | 证据涉及的源对象Handle，可为空 |

## Geometry

| 字段 | 类型/取值 | 中文含义与边界 |
|---|---|---|
| kind | `<class 'str'>` | 图元/几何类别，不等同工程用途 |
| is_closed | `<class 'bool'>` | 声明路径闭合；不证明墙网没有漏检 |
| is_exact | `<class 'bool'>` | 原生成器精确性标志；采样问题未修 |
| extraction_method | `<class 'str'>` | 几何提取方法 |
| paths | `list[list[cst.model.Point]]` | WCS毫米坐标路径，可有多段/点/空数组 |
| bounds | `<class 'cst.model.Bounds'>` | 包围盒，不等同真实轮廓 |

## GeometryFact

| 字段 | 类型/取值 | 中文含义与边界 |
|---|---|---|
| geometry_id | `<class 'str'>` | L2几何ID |
| compatibility_fact_id | `<class 'str'>` | 兼容事实ID，可为空 |
| source_primitive_ids | `list[str]` | 引用L1图元ID列表 |
| feature_kind | `<class 'str'>` | 几何特征类别 |
| adapter_role_hint | `<class 'str'>` | 提供器角色提示，可为空 |
| is_semantic_candidate | `<class 'bool'>` | 是否语义候选 |
| source | `<class 'cst.model.Source'>` | Handle/实例路径/坐标变换等来源 |
| geometry | `<class 'cst.model.Geometry'>` | 几何路径及包围盒；不是保证闭合的房间轮廓 |
| measurements | `<class 'cst.model.Measurements'>` | L2几何量，长度毫米/面积平方毫米 |
| raw_text | `<class 'str'>` | 原始文字 |
| extraction_confidence | `<class 'float'>` | 提供器置信值，不是正确概率 |
| raw_properties | `dict[str, str]` | 原始属性字符串字典 |
| evidence | `list[cst.model.Evidence]` | 分类证据列表，不是每个value都为对象ID |
| reason_codes | `list[str]` | 机器原因码列表；不自动理解为规范违规 |

## GeometryRelation

| 字段 | 类型/取值 | 中文含义与边界 |
|---|---|---|
| relation_id | `<class 'str'>` | 本次关系ID |
| type | `<class 'str'>` | 对象/关系类别，继承原合同枚举 |
| from_geometry_id | `<class 'str'>` | L2关系起点 |
| to_geometry_id | `<class 'str'>` | L2关系终点 |
| distance_millimeters | `<class 'float'>` | L2关系距离毫米 |
| confidence | `<class 'float'>` | 算法置信值，不保证正确 |
| reason_codes | `list[str]` | 机器原因码列表；不自动理解为规范违规 |

## Integrity

| 字段 | 类型/取值 | 中文含义与边界 |
|---|---|---|
| source_hash_before | `<class 'str'>` | 扫描前源哈希 |
| source_hash_after | `<class 'str'>` | 扫描后源哈希 |
| source_bytes_unchanged | `<class 'bool'>` | 生成器记录的扫描前后字节未变 |
| scan_input_mode | `<class 'str'>` | disk_side_database等读取模式 |
| input_database_read_only | `<class 'bool'>` | 数据库只读记录 |
| dbmod_before | `<class 'int'>` | 活动文档扫描前修改状态 |
| dbmod_after | `<class 'int'>` | 活动文档扫描后修改状态 |
| dbmod_clean_at_start | `<class 'bool'>` | 活动文档初始是否无修改 |
| dbmod_unchanged | `<class 'bool'>` | 活动文档状态是否稳定 |

## L1

| 字段 | 类型/取值 | 中文含义与边界 |
|---|---|---|
| schema_version | `typing.Literal['cad-primitives.v1']` | 结构版本，读取器仅支持所列v1，不自动猜测新结构 |
| producer | `<class 'str'>` | 生成器名称 |
| producer_version | `<class 'str'>` | 实际生成器版本，旧样例保持0.2.11 |
| producer_binary_sha256 | `<class 'str'>` | 生成DLL的SHA256记录，不证明当前机器安装相同DLL |
| generated_at_utc | `<class 'str'>` | 扫描时间UTC字符串 |
| status | `typing.Literal['accepted', 'review', 'failed']` | run为accepted/review/failed；对象/关系为accepted/review/rejected |
| reason_codes | `list[str]` | 机器原因码列表；不自动理解为规范违规 |
| drawing | `<class 'cst.model.Drawing'>` | 输入图纸元数据 |
| profile | `<class 'cst.model.Profile'>` | 所用配置元数据 |
| integrity | `<class 'cst.model.Integrity'>` | 扫描过程记录，不代替现在重新核验字节 |
| fact_provider_id | `<class 'str'>` | 宿主事实提供器标识 |
| deterministic_content_hash | `<class 'str'>` | 原生成器算法内容摘要；脱敏后不冒称原摘要有效 |
| metrics | `dict[str, int]` | 生成器整数统计，summary另按实际对象计数 |
| provider_diagnostics | `list[cst.model.Diagnostic]` | 提供器诊断 |
| extraction_configuration_hash | `<class 'str'>` | L1提取配置摘要 |
| deterministic_hash_algorithm | `<class 'str'>` | 内容摘要算法名称，不自动由Python重算原算法 |
| primitives | `list[cst.model.Primitive]` | L1图元列表 |
| proxy_ledger | `list[cst.model.Proxy]` | 代理对象审计账本 |

## L2

| 字段 | 类型/取值 | 中文含义与边界 |
|---|---|---|
| schema_version | `typing.Literal['building-geometry.v1']` | 结构版本，读取器仅支持所列v1，不自动猜测新结构 |
| producer | `<class 'str'>` | 生成器名称 |
| producer_version | `<class 'str'>` | 实际生成器版本，旧样例保持0.2.11 |
| producer_binary_sha256 | `<class 'str'>` | 生成DLL的SHA256记录，不证明当前机器安装相同DLL |
| generated_at_utc | `<class 'str'>` | 扫描时间UTC字符串 |
| status | `typing.Literal['accepted', 'review', 'failed']` | run为accepted/review/failed；对象/关系为accepted/review/rejected |
| reason_codes | `list[str]` | 机器原因码列表；不自动理解为规范违规 |
| drawing | `<class 'cst.model.Drawing'>` | 输入图纸元数据 |
| profile | `<class 'cst.model.Profile'>` | 所用配置元数据 |
| integrity | `<class 'cst.model.Integrity'>` | 扫描过程记录，不代替现在重新核验字节 |
| fact_provider_id | `<class 'str'>` | 宿主事实提供器标识 |
| deterministic_content_hash | `<class 'str'>` | 原生成器算法内容摘要；脱敏后不冒称原摘要有效 |
| metrics | `dict[str, int]` | 生成器整数统计，summary另按实际对象计数 |
| provider_diagnostics | `list[cst.model.Diagnostic]` | 提供器诊断 |
| source_primitive_content_hash | `<class 'str'>` | L2记录的上游L1内容摘要 |
| geometry_configuration_hash | `<class 'str'>` | L2几何配置摘要 |
| deterministic_hash_algorithm | `<class 'str'>` | 内容摘要算法名称，不自动由Python重算原算法 |
| facts | `list[cst.model.GeometryFact]` | L2几何事实列表 |
| relations | `list[cst.model.GeometryRelation]` | 层内关系列表 |

## L3

| 字段 | 类型/取值 | 中文含义与边界 |
|---|---|---|
| schema_version | `typing.Literal['building-semantics.v1']` | 结构版本，读取器仅支持所列v1，不自动猜测新结构 |
| producer | `<class 'str'>` | 生成器名称 |
| producer_version | `<class 'str'>` | 实际生成器版本，旧样例保持0.2.11 |
| producer_binary_sha256 | `<class 'str'>` | 生成DLL的SHA256记录，不证明当前机器安装相同DLL |
| generated_at_utc | `<class 'str'>` | 扫描时间UTC字符串 |
| status | `typing.Literal['accepted', 'review', 'failed']` | run为accepted/review/failed；对象/关系为accepted/review/rejected |
| reason_codes | `list[str]` | 机器原因码列表；不自动理解为规范违规 |
| drawing | `<class 'cst.model.Drawing'>` | 输入图纸元数据 |
| profile | `<class 'cst.model.Profile'>` | 所用配置元数据 |
| integrity | `<class 'cst.model.Integrity'>` | 扫描过程记录，不代替现在重新核验字节 |
| fact_provider_id | `<class 'str'>` | 宿主事实提供器标识 |
| deterministic_content_hash | `<class 'str'>` | 原生成器算法内容摘要；脱敏后不冒称原摘要有效 |
| metrics | `dict[str, int]` | 生成器整数统计，summary另按实际对象计数 |
| provider_diagnostics | `list[cst.model.Diagnostic]` | 提供器诊断 |
| objects | `list[cst.model.SemanticObject]` | L3对象列表 |
| relations | `list[cst.model.Relation]` | 层内关系列表 |
| findings | `list[cst.model.Finding]` | 生成器发现项，不是L4规则结果 |
| proxy_ledger | `list[cst.model.Proxy]` | 代理对象审计账本 |

## Measurements

| 字段 | 类型/取值 | 中文含义与边界 |
|---|---|---|
| length_millimeters | `<class 'float'>` | 路径总长，不能直接当房间长边 |
| area_square_millimeters | `<class 'float'>` | 面积平方毫米，仅area_is_available为true才可用 |
| area_is_available | `<class 'bool'>` | 是否可以使用该面积 |
| area_method | `<class 'str'>` | 面积算法标签 |
| width_millimeters | `<class 'float'>` | WCS包围盒宽，不是旋转房间净长 |
| height_millimeters | `<class 'float'>` | WCS包围盒高，不是建筑层高 |
| representative_point_wcs_millimeters | `<class 'cst.model.Point'>` | 几何代表点 |

## Point

| 字段 | 类型/取值 | 中文含义与边界 |
|---|---|---|
| x | `<class 'float'>` | WCS X毫米 |
| y | `<class 'float'>` | WCS Y毫米 |
| z | `<class 'float'>` | WCS Z毫米 |

## Primitive

| 字段 | 类型/取值 | 中文含义与边界 |
|---|---|---|
| primitive_id | `<class 'str'>` | L1本次图元ID |
| source_fact_id | `<class 'str'>` | 兼容源事实ID，可为空 |
| kind | `<class 'str'>` | 图元/几何类别，不等同工程用途 |
| adapter_role_hint | `<class 'str'>` | 提供器角色提示，可为空 |
| is_semantic_candidate | `<class 'bool'>` | 是否语义候选 |
| source | `<class 'cst.model.Source'>` | Handle/实例路径/坐标变换等来源 |
| raw_text | `<class 'str'>` | 原始文字 |
| raw_geometry | `<class 'cst.model.Geometry'>` | L1原始几何 |
| extraction_confidence | `<class 'float'>` | 提供器置信值，不是正确概率 |
| raw_properties | `dict[str, str]` | 原始属性字符串字典 |
| evidence | `list[cst.model.Evidence]` | 分类证据列表，不是每个value都为对象ID |
| reason_codes | `list[str]` | 机器原因码列表；不自动理解为规范违规 |

## Profile

| 字段 | 类型/取值 | 中文含义与边界 |
|---|---|---|
| project_id | `<class 'str'>` | 配置/运行项目空间标识 |
| profile_version | `<class 'str'>` | 配置版本 |
| sha256 | `<class 'str'>` | 对应源文件/配置的哈希记录 |

## Proxy

| 字段 | 类型/取值 | 中文含义与边界 |
|---|---|---|
| stable_path | `<class 'str'>` | 源实例路径；派生对象可能带derived前缀 |
| handle | `<class 'str'>` | 源DWG Handle；不同实例可共用Handle，须结合stable_path |
| original_dxf_name | `<class 'str'>` | 账本中的原始DXF类型 |
| original_class_name | `<class 'str'>` | 账本中的原始类名 |
| application_description | `<class 'str'>` | 代理对象应用描述 |
| effective_layer | `<class 'str'>` | 继承后的图层 |
| disposition | `<class 'str'>` | 账本处理策略 |
| reason_code | `<class 'str'>` | 原因码 |

## Relation

| 字段 | 类型/取值 | 中文含义与边界 |
|---|---|---|
| relation_id | `<class 'str'>` | 本次关系ID |
| type | `<class 'str'>` | 对象/关系类别，继承原合同枚举 |
| from_semantic_id | `<class 'str'>` | L3关系起点 |
| to_semantic_id | `<class 'str'>` | L3关系终点 |
| status | `typing.Literal['accepted', 'review', 'rejected']` | run为accepted/review/failed；对象/关系为accepted/review/rejected |
| confidence | `<class 'float'>` | 算法置信值，不保证正确 |
| evidence | `list[cst.model.Evidence]` | 分类证据列表，不是每个value都为对象ID |
| reason_codes | `list[str]` | 机器原因码列表；不自动理解为规范违规 |

## SemanticObject

| 字段 | 类型/取值 | 中文含义与边界 |
|---|---|---|
| semantic_id | `<class 'str'>` | L3本次对象ID，不是跨版本永久身份 |
| type | `typing.Literal['storey', 'space', 'wall', 'column', 'opening', 'door', 'window', 'shaft', 'stair', 'ramp', 'zone', 'roof_line']` | 对象/关系类别，继承原合同枚举 |
| classification | `<class 'str'>` | 分类细项，可为空 |
| raw_label | `<class 'str'>` | 原始用途标签；可能是面积/上空等非真实房间 |
| use_code | `<class 'str'>` | 词典代码字符串，可为空/UNKNOWN；非封闭枚举 |
| status | `typing.Literal['accepted', 'review', 'rejected']` | run为accepted/review/failed；对象/关系为accepted/review/rejected |
| confidence | `<class 'float'>` | 算法置信值，不保证正确 |
| source | `<class 'cst.model.Source'>` | Handle/实例路径/坐标变换等来源 |
| geometry | `<class 'cst.model.Geometry'>` | 几何路径及包围盒；不是保证闭合的房间轮廓 |
| evidence | `list[cst.model.Evidence]` | 分类证据列表，不是每个value都为对象ID |
| reason_codes | `list[str]` | 机器原因码列表；不自动理解为规范违规 |

## Snapshot

| 字段 | 类型/取值 | 中文含义与边界 |
|---|---|---|
| schema_version | `<class 'str'>` | 结构版本，读取器仅支持所列v1，不自动猜测新结构 |
| producer | `<class 'str'>` | 生成器名称 |
| producer_version | `<class 'str'>` | 实际生成器版本，旧样例保持0.2.11 |
| producer_binary_sha256 | `<class 'str'>` | 生成DLL的SHA256记录，不证明当前机器安装相同DLL |
| generated_at_utc | `<class 'str'>` | 扫描时间UTC字符串 |
| status | `typing.Literal['accepted', 'review', 'failed']` | run为accepted/review/failed；对象/关系为accepted/review/rejected |
| reason_codes | `list[str]` | 机器原因码列表；不自动理解为规范违规 |
| drawing | `<class 'cst.model.Drawing'>` | 输入图纸元数据 |
| profile | `<class 'cst.model.Profile'>` | 所用配置元数据 |
| integrity | `<class 'cst.model.Integrity'>` | 扫描过程记录，不代替现在重新核验字节 |
| fact_provider_id | `<class 'str'>` | 宿主事实提供器标识 |
| deterministic_content_hash | `<class 'str'>` | 原生成器算法内容摘要；脱敏后不冒称原摘要有效 |
| metrics | `dict[str, int]` | 生成器整数统计，summary另按实际对象计数 |
| provider_diagnostics | `list[cst.model.Diagnostic]` | 提供器诊断 |

## Source

| 字段 | 类型/取值 | 中文含义与边界 |
|---|---|---|
| drawing_hash | `<class 'str'>` | 本次源DWG哈希 |
| handle | `<class 'str'>` | 源DWG Handle；不同实例可共用Handle，须结合stable_path |
| stable_path | `<class 'str'>` | 源实例路径；派生对象可能带derived前缀 |
| raw_layer | `<class 'str'>` | 源图层 |
| effective_layer | `<class 'str'>` | 继承后的图层 |
| normalized_layer | `<class 'str'>` | 去前缀后的图层 |
| native_dxf_name | `<class 'str'>` | 原生DXF类型 |
| native_class_name | `<class 'str'>` | 宿主原生类名 |
| block_path | `list[str]` | 嵌套块实例路径列表 |
| xref_path | `list[str]` | 外参路径列表，可为空 |
| xref_hashes | `list[str]` | 外参哈希列表 |
| wcs_transform | `list[float]` | WCS变换矩阵数字列表 |


## 公开文件压缩与摘要
公开样例是.json.gz，读取器透明解压，不需要用户手工产生副本。manifest记录实际压缩字节SHA256；snapshot内的原content_hash只作扫描记录，清理后未复用为文件校验。无DWG字节未核验始终单列。

## L4人工复核记录
各数据目录可选l4_confirmations.yaml，仅存工程师对指定对象的净长是否超过7m、实际出入口数量，不填写猜测的具体长度。schema_version、origin=ENGINEER_REVIEW、reviewed_by/date、截图摘要明确来源；drawing_sha256和snapshot_sha256只绑定本次复核，不作为运行准入。记录不匹配时忽略旧复核并说明，仍解析任意新图。原L3状态不改，候选Handle映射继续待复核。
