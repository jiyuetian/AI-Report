"""根据新证据更正 O/P/Q 三份方案中的不准确论断。幂等。
新增证据：
1) brain_run_sse.py:86 _sanitize_charts 已存在「图表消毒层」（注释：AI 产出不可直信）
   → P 方案原写「只有 S3 有检查」不准确，需更正
   → 且该层字段检查 `dim not in valid` 同样是精确匹配（同一个归一化 bug，:117/:120）
   → 其基数规则只有下限(<2 丢弃, :133)，无上限
2) brain_run_sse.py:1051 已算 COUNT(DISTINCT)（column_cardinality）
   ai_quality_checker.py:123-127 已有现成画像文案模板
   → Q 方案所需材料链路上已算出，只是没注入 S3 → 成本比原估更低
"""
import io
import sys

P_PLAN = 'night3/plans/P_ai_result_check.md'
Q_PLAN = 'night3/plans/Q_ai_context_injection.md'


def sub(path, old, new, tag):
    s = io.open(path, encoding='utf-8').read()
    if new[:60] in s:
        print('[skip] %s' % tag)
        return
    if s.count(old) != 1:
        print('[fail] %s count=%d' % (tag, s.count(old)))
        sys.exit(1)
    s = s.replace(old, new)
    io.open(path, 'w', encoding='utf-8').write(s)
    print('[ok] %s' % tag)


# ---------- P：更正「只有 S3 有检查」 ----------
OLD_P1 = """| G1 | **只有 S3 有检查**，S1（主题）/ S2（目标）/ S4b（分析说明文本）**全程零校验** | S2 生成的目标里出现不存在的字段 → 一路带到 S3 prompt 里，诱导 S3 也出错（错误放大） |"""
NEW_P1 = """| G1 | **S1（主题）/ S2（目标）/ S4b（分析说明文本）全程零校验**；S3 与落库前有检查 | S2 生成的目标里出现不存在的字段 → 一路带到 S3 prompt 里，诱导 S3 也出错（错误放大） |"""

# 补一段：已存在的消毒层
OLD_P2 = """### 1.2 缺口"""
NEW_P2 = """### 1.1b 更正：落库前**已有**一个消毒层（初版方案漏记，已补）

`brain_run_sse.py:86` `_sanitize_charts()`，注释直接写着
「**图表消毒层（沿用 InsightDesk 的核心原则：AI 产出不可直信，落库前必须校验）**」。

现有 5 条规则：

| 规则 | 位置 | 内容 |
|---|---|---|
| 1 字段存在性 | `:117` `dim not in valid`、`:120` `meas not in valid` | 不存在则**丢弃** |
| 2/3 度量不可用 | `:139-144` | 度量==维度 / 度量非数值 → 纠正为 `aggregation=count` |
| 4 柱状饼图必须有维度 | `:128` | 无维度则丢弃 |
| 5 维度单值 | `:133` `card.get(dim, 99) < 2` | 唯一值 <2 → 丢弃 |

**这改变了方案的起点（初版写"只有 S3 有检查"是错的，已更正）**，并带来三点新发现：

1. **消毒层也犯同一个归一化 bug**：`:117/:120` 的 `not in valid` 与 S3 校验器一样是**精确匹配**。
   即：AI 答对的字段，会在 S3 校验被错杀一次，侥幸通过了还要在消毒层**再被错杀一次**。
   → P0 修复必须**两处一起改**（`s3_llm_enhancer.py:157` + `brain_run_sse.py:117/120`）。
2. **基数检查只有下限、没有上限**：`:133` 只拦 `<2`（无信息量），
   不拦 `>30`（2000 个取值做饼图）。上限缺失正是本方案 L2 要补的。
3. **丢弃/纠正的结果只 print 不落库**（`:158`），用户和评委都看不到
   —— 印证下方 G5，也说明「消毒」这件事本身是有价值的，只是**没被展示**。

### 1.2 缺口"""

sub(P_PLAN, OLD_P1, NEW_P1, 'P-G1 更正')
sub(P_PLAN, OLD_P2, NEW_P2, 'P-1.1b 新增')

# ---------- Q：补充「材料链路上已算出」 ----------
OLD_Q = """**数据来源现成**：`FieldAnalyzer` 已有类型分析，`schema_enricher` 已有 business_role/chart_hint，
质检阶段已有 `field_profiles`（含 `null_count`/`null_rate`，D2 归因实查已在使用）。
**只需要补 distinct 计数与取值采样**，不需要重新造画像体系。"""
NEW_Q = """**数据来源 —— 比初版估计的更现成（已核实）**：

| 材料 | 现成位置 | 状态 |
|---|---|---|
| 字段类型 | `FieldAnalyzer` / `schema_enricher` | ✅ 已在用 |
| 业务角色 / chart_hint | `schema_enricher.build_semantics` → `s3_llm_enhancer.py:278-291` | ✅ 已在用 |
| 空值率 | `ai_quality_checker.py:106`、`appendix_service.py:99`、`field_profiles` | ✅ 已算出（D2 归因实查在用） |
| **distinct 计数** | `brain_run_sse.py:1051` `SELECT COUNT(DISTINCT "{_d}")`，入参名 `column_cardinality`（`:90`） | ✅ **已算出** |
| **取值样例** | `ai_quality_checker.py:108` `sample_values[:5]` | ✅ **已算出** |
| **现成画像文案模板** | `ai_quality_checker.py:123-127`：<br>`"非空X/Y行, 空值率Z, 唯一值N个, 样例: [...]"` | ✅ **可直接复用** |

**关键结论：Q 需要的材料，链路上几乎全算出来了，只是没喂给 S3。**

更值得注意的是 `brain_run_sse.py:1051` 的 DISTINCT：**它是生成之后**算的，
且只算 `final_charts` 的维度字段（`_d = x_field or category_field`），用途是**事后消毒**
（见方案 P 的 1.1b）。

→ 本方案的核心动作其实是**把这个已经存在的能力前移**：
从「生成后算基数、不合格就丢」变成「生成前把基数告诉 LLM、让它别选错」。
**事前预防比事后丢弃更划算** —— 丢弃的图不会变成 AI 参与率，预防选对则会。

因此 P0 的工作量**低于初版估算的 3 h**：不需要新建画像体系，
主要是把 `ai_quality_checker` 已有的画像计算 + 文案模板，接到 S3 的 `fields_desc` 上。"""

sub(Q_PLAN, OLD_Q, NEW_Q, 'Q-数据来源补充')

print('done')
