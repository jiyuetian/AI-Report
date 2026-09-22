# AI 对话能力审计（只读 · 只查只答）

> 审计对象：`backend/app/api/chat.py`、`backend/app/core/action_planner.py`、`backend/app/core/intent_classifier.py`、`backend/app/core/action_executor.py`
> 分支：`p0-security-fixes`（HEAD `c225939`）
> 审计日期：2026-09-22
> 结论先行：**当前对话链路几乎 100% 由「正则规则 + 硬编码代码」驱动，LLM 仅在 3 处零星兜底参与，且上下文完全不注入历史对话。用户感知的「AI 含量」≈ 5%。**

---

## 0. 核心结论（一句话）

用户期待的「能理解语义、承接上下文、自主推理的 AI 助手」，实际是一个 **关键词正则机器人（改图/加图/删图/筛选/标题全写死）+ 一个只在「听不懂时」才出场的闲聊 LLM 兜底**，二者之间没有衔接——这就是「出乎意料地差、基本水平都达不到」的根因。

---

## 1. 当前对话链路完整路径图

```
用户输入 message
   │
   ▼
POST /api/v1/chat/message  (SSE 流式)            [chat.py:437]
   │
   ├─ 阶段1 获取/创建会话 + 读取看板配置 + 提取字段画像   [chat.py:457-542]
   │     └─ context = { session_id, dashboard_id, dataset_id,
   │                    dataset_info:{grain, field_profiles},   ← 仅字段画像
   │                    current_config }                         ← 仅当前看板配置
   │        ★ 注意：context 里【没有】任何历史对话消息（上一轮 user/assistant 都不在）
   │
   ├─ 阶段3 plan_actions(message, context)         [chat.py:593 → action_planner.py:233]
   │     │
   │     ├─ split_clauses：正则分句                 [action_planner.py:69]
   │     ├─ 逐句 classify_intent → IntentClassifier.classify
   │     │     └─ 遍历 INTENT_PATTERNS 正则，第一个命中即 return（置信度基础分 70）
   │     │        [intent_classifier.py:206-211]   ← ★ 99% 走这里（纯规则）
   │     │        全不命中才调 _llm_classify 兜底      [intent_classifier.py:213-217]
   │     │
   │     └─ 歧义检测（单轮 clarify 产出）：
   │           · 粒度冲突   [action_planner.py:156]
   │           · 模糊图型   [action_planner.py:176]
   │           · 字段不存在 [action_planner.py:287]
   │
   ├─ 阶段4 feasibility_check（可行性）             [chat.py:629]
   │
   ├─ 阶段5 响应生成
   │     ├─ plan 有 actions → 规则拼装响应（无 LLM）        [chat.py:696-706]
   │     ├─ UNKNOWN / 低置信 → generate_llm_natural_response [chat.py:707-737]
   │     │     ★ 唯一「AI 自然回复」入口，但只是客服式闲聊，不执行分析动作
   │     └─ 否则 → generate_intent_response 硬编码话术字典   [chat.py:110-202]
   │           ★ 模板化话术："好的，我将把图表改为柱状图。"
   │
   └─ 阶段6 execute_action（代码写死）               [chat.py:796 → action_executor.py:69]
         └─ _execute_change_chart / _execute_add_chart / _execute_delete_chart /
            _execute_filter_drill / _execute_edit_title / _execute_attribution
            ★ 全部纯函数，图型/字段/口径由参数直接决定，LLM 不参与决策
            （仅 _execute_add_conclusion 与 _execute_chart_fix 内含 LLM 润色/诊断）
```

---

## 2. 每步走「规则 vs LLM」比例

| 链路环节 | 代码位置 | 规则占比 | LLM 占比 | 说明 |
|---|---|---|---|---|
| 意图识别 | `intent_classifier.py:206` | **≈95%+** | <5% | 任何含动作动词/关键词的消息都正则命中即返回；LLM 仅在「全模式都不命中」的纯闲聊类兜底 |
| 参数提取 | `intent_classifier.py:310-566` | **≈100%** | 0%（主参数） | `_extract_params` 全正则；仅 `ADD_CHART` 多图有 LLM 结构化提取，且规则≥2 张时优先于 LLM（`intent_classifier.py:840-856`） |
| 动作规划 | `action_planner.py:233` | **100%** | 0% | 分句+逐句正则分类+歧义规则检测，无 LLM 参与 |
| 动作执行 | `action_executor.py:69` | **≈95%** | ≈5% | change/add/delete/filter/reorder/title/attribution 全代码写死；仅 add_conclusion（LLM 润色真实结论）、chart_fix（LLM 诊断）用 LLM |
| 回复生成 | `chat.py:110 / 707` | **≈95%** | ≈5% | 规则命中取硬编码话术字典；仅 UNKNOWN 走 LLM 自然回复 |
| **整链 AI 决策/推理参与度** | — | **≈95%** | **≈5%** | LLM 只在「闲聊 + ADD_CHART 多图 + 结论润色」三处点缀，且均非理解用户真实意图的核心链路 |

**关键陷阱（置信度机制）**：规则命中直接给 confidence≥70（`_calculate_confidence` 基础分 70），而 `is_confident = confidence >= 70`。于是**规则命中后 `is_confident` 永远为 True**，永远不会回落到「低置信→LLM 自然回复」分支。换句话说：**只要正则命中，LLM 对这条消息就完全没有发言权。**

---

## 3. 系统 Prompt 原文（对话链路涉及的全部 LLM 调用）

> 注：外置 `backend/app/core/prompts/*.md` 经确认**不存在**（`Glob core/prompts/*.md` 无结果），Prompt 中心（`prompt_manager._OVERRIDES`）为内存缓存且启动未从 DB 灌入覆盖，因此以下 LLM 调用实际生效的就是代码里的**默认文本**。

### (A) 意图分类 LLM 兜底 prompt — `intent_classifier.py:17-46`（仅规则全不命中时用到）
```
你是一个自然语言意图分类器，请将用户的消息分类为以下意图之一：

可用意图：
- change_chart: 修改图表类型（把饼图改成折线图等）
- add_chart: 新增一个图表
- delete_chart: 删除一个图表
- reorder_chart: 调整图表位置/排序
- filter_drill: 筛选数据、下钻分析
- attribution: 追问原因、归因分析
- edit_title: 修改标题
- unknown: 不确定

当前看板上下文：
{context}

请返回 JSON 格式：
{
  "intent_type": "change_chart",
  "confidence": 85,
  "analysis": {
    "raw_message": "用户说的话",
    "extracted_params": { "target_type": "line" }
  }
}

"注意：纠正类消息（'不是 A 是 B'/'我指的是…'）仍按原始意图分类..."
只返回 JSON，不解释。
```
> 问题：这个兜底 prompt 把「分析/追问/建议」也塞进 `attribution` 等固定意图，且没有「不理解就反问」的指令；且 `{context}` 只填 `json.dumps(context)`，而对话历史**不在 context 里**，所以 LLM 兜底时也看不到上一句。

### (B) ADD_CHART 多图 LLM 结构化提取 — `intent_classifier.py:635-656`（仅单图/常规表述时走）
```
你是一个 BI 图表配置助手。用户会在看板对话里要求新增图表。
请根据用户的自然语言，从给定字段画像中结构化输出要新增的图表列表。
字段画像（name 是真实字段名，必须原样引用，不得臆造）：{field_text}
要求：
1. 支持一次性新增多张图（顿号/、或并列列举拆成多张）
2. 每张图必须选真实存在的 dimension_field / metric_field
3. chart_type 取值：pie/bar/line/scatter/table/kpi
4. title 简洁准确
5. 只输出 JSON 数组
6. 泛指展开：每项/每个/所有 X 遍历所有匹配数值字段逐个出图
7. 聚合口径：平均值/均值 → aggregation:"avg"
8. 纠正理解：'不是 A 是 B' 只返回参数修正后的配置
你是主导，可以自由决定图型、数量和顺序，不要被任何规则限制。
```
> 这是全链路里**质量最高**的一处 LLM 使用（带真实字段白名单、泛指展开、纠正理解），但只服务于「加图」这一种动作。

### (C) LLM 自然回复 prompt — `chat.py:263-278`（UNKNOWN/低置信时）
```
system（load_prompt 实际回退默认一句话）：
  你是一位资深 BI 数据分析师助手，正在帮助用户分析和优化数据看板。

default_prompt：
  你是一位资深 BI 数据分析师助手，正在看板页面与用户对话。
  ## 当前看板信息
  - 主题: {theme}
  - 数据粒度: （宏观/汇总/明细）
  - 图表列表: {charts_text 或 （暂无图表）}
  ## 数据集字段
  {fields_text 或 （无字段画像）}
  ## 回答要求
  1. 直接回答，基于看板与字段信息，不要泛泛而谈
  2. 想分析数据时，给具体建议（用哪个字段、看哪张图）
  3. 想调整看板时，引导用具体指令（把饼图改成柱图、新增趋势图）
  4. 简洁专业，中文，200 字内
  5. 数据里没有的信息要坦诚说明，不要编造
  用户消息: {user_message}
  请直接回复用户（纯文本，不要 JSON）。
```
> 问题：①system 只有一句话，没有任何"承接上下文/多轮对话/主动分析"的指令；②`{charts_text}`/`{fields_text}` 来自当前看板，但**没有上一轮对话**，所以"用户说'再来一个'"时 LLM 不知道指什么；③要求 3 让它「引导用具体指令」——等于承认自己不会直接做，只能当引导员。

### (D) 结论润色 prompt — `action_executor.py:681-689`（add_conclusion 动作内）
```
你是BI分析师。只能使用下面【真实事实】中的字段名和数字写一句结论，
严禁出现事实之外的字段名、严禁编造数字、严禁推测原因。
【真实事实】{rule_text}
【可用字段白名单】{allowed}
【Top明细】{top_txt}
【用户要求】{user_hint}
只输出结论正文（不超过80字），不要解释、不要JSON。
```
> 这是执行链里**唯一一处带强约束的 LLM 使用**（先规则算真实事实，再 LLM 润色，且 `action_executor.py:695-707` 做 anti-hallucination 校验：白名单外字段名/事实外数字一律丢弃）。质量好，但只服务于「追加结论」这一种动作。

---

## 4. 用户能感知的「弱」具体在哪几环

### 弱环 1：上下文零历史注入（最致命）★ `chat.py:533-542`
context 只构建 `dataset_info.field_profiles` + `current_config`，**完全没有上一轮 user/assistant 消息**。
→ 表现：「承接上一句」完全失效。
→ 实据（离线探针，规则已隔离 LLM）：
```
上轮: 用户'把饼图改成柱图' → 执行成功
本轮: 用户'再来一个'
  intent=unknown conf=0 confident=False by=rule actions=[]
  → 走 LLM 闲聊，但 context 无上一句 → LLM 无法承接
```
「再加一张」「再来一个」「另一个维度」全部落 UNKNOWN。

### 弱环 2：意图是「关键词命中即判」，无语义理解 ★ `intent_classifier.py:206`
只要消息含「换/改/新增/删除/筛选/为什么/标题/修复」等词即命中，命中后 LLM 完全不参与。
→ 表现：用户说「分析一下担保代偿风险」「怎么看逾期趋势」——这类**没有动作动词**的语义化请求，规则全不命中 → UNKNOWN → 走 LLM 闲聊，但 LLM 只是客服回答，**不执行任何数据分析动作**，也不出图。
→ 实据（探针）：
```
['分析一下担保代偿风险']  intent=unknown conf=0 confident=False actions=[]
['怎么看逾期趋势']        intent=unknown conf=0 confident=False actions=[]
```

### 弱环 3：纠正后不记忆（D4 未落地）★ `intent_classifier.py:143-145` 仅 ADD_CHART 规则纠正
「不是 A 是 B」「我指的是…」只在 ADD_CHART 泛指新增里被规则正则识别（`intent_classifier.py:142-145`），且**不写回任何记忆**。change_chart 的纠正靠 `title_keyword` 定位，没有「记住上次改了哪张图」。
→ 表现：用户纠正一次后，下一轮仍是全新正则分类，无法"学会"用户偏好。

### 弱环 4：澄清循环断链（B3 半成品）★ `action_planner.py:195-202` + `chat.py:767`
`plan_actions` 能产出单轮 `clarify` 动作（如「字段不存在」「图型模糊」），这是好的。但用户回复澄清答案（如「用华东地区」）时，下一轮 `message` 独立 `classify_intent`，context 里**没有上一轮的 clarify 状态**，大概率 UNKNOWN → 不承接。
→ 表现：澄清是"一次性抛出问题"，多轮对话立刻断链。实据：「换成更好的图」→ `actions=['clarify']`（单轮有效），但回答「那就折线图」时新轮无状态记忆。

### 弱环 5：回复是硬编码话术，机器人腔 ★ `chat.py:110-202`
规则命中后取模板字典：`"好的，我将把图表改为柱状图。"` / `"正在为您删除图表..."`。完全无自然语言能力，用户明显感到"不是 AI 在对话"。

### 弱环 6：归因/分析类意图不真分析 ★ `intent_classifier.py:164-170` + `chat.py` ATTRIBUTION 分支
`attribution`（为什么下降/异常原因）命中后，动作仅返回「追溯血缘」提示 + `requires_lineage=True`，**不基于数据真算归因结论**（除非用户显式触发 add_conclusion 且能取到真实事实）。用户问"为什么逾期上升"，得到的是"我去追溯血缘"的套话，而非"华东地区逾期环比 +37%"这类结论。

---

## 5. 第 8 层对照表（依据 `PROJECT_STATUS.md:150-203`）

| 第8层项 | 定义 | 当前实现状态 | 证据 |
|---|---|---|---|
| **A1** 原始材料完整注入 | 注入完整上下文 | ⚠️ 部分 | 仅注入 field_profiles+current_config；无清洗记录/血缘/历史 `chat.py:533-542` |
| **A2** 结构化上下文 | 上下文结构化 | ✅ 有 | `dataset_info`/`current_config` 结构存在 |
| **A3** 血缘+加工规则+清洗记录注入 | 注入血缘 | ❌ 未注入 | 对话 context 无 lineage/clean 信息 |
| **A4** 字段语义库 | 注入语义 | ❌ 未注入 | build_semantics 未被对话链路调用 |
| **B1** 自主推理 | LLM 推理意图 | ❌ 未实现 | 意图靠正则 `intent_classifier.py:206` |
| **B2** 证据链推理 | 推理溯源 | ❌ 未实现 | — |
| **B3** 澄清循环 | 多轮澄清承接 | ⚠️ 单轮 | 单轮 clarify 产出 `action_planner.py:195`；无多轮承接 `chat.py:767` |
| **B4** 有异议追溯源头 | 异议溯源 | ❌ 未实现 | — |
| **C1** 推理结果落库 | 落库 | ⚠️ 部分 | ChatMessage 存 action_type/params（动作记录，非推理） |
| **C2** 分析模板沉淀 | 模板沉淀 | ❌ 待做 | 即本批指令①要补的 2.6 三件 |
| **C3** 结果自检 | 输出自检 | ⚠️ 部分 | add_conclusion anti-hallucination `action_executor.py:695-707` |
| **C4** 用户纠正流程 | 纠正写回 | ⚠️ 半成品 | 仅 ADD_CHART 规则纠正 `intent_classifier.py:143`；不写回记忆 |
| **D1–D7** 记忆层 | 推理/决策/动作/纠正记录+模型切换承接 | ❌ 全未落地 | context 无 history；无 ai_action_log 消费；无纠正记录 |
| **E1–E4** 约束层 | 超时/预算/降级/中断 | ⚠️ 部分 | LLM 超时 40s、失败交还用户 `chat.py:720-729` |
| **F1–F4** 体验层 | 预估/恢复/通知/AI区分 | ⚠️ 部分 | F4 有 classified_by 区分 AI/规则 |
| **G1–G6** 模型分层 | 强/快/弱路由 | ⚠️ 部分 | 有 LLM 兜底/提取，但无"意图理解"分层路由 |
| **H1–H2** 验证机制 | 评估基准 | ❌ 未实现 | 无通过率追踪 |

**一句话**：第 8 层中 A 输入层/B 处理层/D 记忆层 三项核心（用户感知"AI 含量"的来源）几乎全空；C 输出层、E 约束层、F 体验层、G 模型层只有零散实现。

---

## 6. 修复优先级 Top3（最能提升对话质量）

### 🥇 P0-1：注入对话历史上下文 + 纠正记忆（补 A1/A2 + D 层）
- **改哪**：`chat.py:533-542` 构建 context 时，从 `ChatMessage` 表读最近 N 轮（user/assistant/action）拼入 `context["history"]`；并在执行成功后把「本次改了哪张图/选了哪个字段/口径」写入会话级记忆。
- **效果**：直接修复弱环 1/3/4——「再来一个」「那就折线图」「用华东」都能承接上一句；纠正可记忆。
- **工作量**：中（context 加字段 + 取历史查询 + 执行器读记忆）。

### 🥈 P0-2：把「主执行链路」交给 LLM 决策（补 B1 自主推理）
- **改哪**：新增 `IntentType.SEMANTIC_ACTION` 或复用 `UNKNOWN`：当命中"需要改看板/分析"语义时，调一次 LLM，让其基于 `context`（含 history+字段画像）直接产出**结构化动作 JSON**（图型/维度/指标/口径/筛选），代码只做校验+执行（`action_executor` 不变）。
- **效果**：修复弱环 2/5/6——「分析担保代偿风险」「为什么逾期上升」这类语义请求，AI 能真正理解并出图/出结论，而非"引导用具体指令"的套话。
- **工作量**：中（新增一个 LLM 决策节点 + JSON 校验 + 失败降级回规则）。

### 🥉 P0-3：真正的澄清循环承接（补 B3）
- **改哪**：`plan_actions` 产出 `clarify` 时，把「待澄清状态+已澄清部分」写入 session context（`chat.py:533` 的 context 增加 `pending_clarify`）；下一轮 `classify_intent` 前先合并 pending_clarify，使「华东」「折线图」等答复能补进上轮未完成的动作。
- **效果**：修复弱环 4——澄清不再是一次性抛问题，而是多轮闭环。
- **工作量**：小-中（clarify 状态机 + 下一轮合并）。

> 三者可叠加：P0-1 是地基（记忆），P0-2 是大脑（自主推理），P0-3 是闭环（澄清承接）。做完这 3 项，用户感知的「AI 含量」才会从 ~5% 跃升到「真能对话」的层次。

---

## 7. 附录：离线探针输出（实据，LLM 已隔离）

```
=== 单轮意图/规划（规则优先，LLM 已隔离）===
['把饼图改成柱图']      intent=change_chart conf=90 confident=True by=rule actions=['change_chart']
['新增一个趋势图']      intent=add_chart    conf=75 confident=True by=rule actions=['add_chart']
['分析一下担保代偿风险'] intent=unknown      conf=0  confident=False by=rule actions=[]
['怎么看逾期趋势']      intent=unknown      conf=0  confident=False by=rule actions=[]
['换成更好的图']        intent=change_chart conf=75 confident=True by=rule actions=['clarify']
['用华东地区筛选一下']  intent=filter_drill conf=75 confident=True by=rule actions=['filter_drill']
['再来一个']            intent=unknown      conf=0  confident=False by=rule actions=[]
['再加一张']            intent=unknown      conf=0  confident=False by=rule actions=[]

=== 多轮"承接上一句"模拟（context 不注入历史）===
上轮: 用户'把饼图改成柱图' -> 已执行成功
本轮: 用户'再来一个' -> actions=[]，is_confident=False -> 走 LLM 闲聊，context 无上一句 -> 无法承接
```

> 探针方法：纯函数离线调用 `classify_intent`/`plan_actions`，`mock` 隔离 `_llm_classify` 网络调用，不修改任何项目代码、不触发网络。
