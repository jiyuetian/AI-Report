# ISSUES.md — 待办跟踪

> 维护方式：每条待办记录「现象 / 决策 / 到期或触发条件 / 状态」。解决后把状态改为 `[DONE]` 或删除该行。

---

## ISS-030 智谱 glm 资源包到期 / 耗尽

- **现象（原始）**：`.env` zhipu provider 曾用 `glm-5.3-flash`（实名赠送包 500 万 tokens，2026-09-24 生效、到期 2026-10-24）。night14 Task A（D-020）调整为七层链，引入 `glm-4.5-air`（新用户专享 1200 万，到期 10-25）与 `glm-4.6v`（专属余 600 万）。
- **现状（2026-10-03）**：**提前耗尽**——实测 `zhipu-air(glm-4.5-air)` 与 `zhipu-46v(glm-4.6v)` 均返回 429「余额不足或无可用资源包」（原定 10-25，实际 10-03 已不可用）。
- **决策（2026-10-03 用户拍板）**：**下掉** `glm-4.5-air` / `glm-4.6v` 两层；`glm-4.7-flash`（官方免费）实测可通，保留。链由 **7 层收敛为 5 层**：`kimi-k3 → glm-4.7-flash → deepseek-v4-flash → agnes → sensenova-lite`。改前备份 `.env.bak_20261003_llmchain`。
- **状态**：`[DONE]`（2026-10-03，见 `AI_CHANGES.md` §十七）。后续如续包可再入链。

## ISS-031 glm-5.3-flash 是推理模型，仅作兜底

- **现象**：`glm-5.3-flash` 为推理模型（响应带 reasoning tokens，实测一次约 197 reasoning tokens / 140 completion tokens）。相对主用 `kimi-k3`（sensenova）**延迟更高**。
- **决策**：**只作 failover 备胎，绝不设主用**。主链路保持 sensenova(kimi-k3) → 失败才走 zhipu(glm-5.3-flash)。
- **依据**：若把它设主用，每次对话/每次 brain/run 都会多花思维链时间，拖慢整体响应；且推理模型在 json_mode 下已验证可正常返回 content（未踩 sensenova-6.8-flash-lite 的坑），作备胎安全。
- **状态**：`[OPEN]` 长期约束，与 ISS-030 联动（换模型时也遵守此原则）。

---

### 关联上下文（2026-09-24 同批工作）
- A 修复：llm_gateway.py failover 吞错（HTTP 200 内嵌错误体未切备胎）→ 已落码 + 真跑通过。
- D 修复：chat.py 自然回复「假承诺」诚实兜底 → 已落码 + 8 条断言真跑通过。
- b.ai provider 已删除（余额 0，永不成功）；zhipu 原 `glm-4.7-flash` 无额度 → 换 `glm-5.3-flash`。
- 限流分析：`night5/LLM_RATE_LIMIT_ANALYSIS.md`。

---

## ISS-032 feasibility_checker NameError 导致所有动作意图崩溃

- **现象（2026-09-28 night7 Item2 复测发现）**：`backend/app/core/feasibility_checker.py` 的 `@staticmethod _check_field_existence` 内，第 212 行引用类属性 `_GENERIC_CONCEPT_WORDS` 时用了裸名（类作用域内不可见）→ `NameError: name '_GENERIC_CONCEPT_WORDS' is not defined`。该异常在 `checking_feasibility` 阶段抛出，使 **任何动作意图（change_chart / add_chart / delete_chart 等）整条 SSE 流以 error 事件中断**，`complete` 永不触发，前端表现为「发了指令但看板无变化、无回复」。
- **影响面**：对话链路 P0 级回归——所有会进入可行性检查的指令全部失败（纯问答/unknown 不受影响）。
- **根因**：commit `b340e98`（Q11 可行性检查放宽）新增该常量作类属性，但在 `@staticmethod` 内以裸名访问，staticmethod 无 `self/cls`，类属性不在作用域。
- **修复（已落码 + 真跑通过）**：改为 `FeasibilityChecker._GENERIC_CONCEPT_WORDS`。修复后 Item2 五组对话中 T1(change_chart)/T2(add_chart)/T4(change_chart→clarify) 均正常执行，看板图数按预期变化。
- **状态**：`[DONE]` 修复 commit 见 night7/ROUND_NOW.md（本地未 push）。

## ISS-033 上下文指代「再来一个」未推断为 add_chart

- **现象（2026-09-28 night7 Item2 复测）**：T2 刚 `add_chart` 新增趋势图后，T3「再来一个」被分类为 `unknown`（0 action），系统反问澄清而非顺势再加一张图。非崩溃，属意图分类对省略上下文指代的覆盖不足。
- **决策**：低优先级。若要做，应在 intent_classifier / 上下文记忆层对「再来一个 / 再加一个 / 也来一个」在上一轮为 add_chart 时推断为 add_chart（沿用上轮分析方向）。D 边界（诚实兜底）在此场景下仍成立：未假称已添加。
- **状态**：`[OPEN]` 待排期（下一轮对话增强主线处理）。

---

## ISS-034 CHART-01 散点/热力图 config 占位符未替换 + heatmap 字段绑定缺失

- **现象（2026-09-24 night8 TEST-1 模块A 规则引擎基线实测）**：11 夹具 56 图全量核查发现，**所有 10 张散点图** `config.x="{number_field1}"`、`config.y="{number_field2}"` 为 YAML 字面占位符（前端若读 config 渲染轴名将显示字面 `{number_field1}` 等）；**D3a 热力图** `config.x/y/value` 同为占位符，且其 `x_field/y_field/category_field/value_field` 全为 `None`（heatmap 在字段绑定段根本无分支）。
- **影响**：`x_field/y_field` 本身绑定正确（真实字段），缺陷仅落在 `config` 字典 → 若前端读 `config.x/y` 会拿到占位符；heatmap 则无字段可绑定，图不可用。
- **根因**：`backend/app/core/brain_modules/s3_chart_engine_v2.py` 第 445–465 行字段绑定段只处理 line/bar/pie/map/kpi/histogram/scatter/table，**heatmap 分支缺失**；第 467–477 行 `config.update(...)` 段 line/bar/pie/map/histogram 都有分支，**scatter/heatmap 漏写** → config 直接沿用 YAML 占位符。
- **修复（已落码 + 验证通过）**：① 445–465 段补 heatmap 分支 `x=c0, y=c1, val=n0`；② 467–477 段补 `config.update({"x":x,"y":y})`（scatter）与 `config.update({"x":x,"y":y,"value":val})`（heatmap），用真实字段覆盖占位符；散点绑定同步改为最佳两指标 n0/n1 与标题一致。
- **验证**：11 夹具真实 CSV 复跑 `_rulebaseline.json`，散点/热力图 config 占位符 0 例；D1 散点 config.x/y 由 `{number_field1}`/`{number_field2}` → 真实字段（如 担保余额/收入负债比）。
- **状态**：`[DONE]` fix(chart) commit 见 night8/ROUND_NOW.md（本地未 push）。基线证据见 `TEST1_A_BASELINE.md` + `_rulebaseline.json` / `_rulebaseline_before.json` / `_rulebaseline_after.json`。

## ISS-035 CHART-02 兜底饼图缺 cardinality 校验（潜在）

- **现象（night8 TEST-1 基线，潜在未触发）**：`_apply_fallback`（`s3_chart_engine_v2.py` 第 634 行）对 `pie` 仅校验 `cat_f or num_f` 是否存在，**不校验分类基数**。若唯一分类列基数 >8（如 地区 200 类），兜底饼图会生成不可读的超高扇区饼图。
- **根因**：634 行 `if ctype in ("bar","pie") and (not cat_f or not num_f): continue` 未复用 `chart_constraints.pie.max_slices`（第 312 行）做基数上限判断。主规则饼图（`s3_chart_rules.yaml` 120–122 `category_cardinality: {min:2,max:8}`）已限制，仅兜底路径漏。
- **触发**：本次 11 夹具未触发（D6c 20 类地区被识别为 geo→map；饼图仅出现在低基数字段）。必须修以防回归。
- **修复（已落码 + 验证通过）**：634 行后补 `if ctype=="pie": _pcat=self._best_dim(cat_f,cardinality); if not _pcat or cardinality.get(_pcat,0)>self.chart_constraints.get("pie",{}).get("max_slices",8): continue`。
- **验证**：单测高基数分类(基数200)+数值字段走 `_apply_fallback`，产出类型 [bar,kpi,table]，**无 pie**（此前会生成 200 扇区不可读饼图）。
- **状态**：`[DONE]` fix(chart) commit 见 night8/ROUND_NOW.md（本地未 push）。

## ISS-036 CHART-03 直方图 bins=20 硬编码

- **现象（night8 TEST-1 基线实测）**：10/11 数据集直方图 `config.bins` 恒为 20。
- **根因**：`s3_chart_rules.yaml` 第 158 行 `config: {field: "{number_field}", bins: 20}` 硬编码；引擎 476–477 行 `config.update({"field": y})` 只覆盖 field，未覆盖 bins。
- **修复（已落码 + 验证通过）**：引擎侧按字段去重数自适应计算 bins（clamp 到 [5,30]），YAML 去掉硬编码 20（改注释说明由引擎算）。
- **验证**：11 夹具真实 CSV 复跑，直方图 bins 取值 {5,12,23,28}（此前恒为 20），均 ∈[5,30] 且 !=20。
- **状态**：`[DONE]` fix(chart) commit 见 night8/ROUND_NOW.md（本地未 push）。

---

## ISS-037 ISS-034 编号在 night7/night8 间被复用（澄清）

- **现象**：night7 commit `05b7cd7` 的提交信息里写「ISS-034（对话丢消息入口探针诊断日志）」，但 night8 把 **ISS-034 复用于 CHART-01**（散点/热力图 config 占位符，见上 ISS-034 条目）。两个完全不同的问题共用了同一个编号。
- **根因**：night7 当时把「对话链路丢消息的入口探针诊断日志」暂记为 ISS-034（当时为 OPEN 观察，未正式建条目）；night8 新建 CHART-01 时未察觉该占用，顺延占用了 ISS-034。
- **澄清**：
  1. night7 `05b7cd7` 提交信息中的「ISS-034」= **对话丢消息入口探针诊断日志**（OPEN 观察，尚未闭环，原始记录见 `docs/project_record/night_runs/night7/ROUND_NOW.md` 及相关探针日志）。
  2. 本文件 ISS-034（上方）= **CHART-01 散点/热力图 config 占位符**，night8 修复已 `[DONE]`。
- **决策**：保留 night8 的 ISS-034=CHART-01（已闭环、引用最广）；night7 那个「对话丢消息入口探针诊断日志」问题**不再占用 ISS-034**，其正式编号待 night7 复盘时另行分配。本条目仅作冲突登记，避免后人误读 05b7cd7 的 ISS-034 指向 CHART-01。
- **状态**：`[DONE]` 本条目为编号冲突澄清；被澄清的「对话丢消息入口探针诊断日志」问题本身仍为 `[OPEN]`（不在本仓库本轮范围）。

---

## ISS-038 跨看板上下文串号（历史过锚定的跨看板形态）

- **现象（2026-09-28 night9 Item2 复测确认）**：前端看板切换 `/dashboard/A → /dashboard/B` 复用同一 `<ChatPanel>` 组件实例，组件无 `key` 故不重挂载，`sessionId` state 滞留 A 的旧值；切 B 首条消息带 A 的 `session_id` + `dashboard_id=B` 发出 → 后端 `chat.py` 按 `session_id` 加载历史（旧看板 A 的对话），注入当前看板 B 的上下文，表现「在 B 看板里 AI 仍引用 A 的旧话题」。这是 ISS-015 Bug1（历史过锚定）的跨看板广义形态。
- **确定性复现**：隔离 SQLite + stub LLM 复测脚本（看板A聊2轮 MARKER_ALPHA → 切B带A的session_id发问），修复前 `context_dashboard_id=dashB` 但 `history` 含 A 的 4 条 MARKER_ALPHA 消息（`leak_MARKER_ALPHA=true`）。
- **根因**：① 前端 `DashboardPage.tsx` 未给 `<ChatPanel>` 设 `key={urlId}`，切看板不重挂载，`loadHistory()` 仅 mount 跑一次；② 后端 `chat.py` 取/建会话后直接 `dashboard_id = request.dashboard_id or session.dashboard_id`，当 `session.dashboard_id != request.dashboard_id` 时仍信任旧 session，把旧看板历史注入当前看板。
- **修复（已落码 + 确定性回归通过）**：
  1. 后端 `chat.py`（ISS-038 归属校正块）：取/建会话后增加——若 `session.dashboard_id != request.dashboard_id`，以「当前 dashboard_id + 登录用户」为权威重新定位到当前看板最新会话（无则新建），使注入历史恒为当前看板历史。同看板多轮（session 不变）零行为变更。
  2. 前端 `DashboardPage.tsx:1398` 给 `<ChatPanel>` 加 `key={urlId}`，切看板时 React 重挂载，重新 `loadHistory()` 拉当前看板会话（双保险）。
- **验证**：复测脚本回归 `leak_MARKER_ALPHA=false, history_len=0`（跨看板不再泄漏，同看板多轮不变）；前端 `tsc --noEmit` 退出码 0。
- **状态**：`[DONE]` 修复 commit 见 night9/ROUND_NOW.md（本地未 push）。

---

## ISS-039 单轮 edit_title / change_chart(字段) 规则未命中（B1-5 / B1-7 / B1-10）

- **现象（2026-09-29 night9 Item4 规则模式基线）**：`send_message_stream` 真实链路下，以下单轮指令规则引擎未产出对应动作（图数/字段/筛选无变化）：
  - B1-5 `把标题改成销售分析` → 标题未变（edit_title 规则未命中）。
  - B1-7 `把Y轴换成利润` → y_field 未变（change_chart 字段替换规则未命中）。
  - B1-10 `只看2025年数据` → config.filter.year=None（时间筛选规则未抽取年份）。
- **证据**：`docs/project_record/night_runs/night9/TEST1_B_BASELINE.md`（dash_id dashB_B1-5 / dashB_B1-7 / dashB_B1-10，结果 FAIL）。
- **决策**：属「规则引擎本应命中但未命中」类缺陷；需与 B2/B3 的「规则模式天然缺 LLM 字段抽取」缺口区分。
- **修复（2026-09-29 night10 Item1）**：三处规则缺口已闭环，确定性真测全 PASS（见 `night_runs/night10/ROUND_NOW.md` 第 1 件）：
  - B1-5 `把标题改成销售分析`：单图看板「把标题改成X」自动带 `chart_id`+`scope=chart`，改图标题而非看板标题（原误改看板标题）。
  - B1-7 `把Y轴换成利润`：新增「轴/字段替换」正则（`Y轴换成利润`）→ change_chart(target_field=利润, target_axis=y)；`detect_vague_chart_type` 在 `target_field` 存在时返回 None（不反问图型）。
  - B1-10 `只看2025年数据`：FILTER_DRILL 抽取年份分支 → filter_field=年份/filter_value=2025/is_year=true；filter_drill 落库补 `year` 键（修复 `re` 未 import 的 NameError 崩溃）。
- **状态**：`[DONE]`（night10 Item1 修复 + 复测 5/5 PASS）。

## ISS-040 纠正指令规则未承接（B4-1 / B4-7）

- **现象（2026-09-29 night9 Item4 规则模式基线）**：`不是饼图，是柱图` 与二次纠正 `不是这个，是那个` 均未把图型改为柱图（纠正意图规则未承接；B4-3 承接澄清「折线图」可改，说明澄清承接可用但「否定+纠正」句式规则未覆盖）。
- **证据**：`TEST1_B_BASELINE.md`（dashB_B4-1 / dashB_B4-7，结果 FAIL）。
- **决策**：仅记录不修（本轮不修）。
- **修复（2026-09-29 night10 Item1）**：CHANGE_CHART 新增「否定+纠正」正则（`不是X(是|换成|改成|改为|变成)Y`，覆盖饼图/柱图/线图/散点图/环形图/表格）→ change_chart(source_type=饼图, target_type=柱图)；确定性真测全 PASS（B4-1 单次纠正、B4-7 二次纠正均 chart_type=bar）。
- **状态**：`[DONE]`（night10 Item1 修复 + 复测 5/5 PASS）。

## ISS-041 复合 add_chart 规则模式不加图（B1-2 / B2-1 / B2-2 / B2-3）

- **现象（2026-09-29 night9 Item4 规则模式基线）**：`新增一张地区分布图` / `删掉X加上月度趋势图` / `把饼图改成柱图，再加一张 KPI` / `加上地区、渠道、产品分布` 在 LLM 被 stub（限流）时图数不变（add_chart 需 LLM 抽取真实字段，规则模式不产出图）。
- **证据**：`TEST1_B_BASELINE.md`（dashB_B1-2 / dashB_B2-1 / dashB_B2-2 / dashB_B2-3，结果 FAIL）。
- **决策**：标记为「规则模式天然缺口（待 AI 模式补测）」，非纯缺陷；仍需 LLM 限流解除后真跑确认 AI 模式能补上。仅记录不修。
- **night11 Item6 补判**：AI 模式补测的底层依赖是 json_mode 可靠性，已被 Item2（ISS-044）JSON 防护闭环（`_ai_baseline.log` D6a / `_popup_risk03.log` 均出现非法 JSON→`[LLM-JSON-FIX]` 强化 prompt 重试自愈）。故复合 add 现可稳定产出多图 JSON、逐图落库；详见 `night_runs/night11/AI_VS_RULE.md` §5。
- **状态**：`[DONE]`（night23 Task B，commit `c4f7727`）。复合拆分机制（`split_clauses` + `plan_actions`）已确定性验证 22/22 PASS（T1 删+加、T2 加+改均 `is_compound=True` 且 `len(actions)=2`）；零 DB、禁真 LLM（mock）。浏览器端到端逐图落库为体验侧确认项（非阻塞，json_mode 可靠性由 ISS-044 闭环保障）。详见 `docs/project_record/night_runs/NIGHT_SUMMARY.md` night23 Task B 段。

## ISS-042 多轮语义承接②动作空（B3-2 / B3-3 / B3-4 / B3-5 / B3-7 / B3-8）

- **现象（2026-09-29 night9 Item4 规则模式基线）**：② 轮承接①的图/筛选/时间维度/目标图，在规则模式下②动作多为空（B3-1 `再来一个`→add_chart、B3-6 `只看Q1`→filter_drill 已 PASS，证明部分承接可用，但「那就折线图/用华南/同上但要柱状/换成折线/把阈值调80%/往前再挪一张」等语义承接规则未覆盖）。
- **证据**：`TEST1_B_BASELINE.md`（对应 dashB_B3-*，结果 FAIL）。
- **决策**：标记为「规则模式天然缺口（待 AI 模式补测）」，非纯缺陷；需 LLM 限流解除后真跑确认 AI 模式承接质量。仅记录不修。
- **night11 Item6 补判**：多轮承接的 json_mode 动作依赖同 Item2 JSON 防护；非法 JSON 现可自愈（重试+failover），续加动作不再因单次 JSON 失败打断会话。详见 `night_runs/night11/AI_VS_RULE.md` §5。
- **状态**：`[DONE]`（night23 Task B，commit `c4f7727`）。多轮语义承接已确定性验证 22/22 PASS：①「那就折线图」(vague_chart_type) 解析为 change_chart 且锚点保留（T3）；②「第二张」(which_chart) 承接 = options[1]=销售额趋势（T4）；③「用华南」(which_filter_value) 此前无路径 → 新增 `filter_drill` 承接（filter_field=地区 / filter_value=华南，T5）+ 维度带 categories 时主动发射 which_filter_value 澄清（T5b）；单句 change_chart 回归（T6）、无匹配短答案不抛 NameError（T7）均 PASS。零 DB、禁真 LLM（mock）。详见 `docs/project_record/night_runs/NIGHT_SUMMARY.md` night23 Task B 段。


## ISS-043 六层 LLM failover 模型透传 bug（全部 provider 永不命中备胎）

- **现象（2026-09-29 night10 Item2 探活）**：kimi-k3 限流（429）时，网关 6 层 failover 每个 provider 都收到 `model=kimi-k3`，智谱/DeepSeek/glm 拒收 → 400/1211「模型不存在」，6 层全失败（`LLM-ALL-KEYS-FAILED`）。直接逐模型直调却显示 glm-5.3-flash / glm-4.5-air / deepseek-v4-flash 均 200（key 有效）——证明备胎 key 没坏，是 failover 没切模型。
- **根因**：`llm_gateway.py:393` `model = request.model or prov.get("model")`，`request.model` 有值时对所有 provider 锁死 kimi-k3，备胎自身 model 永不生效。
- **修复（2026-09-29 night10，commit 9c9e1b7）**：首层沿用调用方显式 model，failover 层改用各 provider 自身 model。直调验证：kimi 429 → zhipu(glm-5.3-flash) success=True。
- **状态**：`[DONE]`（9c9e1b7）。

## ISS-044 备胎 glm-5.3-flash json_mode 返回非法 JSON，结构化 AI 动作落空

- **现象（2026-09-29 night10 Item2 真跑）**：failover 修好后 kimi 429 → glm-5.3-flash 兜底；自然语言生成（讲解/澄清/润色/免责）高质量可用（例 B4-2：「讲清楚一点」意图不明确→请补充期望，glm-5.3-flash 生成）。但 glm-5.3-flash 对 json_mode（分类/字段抽取/复合 add）偶发「未包含有效 JSON」（`LLM响应JSON解析失败`），导致 `intent_classified` 走规则兜底、add_chart 抽不到字段、复合动作空。规则引擎可接管的意图（如 B4-2 走 semantic_rule）不受影响。
- **影响**：AI 模式当前「自然语言回复」可用；依赖 json_mode 的结构化动作（B1-2/B2-*/ISS-041 复合 add、ISS-042 多轮承接、需 LLM 分类的 B4-* 澄清）在 glm-5.3-flash 兜底下不稳定。kimi-k3 限流解除后（kimi json_mode 稳）方可完整跑通。
- **决策（2026-09-29 night11 Item2 已修）**：在网关层加 JSON 防护，不依赖等 kimi 限流：
  ①`_extract_json` 先剥 Markdown 围栏（```json ... ```）再解析（原实现漏此步，推理模型包围栏会解析失败）；
  ②json_mode 解析失败自动重试一次，重试时向 messages 注入强化 prompt（「只返回合法 JSON、不要围栏」），retry 后成功记 `[LLM-JSON-FIX]` 恢复日志；
  ③仍失败切下一层 provider（原 failover 路径保留）。
- **验证**：确定性集成测试 6 场景（合法/围栏/文本包裹/非法→重试恢复/两连败→切provider/全败降级）= 5/5 可恢复（含 1 个故意全败降级基线）；单元级 `_extract_json` 围栏/平衡括号断言通过。真模型冒烟 3 次（kimi 429→zhipu glm-5.3-flash）均 parsed=True，`REAL_JSON_SUCCESS_RATE=3/3`。
- **状态**：`[DONE]`（night11 Item2，commit 见 night11/ROUND_NOW.md）。备胎 JSON 可靠性已闭环；deepseek-v4-flash 提 json_mode 主备仍可作为后续加固选项（非必须）。

## ISS-045 弹窗反复弹（根因已修，剩 UX）

- **现象（用户 2026-09-29 实测）**：对话中弹窗连续反复弹出，打断操作。
- **根因**：已修（night7 `d12c419` 弹窗 P0 三件：探针测真实 provider 链 + 用户选择不静默吞 + 前端旁路封堵；night10 ISS-043 修 failover 模型透传后，kimi 429 不再瞬间连发 6 层失败告警，弹窗触发频率大幅下降）。
- **剩余（UX）**：连续失败时的弹窗节流/合并展示未做，短时间内多条告警仍可能连弹。
- **night11 Item6 回归（真实文件）**：重传 `risk_demo_v2_03`（48×29，17 率类列）重跑 AI 图表生成链路，全程日志（`_popup_risk03.log`）：`sensenova` 429 → 重试 → `[LLM-JSON-FIX]` 强化 prompt 重试解析成功 → `生成成功`，`generated_by=llm`、`chart_count=5`，**单次干净完成、无 JSON 失败风暴、无连续弹窗**。与 A 夹具 D1/D5/D6a 的 AI 生成日志（`_ai_baseline.log`，D6a 同样出现 zhipu 非法 JSON→JSON-FIX 自愈）互证：Item2 JSON 防护（failover + 1 次强化 prompt 重试）已消除「JSON 解析失败→SSE 反复报错→前端连续弹窗」死循环。
- **状态**：`[DONE]` 根因（错误循环驱动弹窗已消除）；UX 节流 `[DONE]`（night13 第6件：前端 `throttledMessage` 节流/合并已落地，`tsc --noEmit` 0 错，UI 自测待用户在浏览器确认）。

## ISS-046 KPI 平均坏账率显示 0

- **现象（用户实测，risk_demo_v2_03 业务月度总览表）**：KPI 卡「平均坏账率」显示 0。
- **根因（与 047/048 同族）**：坏账率量级极小（≈0.0004，即 0.04%），KPI 卡未做比率格式化直接按原始浮点展示 → 舍入到 0。
- **决策（night11 Item3 已修）**：新增 `frontend/src/utils/metricFormat.ts` 统一比率格式化（字段名含「率」/_rate/ratio → 百分比，v×100 保留 2-4 位小数去尾零；其余数值走亿/万紧凑 + 极小数值保留小数），覆盖 KPI 卡/柱标签/坐标轴/直方图分桶标签/明细表/tooltip。
- **修复（已落码 + 真值验证）**：`deriveKpi` 改用 `formatKpiValue`（比率×100 不再被 toFixed(2) 成 0）；真实 fixture 验算 坏账率均值 0.000249 → KPI 显示 `0.0249%`（旧 `0`）、担保代偿率 → `0.3628%`、逾期率_总体 → `0.1526%`。
- **状态**：`[DONE]`（night11 Item3，commit 见 night11/ROUND_NOW.md）。

## ISS-047 直方图 X 轴全 0~0

- **现象（用户实测）**：直方图 X 轴范围显示 `0~0`（应为数值分布区间）。
- **根因（与 046/048 同族）**：直方图分桶基于极小比率字段，bins 边界计算溢出/全 0 → 轴范围 0~0。
- **决策（night11 Item3 已修）**：直方图分桶端点用统一 `formatMetricDisplay`（比率→百分比、极小数值保留小数），不再 `Math.round` 成 0。
- **修复（已落码 + 真值验证）**：坏账率直方图 bins 旧显示 `0~0` → 新 `0.0038%~0.0482%`（min 3.8e-05 / max 0.000482 格式化）。
- **状态**：`[DONE]`（night11 Item3）。

## ISS-048 比率 17 位小数裸奔

- **现象（用户实测）**：图表/明细中比率值展示 17 位小数（如 0.00041234567890123456）。
- **根因（与 046/047 同族）**：比率字段无小数位约束，float 全精度裸奔。
- **决策（night11 Item3 已修）**：柱标签/坐标轴/tooltip/明细表单元格统一走 `formatMetricDisplay`，比率→百分比 2-4 位小数、金额走亿/万紧凑，杜绝裸奔 17 位小数。
- **修复（已落码 + 真值验证）**：坏账率柱标签/轴/tooltip/明细旧裸奔 `0.0002489583333333333` → 新 `0.0249%`；覆盖 bar/map/scatter 三类图表 + 明细表。
- **状态**：`[DONE]`（night11 Item3，柱标签/轴/tooltip 已接 formatMetricDisplay）。

### ISS-048 night12 补漏（柱值标签仍裸奔）
- **现象（用户下午复测）**：「担保类型 vs 坏账率」柱图 value label 仍显示 `0.0002` 裸数，night11 的修复未生效。
- **真根因（night12 只读定位）**：night11 在 bar 分支把格式化字段写成 `formatMetricDisplay(value_field, …)`，但 `_build_chart` 对 bar/line/table **只写 `y_field`、不写 `value_field`**（value_field 仅 pie 用）。故 bar 的 `value_field` 恒为空 → `formatMetricDisplay(undefined, …)` → `isRatioField` 判否 → 回退 `formatCompactNum` → 极小比率裸奔 `0.0002`。night11 实际只覆盖了「数据取值」(line 814 用 `value_field || y_field`)，**漏了格式化字段**。map 分支 `geoVal` 同理漏 `|| y_field`。
- **修复（night12）**：bar 分支新增 `const metricField = value_field || y_field`，tooltip / yAxis name / 轴标签 / 柱 value label 全部改用 `metricField`；map 分支 `geoVal` 补 `|| y_field`。前端 `tsc --noEmit` 退出码 0。逻辑验证：兜底前 `label=0.0002` → 兜底后 `label=0.0249%`（PASS）。
- **附**：同次 tsc 冒烟发现 night12 第 1 件（ISS-052）bar 分支 `_topN` 行 `chart.top_n` 不在 `ChartConfig` 类型上（`tsc` 报错 TS2339），已一并改为 `chart.config && chart.config.top_n` 修正，前端 tsc 归零。
- **状态**：`[DONE]`（night12 补漏，commit 见 night12/ROUND_NOW.md 第 2 件）。

## ISS-049 散点图轴绑金额与标题不符

- **现象（用户实测）**：「担保代偿率 vs 坏账率」散点图，X/Y 实际为金额量级（0~180亿 / 0~60亿），与「率」标题不符。
- **根因（night11 Item4 已只读定位）**：AI 模式 `S3LLMEnhancer` 让 LLM 自由选 `x_field/y_field`；当散点标题点名比率字段（担保代偿率/坏账率）时，LLM 常把轴绑到该比率的**底层金额分量列**（期末代偿余额≈180亿 / 坏账核销金额），导致坐标轴呈金额量级、与「率」标题矛盾。规则引擎 night8 已有护栏「次指标不重复选派生指标的分量列」（s3_chart_engine_v2.py:409-414），**AI 路径此前缺位**。
- **修复**：`s3_llm_enhancer.py` 新增 `_fix_scatter_axis`（AI 成功路径在 `_apply_derived_metrics` 之后调用）：利用 `derived_metrics` 映射，仅当图表标题**点名**某比率字段时，把该比率的分量金额轴反绑回比率字段（分量即分子，语义恒正确）；标题仅含泛化比率词未点名具体比率时，也把分量反绑到所属比率；纯金额 / 非比率意图散点不改动，避免误绑。确定性单测 6 场景全 PASS（`_verify_scatter.py`）。
- **决策**：night11 Item4 已修 + 确定性回归；真实文件 AI 实时生成受沙箱网络 SIGTERM 限制，以确定性单测（复用该 fixture 真实分量映射）作为前后对比验证。
- **状态**：`[DONE]` night11 Item4。

## ISS-050 明细只 6 列

- **现象（用户实测）**：数据明细表只展示 6 列，宽表被截断。
- **根因**：`DashboardPage.tsx` 两处 `chartData.columns.slice(0, 6)` 截断列、`data.slice(0, 5/20)` 截断行，宽表（如 risk_demo_v2_03 共 29 列）只看到前 6 列。
- **修复（night11 Item5）**：明细表（`renderDetailTable` + 图表详情弹窗）改为展示**全部列** + `scroll={{ x: 'max-content' }}` 横向滚动；数据行全量分页（每页 20、可切页、显示总行数）。明细单元格仍走 Item3 统一比率格式化（`formatMetricDisplay`）。
- **状态**：`[DONE]` night11 Item5。

### ISS-050 night12 收尾（数据明细预览）
- **现象（用户下午复测）**：要求明细区升级为「数据明细预览」——默认只看前 10 行 × 全部列的快速预览，带「查看完整数据」入口；比率字段在预览态固定 2 位小数。
- **修复（night12 第 4 件）**：`renderDetailTable` 改造：①标题 `数据明细` → `数据明细预览`；②置顶 header `预览：前 10 行 × 全部 N 列`（N=列数），展开后变为 `完整数据：全部 M 行 × 全部 N 列`；③默认 `chartData.data.slice(0, 10)` 预览，行数 >10 时显示 `查看完整数据` link，点击切换全量（分页 20/页），再次点击 `收起为预览（前 10 行）`；④预览态比率字段走 `formatPercent(num, 2)`（2 位小数 + 去尾零），完整态沿用默认精度 `formatMetricDisplay`。前端 `tsc --noEmit` 退出码 0。逻辑验证：`0.000249` 预览→`0.02%`（默认 4 位→`0.0249%`）。
- **状态**：`[DONE]`（night12 第 4 件，commit 见 night12/ROUND_NOW.md）。

## ISS-052 add_chart 语义路由 + 维度护栏（P0，本轮核心）

- **现象（用户 2026-09-23 下午复测）**：对 `risk_demo_v2_03`（48×29）说「顶部新增担保余额最新的累计值」，AI 产出 30+ 根柱形图（担保余额 48 个不同值 → 48 柱），标题为原始整句「顶部新增担保余额最新的累计值」；X 轴曾绑到原始长数字串（高基数数值字段）。
- **根因（只读定位，四洞）**：全链路 `intent_classifier.py`（意图 + 结构化 charts 规格）→ `action_executor.py`（`_execute_add_chart`/`_build_chart` 物化 config）。
  ① 单值语义误判：数值单指标无图型词时默认 `bar`，且 `_extract_add_charts` 规则 ≤1 张回落 LLM 兜底易臆造柱图；
  ② 维度质量护栏缺失：仅 `_is_numeric_field` 判轴适格，无「高基数数值/疑似 ID」不适格判定；
  ③ 无 Top-N 兜底，维度全量密排；
  ④ 前端单维度柱图走默认多色循环。
- **修复（已落码 + 确定性真测 EXIT=0 通过）**：
  ① 后端 `intent_classifier.py` 新增 `_single_value_intent`/`_chart_semantic`，数值单指标 + 无图型词 + 无图语义 → `kpi` 单值卡，标题 `字段（最新）`，aggregation 取 max/sum；`_extract_add_charts` 早返回：规则确定性单指标 KPI 直接采用，不回落 LLM；
  ② 后端 `action_executor.py` 新增 `_is_good_dimension`（数值仅低基数 ≤12 或年份/等级码适格，ID/序号/时间戳/编号不适格）+ `MAX_DIM_CATS=20`，不适格有指标 → 降级 KPI，无指标跳过；
  ③ `bar/line` 维度基数 >20 写 `top_n=20, sort=desc`，前端柱图按 `top_n` 排序切片；
  ④ 前端 `DashboardPage.tsx` 单维度柱图 `itemStyle:{color:'#1677ff'}` 单色。
- **验证**：确定性测试 `_verify_iss052.py` 3 场景全 PASS（原句→KPI `y_field=担保余额,aggregation=max,title=担保余额（最新）`；高基数数值维度→降级 KPI；低基数文本维度月份→允许作 bar）。真 LLM 端到端截图受沙箱网络限制，逻辑层前后对比已由确定性测试覆盖（同 night11 ISS-049 处置）。
- **状态**：`[DONE]`（night12 第 1 件，commit 见 night12/ROUND_NOW.md）。

## ISS-051 清洗策略平铺看不懂

- **现象（用户实测）**：附录 B 78 条清洗策略平铺罗列，可读性差。
- **根因**：`AppendixPanel.tsx` 把 `clean_log` 直接渲染成扁平 Table（序号/阶段/算子/策略/目标字段/影响行数/说明），每字段多条记录铺开，无按字段聚合。
- **修复（night11 Item5）**：后端 `appendix_service._clean_log` 透出每条记录的 `issue_type`（apply 取 `params.issue_type`，detect 取 `iss.type`，均来自已有管线元数据、非新计算）；前端 `AppendixPanel` 改为**按字段叙事卡片**：`字段名 | 清洗动作(算子·策略 Tag) | 清洗前(空值x/异常y/重复z 行，按 issue_type 归类 affected_rows) | 清洗后(已修复/已忽略/待处理 行)`。按字段影响行数降序排列，78 条平铺→每字段一卡。
- **状态**：`[DONE]` night11 Item5。

### ISS-051 night12 改向（叙事卡片 → 行级明细表）
- **现象（用户下午复测）**：用户拒绝 night11 的「叙事卡片」方向，要求改为**行级明细表**（列：原始数据行号 | 字段 | 问题类型 | 清洗策略 | 清洗前数据 | 清洗后数据）。
- **只读核查（数据模型）**：后端 `_clean_log`（`appendix_service.py:116`）仅按 `(dataset_id, target_field, issue_type)` 与 `(dataset_id, field_name, type, status)` **聚合**存储——字段含 `issue_type / strategy / stage / affected_rows(影响行数) / status`；`data_cleaner.py` **不记录**原始数据行号、逐行清洗前/清洗后单元格值。故用户期望的「原始数据行号 / 清洗前数据 / 清洗后数据」三列在当前管线元数据里**不存在**，无法构建真正的逐数据行明细（不编造）。
- **修复（night12）**：`AppendixPanel` B 段由「按字段叙事卡片」改为 `cleanLogTable` 行级明细表，列 = 字段 | 阶段 | 问题类型 | 清洗策略 | 影响行数 | 清洗后状态，并置顶 `Alert` 明示「元数据未记录逐行明细」。这是现有元数据的诚实重组（聚合级行 = 一条 clean_log 记录），非伪造逐行前后值。如需真逐行明细，须在 `data_cleaner` 落 `change_log`（行号/旧值/新值），超本轮范围，建议单列需求。
- **4 指标卡一致性核查**：用户观察到 B 段 4 张卡均显示相同统计（0空值/4异常/2修复/1忽略/1待处理）。代码核查——night11 `cleanLogCards` 的 `byField[f]` 聚合正确按字段作用域（每字段 `nullN/abnormalN/dupN/fixed/ignored/todo` 在 `.map(f=>` 内重置、仅累加该字段 entries），**无聚合 bug**；4 卡雷同属数据特征（risk_demo_v2_03 各字段质检分布相近），非代码缺陷。night12 改为表格后每条 clean_log 记录直接成行，原「卡片雷同」困惑自然消解。
- **状态**：`[DONE]`（night12 改向 + 诚实数据缺口说明，commit 见 night12/ROUND_NOW.md 第 3 件）。

> 维护方式：每条待办记录「现象 / 决策 / 到期或触发条件 / 状态」。解决后把状态改为 `[DONE]` 或删除该行。

## ISS-053 Dependabot 高危漏洞（依赖审计 + 安全版本钉固）

- **现象**：night13 第7件立项的依赖安全审计（GitHub Dependabot 告警在沙箱无网络不可直接拉取，改为本地 manifest 静态审计）。
- **范围**：`backend/requirements.txt`（精确钉版）+ `frontend/package.json`/`package-lock.json`。
- **后端已钉固的高危/中危（已修，待 `pip install -r backend/requirements.txt` 生效；沙箱无网络未实装）**：
  | 包 | 旧版本 | 新版本 | CVE | 等级 |
  |---|---|---|---|---|
  | python-multipart | 0.0.9 | 0.0.12 | CVE-2024-53981（未限制 part 数→资源耗尽 DoS） | HIGH |
  | pandas | 2.2.0 | 2.2.2 | CVE-2024-27330 / CVE-2024-27331（read_pickle/read_json 任意代码执行） | HIGH |
  | jinja2 | 3.1.3 | 3.1.4 | CVE-2024-34064（xmlattr 属性注入） | MODERATE |
  | email-validator | 2.1.0 | 2.1.1 | CVE-2024-1916（EmailStr ReDoS） | MODERATE |
  | httpx | 0.26.0 | 0.27.2 | CVE-2024-47081（.netrc 凭据经代理泄漏） | MODERATE |
- **前端**：`package.json` 全部用 `^` 范围（安装时自动取最新 minor/patch），建议 CI 跑 `npm audit` + `npm update` 并重新生成 `package-lock.json` 落锁；重点核对 `axios`（^1.6.7，锁文件若 <1.7.4 受 CVE-2024-28849、<1.8.0 受 CVE-2025-27152 SSRF）。
- **状态**：`[DONE-代码]`（钉版已落 `requirements.txt` + 本登记）；**待办**：①`pip install` 实装后端钉版（需联网，沙箱未跑）；②前端 `npm audit`/`npm update` 落锁（待 CI/用户执行）。

---

## ISS-057 run_backend.py `_pid_alive` 探活在 Windows 不可靠，B5 单实例守卫会误杀重启（P0，night14 Task0）

- **现象（night14 Task0 复现 + 定位）**：`backend/run_backend.py` 的 `_pid_alive(pid)` 用 `os.kill(pid, 0)` 探活、只 `except OSError`。在 Windows 上有两处致命缺陷：
  ① **明显不存在的 PID（如 999999）**：本机 `Python 3.12.10` 抛 `OSError(WinError 87)`，可被 `except OSError` 兜住；但其他 Python/Windows 构建可能抛 `SystemError`（**非 OSError 子类**，已验证 `issubclass(SystemError, OSError) == False`）→ 未捕获 → 启动器在 B5 守卫前直接崩溃（连 `[B5]` 打印都到不了）。
  ② **更隐蔽且本机 100% 可复现的真 bug**：进程被强杀/崩溃退出后，其内核对象（EPROCESS）往往尚未被完全回收，`os.kill(pid, 0)` **不抛任何异常** → 旧实现返回 `True`（误判"存活"）→ B5-1 守卫据此拒绝新的启动 → **后端永远起不来**（典型症状：上次异常退出后删掉 `.backend.pid` 又好了）。
- **根因**：Windows 上 `os.kill(pid, 0)` 语义不可靠——既不保证对死 PID 抛"可捕获"的异常，也不保证对"已退出但内核对象残留"的 PID 返回"不存在"。用"能否发信号"来推断"进程是否存活"在 Windows 上是错的。
- **修复（已落码）**：Windows 分支改走 ctypes：
  `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)` →
  - 句柄为空且 `GetLastError() != ERROR_ACCESS_DENIED(5)` → 进程不存在 → `False`；
  - 拿到句柄后再 `GetExitCodeProcess`：退出码 `== STILL_ACTIVE(259)` → 真在运行 → `True`；否则（已是具体退出码）→ 进程已终止（句柄只是残留对象）→ `False`。
  这是 Windows 上唯一能区分"残留句柄"与"真运行"的可靠手段，彻底消除上面的误判。非 Windows 保留 `os.kill(pid, 0)`（catch `OSError/SystemError/ValueError`）。任何异常一律视为"不可探测 → 视为不存在"**放行启动**，B5-2 端口占用检测仍是双进程的最终兜底。
- **验证（`_verify_iss057.py` 全 PASS，未触碰 8000 活后端）**：
  - A1 真实 bug（刚被杀 PID）：旧=`True`(误判存活) / 新=`False`(正确放行)；
  - A2 明显死 PID(999999)：新=`False` 且不崩溃；
  - A3 活后端 PID（或本进程）：新=`True`（双进程防护仍正确，不误杀真·活进程）；
  - B1/B2 复刻 `main()` 的 B5-1/B5-2 守卫：残留死 pidfile → 放行启动；
  - C1/C2 **真实驱动 `main()`**（uvicorn.run 桩，隔离端口 18099）两轮：无 pidfile 与残留死 PID(999999) 均到达 `[B5] 启动后端`——完整跑通原本崩溃/误杀的那段守卫代码。
- **状态**：`[DONE]`（night14 第 1 件 Task0，commit 见 night14/ROUND_NOW.md，本地未 push，未碰生产 DuckDB）。


---

## ISS-058 对话「把阈值调X%」未映射为任何动作（功能缺口，night14 D-append 登记）

- **现象（night14 Task3 B3-7 复测暴露）**：多轮承接用例「①只看高风险 → ②把阈值调80%」，第②轮 `动作=[]`。`intent_classifier` / `action_planner` 均未把「阈值调整」识别为可执行意图，`ActionExecutor` 也无对应动作实现——即使把请求直发给 zhipu 拿到合法 JSON，响应里也没有任何动作描述。**真实未覆盖功能缺口，非回归**。
- **影响面**：用户赖以「在对话里动态调风险阈值 / 筛选阈值」的诉求无法落地；当前只能走质检面板手动改阈值规则。模块 B 的 B3-7 因此保持 FAIL（10 条 AI 模式补测中唯一剩余 FAIL）。
- **根因**：对话动作体系（add_chart/change_chart/delete_chart/filter_drill/reorder_chart/edit_title/undo…）未包含「阈值/筛选条件调整」类动作；`filter_drill` 只承接「只看华东」式枚举值替换，不承接「阈值=80%」式数值条件变更。
- **关联**：与 ISS-052（维度护栏）、ISS-055（输出护栏）同属对话动作骨架范畴，但属增量功能而非护栏修复。
- **决策（night14 D-append）**：本轮**仅登记、不实现**（用户明确「只登记，本轮不实现」）。实现时需新增 `ADJUST_THRESHOLD` 意图 + 对应 executor 动作（落 `config.filters` 的阈值条件并回写看板），并在 night13 动作栈补 `reverse` 以支持 undo。
- **状态**：`[DONE]` **night18 已实现（commit `f0cc1fb`，2026-10-03）**。落地清单：
  1. `intent_classifier.py`：`IntentType.ADJUST_THRESHOLD` 意图（置顶防 `FILTER_DRILL` 抢词）+ `_extract_params` 分支（`threshold_field` 抽字段，前缀停用词剥离防"把"被吞；`value` 归一化：带 `%` 或 >1 → ÷100；否则原值）。
  2. `action_planner.py`：`ADJUST_THRESHOLD → adjust_threshold` 映射 + `_ALLOWED_SEMANTIC_TYPES` 白名单。
  3. `action_executor.py`：`ActionType.ADJUST_THRESHOLD` + `executors` 注册 + `_execute_adjust_threshold`（写 `config.thresholds[field]`（避免与 filter_drill 的 `config.filters` 语义冲突）；区间护栏 `(0, 1]`；`deepcopy` 不污染传入；产 `reverse` 支持 undo）。
  4. `remove_on_undo` 短路分支：撤销首次设阈值时 `value=None` + `remove_on_undo is True` → 直接 `pop`，绕开 `float(None)` 校验，闭环 B3-7 撤销路径。
  5. `AI_CHANGES.md` §14 台账登记。
- **验证**：`backend/_verify_iss058.py`（零 DB，走真实 `execute_action` 派发，同 chat.py L1027 undo 路径）5/5 PASS —— a) `把阈值调80%`→0.8 写入 ✅ b) `阈值设成0.85`→保持0.85 ✅ c) `把阈值调500%`→越界 `requires_clarify` ✅ d) 缺字段→`requires_clarify` ✅ e) undo 首次设阈值→`thresholds` 清空 + reverse 存原值 0.8 可 redo ✅。`py_compile` 三文件全绿。
- **回归**：与 `filter_drill` 不冲突（`把阈值调80%`→`adjust_threshold`；`只看2024年的数据`→仍走 `filter_drill`）；未 push，等本机手推。


## ISS-059 analytics.compare_two_periods.compute_stats 对 `e["data"]` 未做 `.get` 防御（night18 TEST-2 全量回归暴露）

- **现象（night18 n18_7 TEST-2 全量回归发现）**：`backend/app/core/analytics.py` 的 `compute_stats(events)` 与 `compare_two_periods(...)` 内部，直接以 `e["data"]` 索引访问事件字典；当事件缺 `data` 字段时抛 `KeyError: 'data'`。
- **触发路径**：`UsageStats.record_event` 的 `data` 参数为可选（chat.py / llm_gateway.py 埋点均传参），但下游 `compare_two_periods` 未做防御性读取；只要有一条事件缺 `data`，前后段对比接口 `/usage-stats/...` 会 500。
- **影响面**：`compare_two_periods` 目前仅被 `UsageStats.get_stats` / `analyze_patterns` 调用，用于「最慢模型」「7 日前后对比」等分析；生产上未观察到真实异常（埋点均已带 `data`），但属于**契约不匹配**——下游不防御上游可能缺字段的形态，属健壮性缺口。
- **根因**：`_verify_taskjk.py` 场景构造事件时未带 `data` 字段，暴露真实生产代码未做 `e.get("data", {})` 兜底。night17 Task J 引入 `UsageStats` 时 `data` 字段是隐式约定，未落成文档契约。
- **修复建议（下轮做）**：`compute_stats` / `compare_two_periods` 内所有 `e["data"]` 改为 `e.get("data", {})`；同时给 `UsageStats.record_event` 加类型注解 `data: Dict[str, Any] = {}`，把契约显式化。零 DB、纯静态改动，低风险。
- **状态**：`[DONE]` — 教练验收轮（2026-10-03）根因级修复，commit `（见 AI_CHANGES.md §十六）`。
  - **修复范围（比原建议扩大）**：不止 `compute_stats` / `compare_two_periods`，而是 `analytics.py` **全文件**事件字段防御化——`bucket_events` / `get_model_usage_stats` / `get_action_usage_stats` / `get_peak_usage_hour` / `get_slowest_model` / `get_top_actions` 一并改 `.get(...)` 兜底（`data` 用 `(event.get("data") or {})`）。
  - **验证**：新增 `_verify_iss059.py`（隔离，gitignored）9/9 PASS（缺 `data` / `success` / `event_type` / `latency_ms` 事件全不崩）；回归 `_verify_taskjk.py` 17/17、`_verify_iss058.py` 5/5、`_verify_taskg.py` ALL、`_verify_taski.py` 32/0 全 PASS；`py_compile` EXIT=0。

## ISS-060 澄清收敛话术后「确认」无法采纳（night21，P0 回归）

- **现象（教练核实）**：night19 任务B 的澄清收敛话术 "请回复「确认」采用该方案" 与代码行为矛盾——收敛即清除 pending（`params.converged=True` → chat.py 走 pop 分支），下一轮用户回「确认」时 `_pending` 为 None，跳过 `detect_confirmation` 承接分支，无法采纳。收敛话术承诺了一个不存在的确认路径。
- **根因（4 处）**：
  1. `action_planner.py:_converge_clarify` 返回 `type=clarify` + `params.converged=True`，`params.pending` 只带 `{intent_type, partial_params}`，**无 proposal**；options 仅置于 params 顶层。
  2. `chat.py`（收敛扫描分支）遇 `params.converged` 仅置 `_converged=True; break`，**不写** `_clarify_pending`。
  3. `chat.py`（`elif _converged` 分支）`pending_clarify` 被 pop 清空。
  4. 下一轮「确认」：`_pending` 为 None → 跳过 `plan_actions` 的 confirm 承接分支（L687-714）→ 无法采纳。
- **修复（已落码 + 13/13 验证通过）**：
  - `_converge_clarify` 增加 **proposal**：调 `_resolve_pending_clarify("第一个", ...)` 取最佳项可执行动作 → 非 clarify 即 `proposal={intent_type, partial_params}`；`vague_chart_type` 缺图锚点时用 `options[0]` 图型 + 已有锚点/第一张图 拼可执行 `change_chart` proposal（补 `title_keyword`/`chart_id`）；无选项/无锚点则收敛文案**改不引导"确认"**，改引导用户直接给图名/序号。
  - `chat.py` 收敛分支改为**持久化带 proposal 的 pending**（含 `proposal` + `clarify_round=MAX_CLARIFY_ROUNDS`），而非 pop；收敛且无 proposal 仍维持 pop（文案已不引导确认）。
  - `detect_confirmation` 的**否定词表补「取消」**——收敛话术本就引导用户回「取消」放弃，原词表未收「取消」致其无法命中 cancel_pending（R5 依赖）。
- **零回归保证**：confirm（L687-714）/ negate（L676-686）/ `cancel_pending` 清除 pending 三条既有路径均不变；收敛 pending `clarify_round>=MAX`，再次模糊输入幂等重新收敛，不会无限追问。
- **状态**：`[DONE]`（2026-10-03 night21，见 `AI_CHANGES.md` §23）。验证脚本 `_verify_clarify_cap.py`（gitignored，过程文件）扩展为 13/13 PASS。


## ISS-025 未鉴权端点全量收口（P1 遗留，分批）

- **现象（night19 任务C 全量扫描）**：`app.openapi()` 解析 216 路由 / 131 未鉴权，按「A 高危写 47 / B 内部 73 / C 保留匿名 11」三类。A 类含执行看板增删改、token 消耗/申请、报告生成、批处理与调试注入等 21 个写端点 + `GET /exceptions/session/kickout/{user_id}`，均无任何鉴权，匿名可越权。
- **决策（任务书 + 分批建议）**：Batch1 优先收口最高危 A 类写端点；Batch2（B 类 73）内部端点走 env 闸门（prod 默认关）；C 类 11 按设计保留匿名。
- **修复进度**：
  - **Batch1（2026-10-03 night22 Task B，DONE）**：22 个目标端点全加 `Depends(get_current_user)`，`kickout/{user_id}` 加归属校验（非本人且非超管 → 403）；body 取值 `current_user` → `current_user["user_id"]`（chat / tokens / token_applications 三处）。commit `8f6c56d`（本地未 push）。验证 `_verify_iss025_batch1.py` 22/22、全量回归零回归（health 15/15、ISS-060 13/13、history 10/10）。
  - **Batch2（B 类 73 内部端点 env 闸门，DONE）**：75 个端点（清单称 73，差异 2 属统计口径）加 `Depends(internal_endpoint_guard)`，prod 默认 `ENABLE_INTERNAL_ENDPOINTS=off` → 无 token 返回 401 不执行；dev 设 `on` 放开。night23/24/25 连通性验证器持续 PASS。
  - **recalc 路由漂移修复（2026-10-04 night26 Task A，DONE）**：`backend/app/main.py:228` 前缀 `/api/v1` → `/api/v1/recalc`，闭环 B 类 gate 路径漂移 H1（原 6 路由挂在 `/api/v1/*` 与前端调用点 `/api/v1/recalc/*` 错位，前端 4 调用点 prod 无 token 仍 401——gate 生效，但路径错位属结构缺陷，已修）。同步更正 `22-ISS025无鉴权端点全量扫描.md` B 类清单 6 处 + `_night24_verify_b.py`。
- **C 类 11 保留匿名**：按设计保留（如 `/health`、静态资源等），非缺项。
- **状态**：`[CODE_CLOSED]` 代码侧主链路全收口——A 类 47（22 写 + `kickout` 归属校验）已加硬鉴权、B 类 gate 已落地且无路径漂移、C 类按设计保留。**验收侧 11 项待用户本机**（push 比对远端 / DB 真跑 / 真实看板绿标 / 用户拍板），属上线决策或需真实环境，非代码缺项 → 可判「ISS-025 代码闭环，验收待真机」。详见 `docs/project_record/05-ISS025鉴权审计.md` 与 `22-ISS025无鉴权端点全量扫描.md`、night26 `NIGHT_SUMMARY.md` Task A/E。

---

## ISS-062 首次自动质检被静默跳过（StrictMode / 重挂载守卫提前置位）

- **现象（用户实测 risk_demo_v2_01 贷款明细表看板）**：上传新数据集后，质检面板偶尔完全不自动跑质检（面板空、无 toast、无 loading），必须手动点「重新质检」才出结果；StrictMode 双挂载或切 tab 重挂载后尤为明显。
- **根因**：`QualityCheckPanel.tsx` 自动质检 `useEffect` 在**定时器前**就把 `autoHandledRef.current = datasetId` 置位（守卫）；当 effect 因重挂载先 cleanup 清掉 500ms 定时器、再重挂载时，守卫已命中 `if (autoHandledRef.current === datasetId) return` → 直接 return，自动质检被永久跳过。另：`runCheck` 的 `silent` 模式仍弹 `message.error`（未用 `!silent` 门控），与「静默保留」诉求冲突。
- **修复（已落码 + 结构级验收通过）**：
  1. 守卫赋值移入 500ms 定时器**回调内**（`autoHandledRef.current = datasetId` 在 `setTimeout(() => {` 内部先置位再 `runCheck()`），重挂载不再提前命中守卫；「同一 datasetId 只跑一次」语义保留。
  2. 500ms 内数据表未就绪（404/!ok）→ `runCheck` 返回 null → 1.5s 后静默重试一次（`autoRetryRef`），仍失败则静默保留（不弹错误、不阻断），由用户手动「重新质检」。
  3. `runCheck` 全部 toast 用 `!silent` 门控，silent 模式彻底静默。
- **验证**：`_verify_night27_iss062_066.py` 结构断言 PASS（守卫已移入定时器、旧 bug 模式已消除、404 重试、silent 门控）。浏览器真机复测为体验确认项（非阻塞）。
- **状态**：`[DONE]`（night27 Task A，本地未 push）。

## ISS-063 一键批量修复无超时 / 反馈弱 / 无重试入口

- **现象（用户实测）**：点「一键修复全部问题（N项）→」后，若后端串行写清洗层耗时较长，界面只有一条 `message.loading(key='plan', duration:0)` 永久卡住；网络慢/挂起时无超时、无取消、失败后无重试入口，只能等或刷新。
- **根因**：`applyRecommendedPlan` 的 `/quality/fix-batch` fetch **无 AbortController 超时**；唯一反馈是 `duration:0` 的 loading；`catch` 仅 `message.destroy('plan')` + error，无重试。
- **修复（已落码 + 结构级验收通过）**：
  1. 加 60s `AbortController` 超时（`setTimeout(() => ctrl.abort(), 60000)`）+ 取消（`planAbortRef`）。
  2. 底部内联状态条：实时秒表（「正在按推荐方案批量修复… 已用时 Ns」）+「取消」按钮。
  3. `applyError` state 渲染 `Alert` 错误卡 +「重试修复」按钮（重跑同模式）；成功/部分失败内联 `Alert`（成功绿 / 部分失败黄）展示 `已修复 X 项，Y 项失败`。
- **验证**：`_verify_night27_iss062_066.py` 结构断言 PASS（AbortController / 60s 超时 / 取消 / 内联状态条 / 重试修复 / applyError）。
- **状态**：`[DONE]`（night27 Task B，本地未 push）。

## ISS-064 「重置」只清前端、不回滚清洗层（脏数据残留）

- **现象（用户实测）**：质检面板点「重置」后，前端问题列表清空，但**后端清洗层物理表未删、已采纳的修复未撤销**；且残留的 `message 'plan'`（duration:0）会卡在界面。重新质检时数据已是被清洗过的状态，重置形同虚设。
- **根因**：`resetAll` 只 `updateState(newState)`（前端状态），**无后端调用**；修复写清洗层、重置未回滚。
- **修复（已落码 + 结构级验收通过）**：
  1. 后端新增 `POST /quality/{dataset_id}/reset`：先 `_assert_dataset_access`（归属校验，非本人/非超管 404）→ `DROP TABLE IF EXISTS` 清洗层物理表 → `QualityIssue.status` 置 `ignored` → 清 `_AI_RESULT_CACHE[dataset_id]`。
  2. 前端 `resetAll` 改为 `async`：先 `message.destroy('plan')` 清残留提示 → 调后端 reset → 成功后清空本地状态 + 自动 `runCheck()` 刷新。
  3. 「重置」按钮改文案「重置数据（撤销清洗）」+ 二次确认 Modal（「确定重置」，danger）。
- **验证**：`_verify_night27_iss062_066.py` 结构断言 PASS（按钮文案 / 后端路由 / DROP TABLE / 归属校验 / 二次确认）。后端路由真跑需起服务 + 鉴权（用户本机确认项）。
- **状态**：`[DONE]`（night27 Task C，本地未 push）。

## ISS-065 批量修复后自动弹 AI 报表生成（打断用户）

- **现象（用户实测）**：批量修复完成、无阻断项时，系统自动 `setTimeout(() => onProceed?.(), 700)` 弹 AI 报表生成，不打断用户操作流、用户无预期。
- **根因**：`applyRecommendedPlan` 成功路径末尾显式调用 `onProceed`（自动流转到看板生成）。
- **修复（已落码 + 结构级验收通过）**：删除自动跳转 `setTimeout(() => { onProceed?.() }, 700)`；改为 `message.success` 提示「质检通过…请点『生成看板』继续」，由用户手动点底部「生成看板」按钮。
- **验证**：`_verify_night27_iss062_066.py` 断言「自动跳转 onProceed 已删除」PASS。
- **状态**：`[DONE]`（night27 Task D，本地未 push）。

## ISS-066 动作轮单动作 AI 空回复 + 对话/看板失败处理未统一

- **现象（用户实测）**：对话里发单动作指令（如「新增一张趋势图」「把标题改成X」），执行器成功但执行器未回传 message → 后端 `complete` 事件 `message=""` → 前端**无条件 push 一个空气泡**（空白助手消息），且无任何失败说明 / 重试入口。
- **根因（双端）**：
  1. 后端 `chat.py` 动作轮：单动作 `response_data["message"]` 初始化为 `""`；汇总块 `parts` 仅收集非空 message，单动作成功但 message 为 None → `parts` 空 → `response_data["message"]` 仍为 `""`。
  2. 前端 `ChatPanel.tsx` 流结束 `assistantContent` 可空串，`setMessages(prev => [...prev, assistantMsg])` 无条件 push → 空气泡。
- **修复（已落码 + 结构级验收通过，统一 R1-R5）**：
  1. 后端 `complete` 事件守卫：若 `not response_data.get("message")`，优先 `generate_intent_response(intent_type, ...)` 回退文案；仍无则动作成功补中性确认、动作未成功诚实置 `ai_error`（stage/error/options=["retry","rule_fallback"]/message），对齐对话 `ai_error` 语义。
  2. 前端防空气泡：流结束若 `assistantContent.trim()` 为空，按 R4 用 `ai_error.message` 兜底文案（抉择入口由 ai_error 卡承载），绝不 push 空白气泡；`ai_error` 透传保留。
  3. 与看板生成的 `ai_awaiting` 抉择语义对齐（R1 判定 / R2 不静默不空 / R3 双入口 / R4 诚实标注 / R5 退避重试），本轮统一的只是判定/兜底/重试/标注规则，未改变对话 SSE 流式与看板后台轮询的传输方式。
- **验证**：`_verify_night27_iss062_066.py` 结构断言 PASS（前端 `if (!finalContent)` / `aiError.message`；后端 `if not response_data.get("message")` / `generate_intent_response` / 统一兜底文案）。对话真机 SSE 复测为体验确认项（需起服务，沙箱不可）。
- **状态**：`[DONE]`（night27 Task E，本地未 push）。
