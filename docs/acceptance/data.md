# 数据读取与引用校验

```powershell
python -m cst summary samples/A
python -m cst verify samples/A
python -m cst summary samples/B
python -m cst verify samples/B
```

A/B应分别包含73/48个Space；每个L3对象的L2/L1引用及Handle有明确核验结果。断链输出具体对象。未附原DWG时显示源字节未核验，不伪称通过，也不因未提供原图退出失败。

公开样例为配套.json.gz，读取器透明解压。manifest核对公开压缩文件的实际摘要；原扫描哈希保留来源意义。样例不附原DWG，布局几何仍可见；使用者不能据此假定任意输入都已匿名化。

缺文件、字段或类型不匹配时检查[契约](../api/schema.md)，不手工修改哈希配平。样例和人工记录被冻结用于回归，不是普通新图准入名单。
