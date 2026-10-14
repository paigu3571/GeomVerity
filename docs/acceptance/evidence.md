# 决策证据包

```powershell
python -m cst bundle samples/A-change --changes dist/changes/example/diff.json --output dist/bundle/example
python -m cst verify dist/bundle/example
python -m cst rule-impact --code "GB 55024-2022" --bundle dist/bundle/example --synthetic
```

完整示例输出194条决策，含规则、生成灯具及计算适用性记录。每条可查看输入指纹、规则版本/哈希、来源引用和确认范围。任一依赖变化使原确认失效；没有原确认的记录不继承签字。

证据包校验应failure_count:0。没有原DWG时源字节核验单列未核验。修改任一输出文件后，清单校验应发现差异。规范影响命令是SYNTHETIC假设修订演示，不表示规范实际变更。

输入/变更文件须为同两版。校验失败时重新导出并保留原包排查，不手改失败结果为通过。
