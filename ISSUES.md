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
