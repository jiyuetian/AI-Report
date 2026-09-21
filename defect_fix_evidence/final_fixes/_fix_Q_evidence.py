"""修正 Q 方案「数据来源」段：原文是引用块（带 '> ' 前缀），且原结论「只需要补 distinct」已不成立。"""
import io
import sys

P = 'night3/plans/Q_ai_context_injection.md'
s = io.open(P, encoding='utf-8').read()

OLD = """> 数据来源现成：`FieldAnalyzer` 已有类型分析，`schema_enricher` 已有 business_role/chart_hint，
> 质检阶段已有 `field_profiles`（含 `null_count`/`null_rate`，D2 归因实查已在使用）。
> **只需要补 distinct 计数与取值采样**，不需要重新造画像体系。"""

NEW = """#### 数据来源 —— 比初版估计的更现成（已逐项核实）

| 材料 | 现成位置 | 状态 |
|---|---|---|
| 字段类型 | `FieldAnalyzer` / `schema_enricher` | ✅ 已在用 |
| 业务角色 / chart_hint | `schema_enricher.build_semantics` → `s3_llm_enhancer.py:278-291` | ✅ 已在用 |
| 空值率 | `ai_quality_checker.py:106`、`appendix_service.py:99`、`field_profiles` | ✅ 已算出（D2 归因实查在用） |
| **distinct 计数** | `brain_run_sse.py:1051` `SELECT COUNT(DISTINCT "{_d}")`，入参 `column_cardinality`（`:90`） | ✅ **已算出** |
| **取值样例** | `ai_quality_checker.py:108` `sample_values[:5]` | ✅ **已算出** |
| **现成画像文案模板** | `ai_quality_checker.py:123-127`：<br>`"非空X/Y行, 空值率Z, 唯一值N个, 样例: [...]"` | ✅ **可直接复用** |

**关键结论：Q 需要的材料，链路上几乎全算出来了，只是没喂给 S3。**
初版写的「只需要补 distinct 计数与取值采样」是**低估了现状** —— 它们已经有了。

更值得注意的是 `brain_run_sse.py:1051` 的 DISTINCT：**它是生成之后**才算的，
且只算 `final_charts` 的维度字段（`_d = x_field or category_field`），用途是**事后消毒**
（详见方案 P 的 1.1b 消毒层）。

→ 本方案的核心动作其实是**把这个已经存在的能力前移**：
从「生成后算基数、不合格就丢」变成「生成前把基数告诉 LLM、让它别选错」。
**事前预防比事后丢弃更划算** —— 被丢弃的图不会计入 AI 参与率，预防选对则会。

因此 P0 工作量**低于初版估算的 3 h**：不需要新建画像体系，
主要是把 `ai_quality_checker` 已有的画像计算与文案模板接到 S3 的 `fields_desc` 上。"""

if NEW[:60] in s:
    print('[skip] already applied')
    sys.exit(0)
if s.count(OLD) != 1:
    print('[fail] count=%d' % s.count(OLD))
    sys.exit(1)
s = s.replace(OLD, NEW)
io.open(P, 'w', encoding='utf-8').write(s)
print('[ok] applied, chars =', len(s))
