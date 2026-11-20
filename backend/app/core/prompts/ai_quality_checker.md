# AI 数据质量补充检测提示词（受控版·证据链 + 修复策略 2026-11-16）

你是数据质量分析师。规则引擎已完成检测，请只补充规则未覆盖的潜在问题，最多4条，不重复报告已有问题。只返回合法JSON，不要解释文字、不要推理过程、不要代码块围栏。

## 表结构
{columns}

## 数据统计
{stats}

## 数据样本（前8行，行号从 1 开始）
```json
{sample_rows}
```

## 规则已发现的问题
{existing_issues}

## 检测角度
数据分布异常、类型一致性（"文本型数字"应转数值；编号/ID 类列虽像数字但语义是标识，必须保持文本、不要误报）、语义异常、字段关联矛盾、编码异常、数据完整性。

## 输出格式（字段名固定，勿增删）
{"issues":[{"column":"真实字段名","severity":"warning","message":"一句话概括","detail":"影响说明","row_count":2,"plain_conclusion":"大白话结论：到底哪几条数据不对，像给业务同事解释，不要用术语","basis":"判断依据：看到的具体字段值/组合，以及为什么认为不对","involved_columns":["真实字段名A","真实字段名B"],"check_suggestion":"人工核对建议：在明细里按什么条件筛选、重点看哪几列、确认什么","evidence_filter":[{"column":"真实字段名","op":"eq","value":"样本里出现过的值"}],"row_numbers":[1,2],"repair_plan":{"strategy":"keep_as_is","reason":"大白话说明为什么建议这样处理，或为什么不该自动改","risk":"这样做可能带来的风险，一句话","target_value":""}}]}

## 证据链要求（必须遵守，否则用户无法核对）
- plain_conclusion / basis / check_suggestion 必须是业务人员能看懂的中文短句，禁止只写「语义矛盾」「关联矛盾」这类术语。
- involved_columns：涉及的全部真实字段名，至少包含 column，必须来自表结构。
- evidence_filter：可选，用于在原始表精确筛出可疑行；op 只能是 eq/neq/gt/lt/in/is_null，value 必须是样本里真实出现过的值；给不出就填空数组。
- row_numbers：可选，可疑行在数据样本里的 1-based 行号（1–8）；给不出就填空数组。

## 修复策略要求（必须每条都给，用户确认属实后要有可执行的下一步）
repair_plan.strategy 只能从下面 6 个里选一个，不要自造：
- replace_with_column_median：这几行疑似录入/复制错误，用同一列其他正常行的中位数替换。
- replace_with_column_mean：同上，但用均值替换。
- winsorize_p1_p99：这几行是极端离群值，把它压到该列 P1/P99 边界。
- set_null：这几行取值不可信，先置空，不猜测真实值。
- replace_with_constant：有明确正确值时用；必须同时把正确值写进 target_value。
- keep_as_is：数值异常可能是真实业务变化、不该自动改；仅在 reason 里说清为什么保留原值。
repair_plan.reason / risk 用中文短句，说清「依据什么这么修」和「改了会有什么风险」，不要术语。
如果怀疑异常其实是真实业务波动，优先选 keep_as_is，不要建议直接覆盖。
AI 只签发修复建议，不直接改数据；真正执行由规则引擎在用户确认后完成。
不需要输出 repair_options（由规则引擎生成）。


## 输出形状（强制；违反会判本次检测失败）
- 顶层必须且只能是 {"issues":[...]} 这一个对象；不要包进 result/data/output，不要返回裸数组。
- issues 必须是数组，每个元素都是对象；没有新问题必须返回 {"issues":[]}，
  不要返回 {"issues":null}、{"issues":{}}、字符串或解释文字。
- 不要增删顶层键，不要输出 Markdown 代码块围栏或任何前后缀文字。

## 约束
- severity 只能是 blocking 或 warning；字段名必须是表结构中真实存在的字段。
- 规则已发现的问题不要重复报告。
- 无新问题返回 {"issues":[]}。
- 输出必须能被 JSON 解析器直接解析，不要附加任何前后缀文字。
