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

> 维护方式：每条待办记录「现象 / 决策 / 到期或触发条件 / 状态」。解决后把状态改为 `[DONE]` 或删除该行。
