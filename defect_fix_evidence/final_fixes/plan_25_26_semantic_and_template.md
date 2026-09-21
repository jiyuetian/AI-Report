# 方案 2.5 + 2.6 · AI 自主推理语义 + 分析模板库（仅方案，未落地）

> 本方案是 **第 8 层 O/P/Q 的落地层**：
> - **2.5 = 落地方案 Q（上下文注入）** 的 L1 业务知识 + L2 数据画像 + L4 反馈记忆；并把"AI 推理结果"持久化（field_semantics 表）。
> - **2.6 = 落地第 8 层 C2（分析模板沉淀）**，并与现有 S2 目标生成整合。
> 所有论断均基于已读代码，附 `file:line`。不含"应该是"类推断。

---

## 〇、边界总览（先定清楚，免得和 O/P/Q 打架）

| 本方案做的事 | 属于哪个上层方案 | 不碰什么 |
|---|---|---|
| 2.5 注入 L1/L2/L4 材料、落 field_semantics | Q（喂什么） | O 的埋点（llm_calls）、P 的检查（不在此写） |
| 2.5 用户纠正写回 field_semantics | Q + 第8层 D4（纠正记录） | 不改 S3 校验逻辑（那是 P） |
| 2.6 模板表 + 匹配 + 与 S2 整合 | 第8层 C2（分析模板沉淀） | O 的"过程时间轴"、P 的"事实对账" |

接口红线：**2.5 产出被 O 记录、被 P 消费；2.6 产出的模板仍须过 P 检查，模板不是免检。**

---

## 一、2.5 AI 自主推理语义

### 1.1 现状：出图时 AI 现在到底收到什么（已读 `s3_llm_enhancer.py`）

`_build_prompt`（L245-377）实际拼给 LLM 的内容：

| 块 | 代码位置 | 内容 | 缺什么 |
|---|---|---|---|
| `fields_desc` | L291 `f"  - {f}（{_desc(f)}）"` | 字段名 + `_desc`（类型标签 + `business_role` + `chart_hint`） | ❌ 无 distinct / 空值率 / 取值样例 |
| 派生指标口径 | L294-300 `annotate_fields` | 含「派生指标：X=A÷B，只能 avg」 | ✅ 已有 |
| `default_prompt` | L315-358 | 主题 + `dim_hint` + 粒度 + `goals_str` + 约束（第6条 L338 文字警告"严禁臆造字段"） | ❌ 约束力弱，靠文字 |
| `global_guard` | L375-376 | Prompt 中心 `system`+`accuracy` 前缀 | ✅ 已有 |
| 样本行 | — | **S3 完全没有** | ❌ S1(`s1_theme_detector.py:169-183`)、S2(`s2_goal_generator.py:231 sample_data[:3]`) 都有，S3 独缺 |

**关键事实**：`build_semantics`（`schema_enricher.py:153-204`）其实已经算出了 `meta[f]["cardinality"]`（mid/low/high）、`distribution_ok`、`business_role`、`chart_hint`、`ai` 标记，但 `_desc`（L278-289）**只取了 `business_role`+`chart_hint` 两个字段**，把 `cardinality` 丢了——所以"高基数字段禁止做饼图"这种信息，系统算出来了却没告诉 LLM。

> 结论（回答用户问题 2.5-1）：**现在 AI 收到的是"字段名+类型+业务角色+建议+派生口径+目标+粒度"，缺真实取值/基数/空值率/样本行，且已有 cardinality 没用上。**

### 1.2 要注入什么（回答 2.5-2，落地 Q 的 L1/L2/L4）

**(a) L2 数据画像升级 `fields_desc`（本方案最大单点收益，对应 Q 方案第二节）**

把 `_desc`（L278-289）从一行扩展为多行结构化画像，注入四类现成数据：

| 注入字段 | 数据来源（已核实存在） | 代码位置 |
|---|---|---|
| 字段类型 | `build_semantics` `type_map` | `schema_enricher.py:161` |
| 业务角色/建议 | `meta[f]["business_role"]`/`chart_hint` | `schema_enricher.py:194` |
| 基数（distinct 精确值） | 复用 `ai_quality_checker.py:108` `sample_values` 同口径的 COUNT DISTINCT；生成前算（不要等 `brain_run_sse.py:1051` 事后算） | 需新增：在 S3 调用前对 `fields` 跑 `SELECT COUNT(DISTINCT "{f}")` |
| 空值率 | `field_profiles`（`context["dataset_info"]["field_profiles"]`，即 D2 归因实查的数据源） | `ai_quality_checker.py:106`、`appendix_service.py:99` |
| 取值样例 | `ai_quality_checker.py:108` `sample_values[:5]` | 已算出 |
| 派生/禁用标注 | `annotate_fields` | `derived_metric_service.py:209` |

扩展后 `fields_desc` 形如（解决 Q 的 P1/P2/P3）：
```
  - 客户名称  文本标识 | distinct=2143 | 空值率 0% | ⚠️高基数，禁止作为分类维度
  - 担保类型  分类维度 | distinct=2 | 空值率 0% | 取值: 融资性,非融资性
  - 抵押率    【派生比率】= 担保余额÷抵押物评估价值，只能 AVG
  - 身份证号  【禁用】含敏感信息，禁止进图
```
改动点：`_build_prompt` L278-291（`_desc` 扩展）+ `generate_with_self_healing`（L386-387）调用方需额外接收 `field_profiles`（含 distinct/空值率/取值）并传入。

**(b) L3 样本注入（S3 补 3~5 行脱敏样本，对齐 S1/S2）**

S1/S2 已注入 `sample_data[:3]`，S3 没有 → 不一致。补 3~5 行**代表性**样本（覆盖各枚举取值 + 边界值）。
**脱敏硬红线**：识别敏感字段（名称/证件/电话/地址类，复用 `FieldAnalyzer.ID_PATTERNS` 同族正则或可扩展清单）→ 整列不注入或打码。**V4 一票否决，不许先上线再补。**

**(c) L1 业务词典（指标口径/枚举值域/禁用字段）**

新增可运营材料表（非代码硬编码），UI 复用现成 Prompt 中心（`frontend/src/views/admin/PromptCenter.tsx` 已有增删改查）。字段：
`business_dict(id, kind[口径/值域/禁用], field_or_topic, value, note, updated_by)`。
例：口径「抵押率=担保余额÷抵押物评估价值」；值域「担保类型∈{融资性,非融资性}」；禁用「身份证号/手机号/客户姓名」。

**(d) L4 反馈记忆（跨 run 沉淀，解决 Q 的"自愈错误只在单次 run 有效"）**

三类落库（均净新增或接现有）：
1. 自愈错误：现成 `error_section`（L257-264）目前只单次 run 内有效 → 落 `business_dict` 或 `field_semantics.note`，下次同数据集前置提醒。
2. 用户修改：用户在看板详情改了图字段/类型 → 写 `field_semantics`（source=user，覆盖 ai 值）。
3. 被 P 剔除的图：落 `ai_action_log`（第8层 D6，见 1.5）→ 该字段组合下次降权。

### 1.3 AI 推理结果落库设计（回答 2.5-3：field_semantics 表）

**全仓确认 `field_semantics` 不存在**（grep 无命中）→ 净新增表。

```python
class FieldSemantics(Base):   # backend/app/models/ 新增
    __tablename__ = "field_semantics"
    id            = Column(String(36), primary_key=True)
    dataset_id    = Column(String(36), index=True)
    field         = Column(String(120))
    field_type    = Column(String(20))     # CATEGORY/NUMBER/DATE/TEXT/GEO
    business_role = Column(String(120))    # 来自 build_semantics meta
    chart_hint    = Column(String(120))
    cardinality   = Column(String(10))     # low/mid/high（复用 build_semantics）
    distinct_count= Column(Integer)        # 新增：精确 distinct
    null_rate     = Column(Float)          # 新增：来自 field_profiles
    sample_values = Column(Text)           # 新增：取值样例 JSON
    is_forbidden  = Column(Boolean)        # 新增：敏感/禁用
    source        = Column(String(10))     # ai / rule / user
    confidence    = Column(Float)
    updated_at    = Column(DateTime)
```

**持久化逻辑**（不每轮重算）：
- `generate_with_self_healing`（L400-401）当前每次 `build_semantics(fields, theme)` → 改为：先查 `field_semantics` 表，缺才 `build_semantics`，结果写回表（`source=ai`）。
- 读取：`_build_prompt` 的 `_desc` 优先读 `field_semantics`（含 distinct/空值率/取值），表无才降级 `_desc` 现状。
- 与 O 接口：O 的 `llm_calls.prompt_digest` 复用此表的语义摘要（不重复算）。

### 1.4 用户纠正流程（回答 2.5-4）

触发点：用户在前端看板详情改某图 `x_field/y_field/类型`（现有链路 `DashboardOps.tsx` 回退成功 → `onConfigReload` → `GET /dashboards/{id}` → `setConfig`，见 PROJECT_STATUS 第8层注）。
设计：
1. 纠正落 `field_semantics`（该字段 `source=user`，覆盖 ai 值 + `updated_at=now`）。
2. 同时写 `ai_action_log`（第8层 D6，`action_type="field_correct"`）供 O/P 统计。
3. 下次同数据集生成：`_build_prompt` 读 user 修正语义 → LLM 不再犯同类错。
**不自动改用户正在看的图**（只影响下次生成），与 P 方案"不一刀切改写文案"同一原则。

### 1.5 与 O/P/Q 的接口边界（回答 2.5-5）

| 接口 | 谁写 | 谁读 | 落点 |
|---|---|---|---|
| field_semantics | 2.5 写 | O 读 prompt 摘要 / P 读 distinct 做 L2 基数检查 | 共用 `distinct` 阈值常量（饼图≤12、柱≤30，来自 P 方案 L2） |
| ai_action_log | 2.5 用户纠正写 | O 时间轴、P 检查统计 | 第8层 D6 表（2.5 不建，引用） |
| llm_calls.prompt_digest | O 建 | 2.5 填 field_semantics 版本号 | O 方案 L1 |

### 1.6 改动量 / 风险 / 工时（回答 2.5-6）

| 阶段 | 内容 | 工时 |
|---|---|---|
| P0 | L2 画像升级 `_desc` + 调用方传 field_profiles（distinct/空值率/取值） | 3 h |
| P1 | L3 样本注入（S3 补 3~5 行）+ 敏感字段脱敏 | 2 h |
| P2 | field_semantics 表 + build_semantics 持久化（不再每轮重算） | 2.5 h |
| P3 | L1 业务词典表 + 接 Prompt 中心 UI | 3 h |
| P4 | L4 反馈记忆（用户纠正写回 + 被剔除图降权） | 3 h |

**风险**（同 Q 方案第五节）：
- 数据泄漏（最大）：脱敏失败一票否决，V4 硬红线。
- prompt 变长 → 成本/延迟：预算优先级裁剪（Q 方案 P2）。
- 画像算错误导 LLM：distinct 由 duckdb 实算，不算失败标"未知"不瞎填。
- 加了反而变差：必须 A/B（依赖 O 埋点），不许凭感觉说"加了肯定好"。

---

## 二、2.6 分析模板库

### 2.1 现状（已读 `s2_goal_generator.py`）

| 能力 | 位置 | 说明 |
|---|---|---|
| 规则目标 | `generate_goals_rule_based`（L227 调用） | 按主题出候选 |
| LLM 增强 | `generate_goals_llm_enhanced` L213-273 | base_goals → LLM refine → `generated_by="llm"`（L268） |
| 规则配置 | `load_rules` L58-65 读 `goal_rules` config；`theme_rules` L69-79 默认按主题 | 已有"规则"机制 |
| 目标结构 | `AnalysisGoal` L17-38：`goal_id/title/description/type/priority/expected_charts/generated_by` | 当前内存对象 |
| 模板库表 | **全仓无** | 净新增 |

> 结论（回答 2.6 起点）：S2 已是"规则 + LLM"两阶段，缺"跨数据集复用"的第三层。模板库不是替代，是**在 base_goals 阶段并入候选**。

### 2.2 模板库结构设计（回答 2.6-1）

**净新增 `analysis_template` 表**（全仓确认不存在）：

```python
class AnalysisTemplate(Base):
    __tablename__ = "analysis_template"
    id            = Column(String(36), primary_key=True)
    name          = Column(String(120))          # 展示名，如"担保风控·标准六图"
    intent_skeleton = Column(Text)               # JSON：触发匹配用的"字段画像特征"
    trigger_conditions = Column(Text)            # JSON：匹配规则（见 2.4）
    goals_json    = Column(Text)                 # JSON：复用 AnalysisGoal.to_dict() 结构
    charts_json   = Column(Text)                 # JSON：预置图表配置（可选）
    usage_count   = Column(Integer, default=0)
    last_used_at  = Column(DateTime)
    created_by    = Column(String(10))           # ai / user
    approved      = Column(Boolean, default=False)# 必须经用户确认才生效
    score         = Column(Float, default=0.0)   # 质量分（来自 P 检查）
```

**意图骨架（intent_skeleton）不是精确字段名，而是"字段画像特征"**，例：
```json
{"theme_hint":"担保|风控", "must_have_types":["CATEGORY","NUMBER"],
 "semantic_hints":["抵押率→比率类","担保金额→数值指标"], "min_fields":4}
```
→ 这样"另一份担保数据"也能命中，不绑定具体列名。

### 2.3 积累机制（回答 2.6-2：AI 沉淀 + 用户确认）

1. **AI 沉淀（候选）**：一次生成结束且 P 检查全 pass（`check.status` 全 `pass`/`auto_corrected`，无 `removed`）→ 提一候选模板（`created_by=ai`, `approved=False`）。
2. **用户确认（生效）**：管理后台/看板详情加"保存为模板"按钮（复用 Prompt 中心 `PromptCenter.tsx` 的增删改查模式），用户点确认 → `approved=True`。
3. **防污染**：未确认模板只进候选表，**不自动套用**；`approved=False` 的模板匹配命中也不预填。

### 2.4 匹配机制（回答 2.6-3：触发才用）

新数据集进来 → 算字段画像（复用 `build_semantics` + 2.5 的 field_semantics）→ 对 `analysis_template` 逐条匹配 `trigger_conditions`：
- 字段类型集合覆盖 `must_have_types` ✅
- 语义 hints 命中（如存在"比率类"字段）✅
- 字段数 ≥ `min_fields` ✅
→ 命中 → 该模板进 S2 候选源。**不命中则完全走现有 rule+LLM，零影响。**

### 2.5 与现有 S2 目标生成整合（回答 2.6-4）

当前（`generate_goals_llm_enhanced` L227）：`base_goals = generate_goals_rule_based(...)` → `llm_chat` refine（L244-271）。
新增第三层（不破坏现有 fallback L249-252）：

```
base_goals = generate_goals_rule_based(...)          # 原有
matched = match_templates(dataset_profile)          # 新增：命中 approved 模板
base_goals += [AnalysisGoal.from_dict(t.goals_json) for t in matched]  # 并入候选
# 之后照旧 LLM refine；LLM 看不到"这是模板"也行，它只是多了一组候选目标
```

改动点：
- `generate_goals_llm_enhanced` L227 前插入 `match_templates`（2.4 逻辑）。
- `load_prompt("s2_goal_generator", ...)`（L234）可注入 `matched_templates` 让 LLM 参考（可选，不强求）。
- `fallback`（L249-252）规则兜底保持不变 → 模板命中失败也不影响兜底。

### 2.6 与 O/P/Q 接口边界（回答 2.6-5）

| 接口 | 说明 |
|---|---|
| O | `llm_calls` 增 `template_id` 字段，记录本次命中哪个模板（O 方案 L1 表已预留扩展位） |
| P | 模板衍生的图**仍过 P 检查**（模板不是免检；`score` 来自 P 的 `check`） |
| Q | 模板触发条件用 Q 的字段画像（2.5 的 field_semantics） |

### 2.7 改动量 / 风险 / 工时（回答 2.6-6）

| 阶段 | 内容 | 工时 |
|---|---|---|
| P0 | `analysis_template` 表 + `match_templates` 函数 | 2 h |
| P1 | AI 沉淀候选（P 检查全 pass 才提） | 1.5 h |
| P2 | 用户确认 UI（复用 Prompt 中心模式） | 3 h |
| P3 | S2 整合（L227 前插入匹配） | 2 h |

**风险**：
- 模板错配导致图跑偏 → `approved` 门禁 + P 检查兜底（错配的图会被 P 剔除，不进看板）。
- 自动污染 → 未确认模板不套用（2.3 防污染）。
- 过度依赖模板 → 同数据集每次长一样 → 模板只作"候选增强"，LLM 仍主导，不强制采纳。

---

## 三、验收标准（方案阶段，落地时再转测试）

| # | 2.5 断言 | 怎么验 |
|---|---|---|
| V1 | `fields_desc` 含 `distinct=` 与 `空值率`，高基数字段带"禁止作为分类维度" | 看 S3 prompt 拼接结果 |
| V2 | 构造含 distinct=2000 的"客户名称" → LLM 不再选它为饼图维度 | 对比改造前后 |
| V3 | `field_semantics` 表在一次生成后写入，二次生成读表不重算 `build_semantics` | SQL 查 + 日志 |
| V4 | 敏感字段（身份证号）不出现在任何 prompt/样本 | 全量 prompt 落库抽查（O 的 `prompt_full` 开时） |
| V5 | 用户改某图字段 → 下次同数据集生成用修正值 | 构造 + 重跑 |

| # | 2.6 断言 | 怎么验 |
|---|---|---|
| V6 | `approved=True` 模板命中 → S2 预填该组目标 | 构造数据集匹配 + 看 goals |
| V7 | `approved=False` 模板命中 → **不**预填 | 同上，门禁验证 |
| V8 | 模板衍生的图被 P 判 `removed` → 不进看板（模板非免检） | P 检查联动 |

---

## 四、交付物（本阶段只出方案）

- 本文件 `plan_25_26_semantic_and_template.md`
- 不动任何代码（用户纪律：先给方案拍板）
- 待拍板后，按 1.6 / 2.7 的 P0→P4 顺序落地，每项落 `defect_fix_evidence/final_fixes/ev_25*.md` / `ev_26*.md`
