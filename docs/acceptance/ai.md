# 产品AI与离线重放

```powershell
python -m cst ask --replay
python -m cst naming samples/A samples/B samples/A-change --replay
python -m cst notify samples/A samples/A-change --changes dist/changes/example/diff.json --replay
```

ask默认重放SYNTHETIC引用控制；真实产品问答、草案、通知和术语实验由公开缓存复现，完整流程见[离线演示](demo.md)。

术语实验应有112种候选、49种人工一级类别对照、一致35/49，63项新名称提议中43项采纳、20项修改，56项启用、7项暂缓启用。保留模型原提议和人工校正；回放不重算事后批准为模型准确结果，也不发网络请求。

通知应valid:true、network_used:false、sent:false，包含房名、Handle和版本时间；没有逐对象编辑时刻。最新稳定引用缓存一次重答后通过。通知为待签字文件，未自动发送。

六问评测使用固定输入：首答3/6，重答后5项通过、1项拦截。不同数据或提示词不能借旧缓存冒称同一次结果。API key只从环境变量DEEPSEEK_API_KEY读取，不写文件、日志或缓存。
