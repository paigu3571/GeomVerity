# 评测与验证证据

- sample_freeze.json：公开输入和R1人工确认的冻结字节摘要，用于回归，不是扫描准入白名单。
- llm_naming.md / llm_naming_results.json / room_name_corpus.json：房名分类实测、模型原输出和带源引用的候选清单。
- change_test.md / change_test_results.json：8项人工修改的事后对照；原记录与更正记录分别保留。
- change_ai_results.json：固定输入的六问统计与拦截结果。
- A/B_gold.csv、A/B_missed.csv、focused_review.csv等：标注模板或人工记录。空白不当作正确答案，完整空间准确率未评测。
- SYNTHETIC_*：人工构造的规则与引用控制，仅用于验证程序边界。
- coedge_candidates.*：早期几何共边候选观察，用于与隔墙判定区分。

评测数字限定到具体输入、标注范围和规则版本；候选数量不等于正确数量。运行与参数见[验收](../docs/acceptance/ai.md)。
