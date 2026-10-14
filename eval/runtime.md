# 运行内存与耗时

|平台|命令范围|耗时|峰值进程RSS|结果|
|---|---|---:|---:|---|
|Windows|full|340.359秒|3873.98MiB|退出码0|
|Windows|changes-only|182.717秒|3867.25MiB|退出码0|
|Ubuntu / Python 3.11|full|384.27秒|4102.84MiB|退出码0|
|Ubuntu / Python 3.11|changes-only|182.84秒|4100.81MiB|退出码0|

测量输入为公开A/B/A-change，测量代码提交c853a35。Windows/Python 3.13.4以50ms间隔采样单进程RSS；Ubuntu/Python 3.11使用GNU time -v记录峰值。安装、CAD与浏览器不计入。两平台各单次运行，不能据此推断所有图纸规模。

完整演示建议64位系统、至少8GB整机内存，运行前可用内存至少5GB；CAD和浏览器并行建议16GB。这是按实测给出的配置建议，尚未寻找精确最低边界。512MB外部沙盒的demo/check/全量测试曾中断。

**缩减范围节省时间，未显著降低峰值内存。** `python -m cst.demo --changes-only`跳过A/B独立输出和全组AI重放，但仍重算A到A-change的几何、规则和证据。512MB环境应使用预生成HTML或Pages，不建议执行重算。

[Ubuntu实测及验收](https://github.com/paigu3571/GeomVerity/actions/runs/38499689728)。机器配置、后台负载和软件版本会影响耗时。

峰值不代表常驻内存。正式版0.3.0仅将决策版本元数据从dev0更新为0.3.0；上述运行时数字保留实际测量提交，不伪装成新一轮测量。
