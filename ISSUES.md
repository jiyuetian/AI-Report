# ISSUES.md — 待办跟踪

> 维护方式：每条待办记录「现象 / 决策 / 到期或触发条件 / 状态」。解决后把状态改为 `[DONE]` 或删除该行。

---

## ISS-030 智谱 glm-5.3-flash 资源包到期

- **现象**：`.env` 中 zhipu provider 已改用 `glm-5.3-flash`（替代无额度覆盖的 `glm-4.7-flash`）。该模型当前可用的额度来自「实名认证赠送」资源包 **500 万 tokens**，控制台显示生效 2026-09-24，到期 **2026-10-24**。
- **决策**：到期前必须处理，否则 zhipu 这条 failover 备胎会变回死项（整条链路只剩 sensenova 一个健康 provider）。
- **方案（二选一，到期前拍板执行）**：
  1. 切换到仍有资源包覆盖的 `glm-4.5-air`（新用户专享包 1200 万 tokens，到期 2026-10-25，并发上限未明，需先真跑确认）；或
  2. 在智谱控制台为 `glm-5.3-flash` 充值 / 续领免费额度。
- **状态**：`[OPEN]` 触发日 2026-10-24（建议 10-20 前处理）。

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
- **状态**：`[OPEN]` 待 AI 模式补测。

## ISS-042 多轮语义承接②动作空（B3-2 / B3-3 / B3-4 / B3-5 / B3-7 / B3-8）

- **现象（2026-09-29 night9 Item4 规则模式基线）**：② 轮承接①的图/筛选/时间维度/目标图，在规则模式下②动作多为空（B3-1 `再来一个`→add_chart、B3-6 `只看Q1`→filter_drill 已 PASS，证明部分承接可用，但「那就折线图/用华南/同上但要柱状/换成折线/把阈值调80%/往前再挪一张」等语义承接规则未覆盖）。
- **证据**：`TEST1_B_BASELINE.md`（对应 dashB_B3-*，结果 FAIL）。
- **决策**：标记为「规则模式天然缺口（待 AI 模式补测）」，非纯缺陷；需 LLM 限流解除后真跑确认 AI 模式承接质量。仅记录不修。
- **状态**：`[OPEN]` 待 AI 模式补测。


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
- **状态**：`[DONE]` 根因（弹窗触发源已堵）；UX 节流为 `[OPEN]` 待 night11 Item6 回归验证后评估。

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
- **状态**：`[DONE]`（night11 Item3）。

## ISS-049 散点图轴绑金额与标题不符

- **现象（用户实测）**：「担保代偿率 vs 坏账率」散点图，X/Y 实际为金额量级（0~180亿 / 0~60亿），与「率」标题不符。
- **根因（night11 Item4 已只读定位）**：AI 模式 `S3LLMEnhancer` 让 LLM 自由选 `x_field/y_field`；当散点标题点名比率字段（担保代偿率/坏账率）时，LLM 常把轴绑到该比率的**底层金额分量列**（期末代偿余额≈180亿 / 坏账核销金额），导致坐标轴呈金额量级、与「率」标题矛盾。规则引擎 night8 已有护栏「次指标不重复选派生指标的分量列」（s3_chart_engine_v2.py:409-414），**AI 路径此前缺位**。
- **修复**：`s3_llm_enhancer.py` 新增 `_fix_scatter_axis`（AI 成功路径在 `_apply_derived_metrics` 之后调用）：利用 `derived_metrics` 映射，仅当图表标题**点名**某比率字段时，把该比率的分量金额轴反绑回比率字段（分量即分子，语义恒正确）；标题仅含泛化比率词未点名具体比率时，也把分量反绑到所属比率；纯金额 / 非比率意图散点不改动，避免误绑。确定性单测 6 场景全 PASS（`_verify_scatter.py`）。
- **决策**：night11 Item4 已修 + 确定性回归；真实文件 AI 实时生成受沙箱网络 SIGTERM 限制，以确定性单测（复用该 fixture 真实分量映射）作为前后对比验证。
- **状态**：`[DONE]` night11 Item4。

## ISS-050 明细只 6 列

- **现象（用户实测）**：数据明细表只展示 6 列，宽表被截断。
- **决策**：night11 Item5 改为全列横向滚动（或表头标「预览：前N行×前M列」+ 完整数据入口）。
- **状态**：`[OPEN]` 待 night11 Item5。

## ISS-051 清洗策略平铺看不懂

- **现象（用户实测）**：附录 B 78 条清洗策略平铺罗列，可读性差。
- **决策**：night11 Item5 改为按列叙事卡片（字段名 | 清洗动作 | 清洗前 空值x/异常y/重复z | 清洗后）；数据来自管线元数据，仅重组展示非新计算。
- **状态**：`[OPEN]` 待 night11 Item5。

> 维护方式：每条待办记录「现象 / 决策 / 到期或触发条件 / 状态」。解决后把状态改为 `[DONE]` 或删除该行。
