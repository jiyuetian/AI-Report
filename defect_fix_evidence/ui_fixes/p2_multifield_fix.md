# 问题2 修复记录：多字段截断 + LLM 路径字段匹配（P0）

## 根因回顾
用户消息「我想要顶部的汇总看板加上每个：业务流程合规率，抵押登记合规率，档案管理合规率，
制度执行到位率，内部审计问题整改率的平均值汇总」此前：
1. **截断**：`split_clauses` 按逗号切分，5 字段变 5 子句，仅首段带「加上」产出动作，
   其余 4 个裸字段名被丢进 `unparsed` → 5 字段变 1 动作。
2. **匹配失败**：即便合并，原 ADD_CHART 规则要求「图型词(饼图/柱图)或指标词(金额/数量)」，
   该消息两者皆无 → 掉进 `_llm_classify`，AI 限流时返回 `unknown/0`，执行器报「匹配不到字段」。

## 修复（四处，严格约定范围）
### Layer1 — action_planner.py `split_clauses` 防截断
- 新增 `_ACTION_VERB_RE`（多字动作动词集合，**不含**裸单字「改/加/换」以免误命中「整改率」等字段名）。
- 切分后做回并：把「无动作动词的续接子句」拼回上一带动词子句（保留分隔逗号）。
- 「删掉A图，新增B图」两段均含动作动词 → 各自成句，复合指令不受影响（回归安全）。

### Layer2 — intent_classifier.py
- B1：ADD_CHART 规则新增「加上/新增 +（多字段列举，允许逗号）+ 平均值/均值/汇总」模式
  （用 `.{0,80}?` 跨逗号匹配字段列举），使该消息在**无 LLM**时也识别为 add_chart。
- LLM 路径字段规范化（`_llm_classify`）：拿到 LLM 的 `analysis` 后调用新增 `_canonicalize_analysis`，
  用 `_match_field` 把 `dimension_field`/`metric_field`/`charts[]` 候选名规范化成真实字段名
  （解决「每个：业务流程合规率」带前缀表述到执行器仍匹配不到的根因）。

### Change C — intent_classifier.py `_rule_extract_add_charts` 枚举真实字段
- 子句优先按「命中的真实数值字段」当作指标（合规率类字段即数值指标），避免被「业务」维度词
  或「均值」关键词误导；仅当无真实数值字段时才走原维度/指标关键词匹配（兼容「地区分布柱状图」表述）。
- 子句末尾 `if not charts` 兜底：消息含聚合/统称词且列举真实字段名时，按「每个字段的均值」生成图。

### Layer3 — action_executor.py `_execute_add_chart` 容错
- charts_spec 内单图 `metric_field` 缺失但有 `metric_name`/`title` 时，用内联 `_match_field` 回退解析真实字段；
  仍缺失才回退画像首个数值字段（不再直接报「匹配不到字段」）。

## 验证
- `tests/test_p2_multifield.py`（LLM 提取 monkeypatch 为 None，离线快跑）3 passed：
  1. `test_layer1_no_truncation`：5 字段消息合并为 1 子句，5 字段全保留。
  2. `test_multifield_extraction`：识别为 add_chart，提取 5 张图，metric_field 均为 5 个真实字段。
  3. `test_compound_delete_add_regression`：「删掉A图，新增B图」拆成 2 动作（delete_chart + add_chart），复合指令未误合并。
- 后端 `py_compile` 通过。

## 落盘
- 本记录 + `p2_test.out`~`p2_test4.out`（迭代过程，最终 `p2_test4.out` 3 passed）。
- 改动文件：action_planner.py / intent_classifier.py / action_executor.py（均在本问题范围）。
