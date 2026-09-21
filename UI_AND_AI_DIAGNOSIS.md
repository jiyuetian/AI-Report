# UI_AND_AI_DIAGNOSIS.md — 四个 UI + AI 问题诊断（仅诊断，不写代码）

> 诊断日期：2026-09-21
> 仓库：`C:/Users/Asus009/Desktop/临时/ai大赛/AI-Report`
> 复现环境：测试看板 `risk_demo_v2_05_合规月度表看板`（事件日志 `dashboard_id = dash_cb0a9738_8100bb`，session `4ffede4b-455d-4346-a04c-90a139dd6384`）
> 纪律：仅读代码+查日志，未改任何文件；未碰生产库 / `.env`。

---

## 0. 铁证：生产事件日志与后端日志已真实复现

**前端事件日志** `backend/logs/events/user_events_202609.jsonl`（同 session，2026-09-21 上午）：

```
315: "我想要顶部的汇总看板加上每个合规率的平均值汇总"
     → intent_type=add_chart, feasible=true, confidence=82
316: "我想要顶部的汇总看板加上每个：业务流程合规率，抵押登记合规率，档案管理合规率，
       制度执行到位率，内部审计问题整改率的平均值汇总"
     → intent_type=unknown, feasible=true, confidence=0
317: (同上 5 字段名消息，另一次)
     → intent_type=add_chart, confidence=85
```

**后端运行日志** `backend/_start.log`（历史多次）：
```
[Brain] S3完成: 6个图表, source=rule_engine
[Brain] S3完成: 5个图表, source=rule_engine
```
→ 系统内部**明确知道 AI 没参与**，但前端/用户无感。

---

## 1. 问题 1（最严重）：生成看板时 AI 限流，系统静默兜底

### 1.1 brain/run 跑的是什么生成流程
- 入口：`backend/app/api/brain_run_sse.py` `POST /brain/run`（`brain_run`，`:1218-1279`）→ 质检门禁后丢后台 `asyncio.create_task(_run_worker(...))`，立即返回 `run_id`，前端轮询 `/brain/run/{run_id}/status`。
- 管线 `brain_run_pipeline`（`:486-1163`），五阶段 S1→S5：
  - **S3 图表推荐（`:715-831`）是 AI 参与的关键阶段**，调用 `generate_charts_with_llm(...)`（`:749`）。
  - 落库（`:1015-1118`）：构造 `Dashboard` 对象 + `dashboard_config` JSON，写入 `Dashboard.config`，`status="published"`。
- AI 是否参与由 S3 的 `generated_by` 决定。

### 1.2 M1 弹窗触发条件（对话 vs 生成，关键差异）
**对话修改路径（必然弹窗）** — `backend/app/api/chat.py`：
- 当 `generate_llm_natural_response` 返回 `ok=False`，后端**无条件**构造 `ai_error`（`:717-736`）带 `options:["retry","rule_fallback"]`，并在 `complete` SSE 事件一并下发（`:859`）。
- 前端 `ChatPanel.tsx:463-494` 读到 `msg.ai_error` 后**无条件渲染红色 Alert + "重试 AI / 改用规则引导回复"按钮** = 用户看到的 M1 弹窗。
- 结论：**只要 AI 失败就弹窗，与是否在页面/是否轮询无关。**

**生成看板路径（弹窗有条件且脆弱）** — `brain_run_sse.py`：
- 弹窗只通过 `_request_user_choice`（`:173-200`）触发，仅在两个分支被调用：
  1. 入口探针 `llm_offline=True`（`:566,591`）；
  2. S3 **非超时类** AI 失败且 `llm_offline=False`（`:783-805`）。
- **静默分支（根因）**：S3 的 LLM 调用**超时**（限流最典型的"挂起"表现）→ `except asyncio.TimeoutError`（`:759-773`）直接规则兜底并 `llm_offline=True`，**此处从不调用 `_request_user_choice`**；而 `:794` 的 `if not llm_offline` 因 `llm_offline=True` 为假 → 弹窗被跳过。
- 即便走"会弹窗"的分支（2），弹窗也**只在用户停在 LoadingPage 且 2.5s 轮询命中 `ai_awaiting` 时**才显示（`LoadingPage.tsx:152,425-455`）。用户点"跳过等待直接查看看板"（`:413`）或关页面即看不到；超时（`BRAIN_AI_CHOICE_TIMEOUT` 默认 120s）后自动 `rule_fallback`。

**结论**：对话路径是"AI 失败→必然弹窗"；生成路径是"AI 失败→多数静默（超时分支根本不弹，非超时分支还要人停在 LoadingPage 才弹）"。限流最常被归入 **S3 超时静默兜底**分支，故用户"没有任何弹窗"。

### 1.3 `risk_demo_v2_05` 当前 config 里这些字段是什么
- `generation_mode` / `ai_participated` 只在 **SSE 完成事件 `detail`** 里临时计算（`brain_run_sse.py:1153-1157`）：
  ```python
  "ai_participated": generated_by == "llm",
  "generation_mode": "ai" if generated_by == "llm" else "rule",
  ```
- DB 模型 `Dashboard`（`models/dashboard.py:12-55`）**无专用列**，只有 `config` JSON 大字段（`:34`）。
- **真正落库的 `dashboard_config`（`:1082-1099`）只写了 `generated_by`（`:1087`），没有 `generation_mode` / `ai_participated`**。
- 当 AI 限流走规则兜底，`generated_by` 写成 `"rule_engine"`（或 `"rule_engine_fallback"` / `"rule_engine_v2"`，见 `s3_chart_engine.py:489`、`s3_chart_engine_v2.py:702`）。
- **即：打开该看板时，config 里只有 `generated_by:"rule_engine"`，根本没有 `generation_mode`/`ai_participated` 两个 key 可供显示。**

### 1.4 后端日志里有没有"AI 限流 / llm_offline / rule_engine"记录
**有，但都是 `print` 且仅服务端可见，未透传前端/用户**：
- `brain_run_sse.py:565` `[Brain] LLM 不可达({reason})：暂停并询问用户`
- `:735` `[Brain] LLM 不可达：S3 直接走规则引擎兜底，不调用 AI、不询问用户`
- `:762` `[Brain] S3 LLM 调用超时(...)按规则引擎兜底`
- `s3_llm_enhancer.py:473` `[S3-LLM] LLM生成失败，降级到规则引擎`
- `_start.log` 多次 `[Brain] S3完成: N个图表, source=rule_engine`
→ **系统知道 AI 挂了，但：①超时分支把 `llm_offline` 藏起不弹窗；②标注字段不落库；③print 日志不推前端。**

### 1.5 前端绿标/灰标显示逻辑
- **生成中（LoadingPage）——有实现，但只在生成当次**：`LoadingPage.tsx:113-119,384-390` 按 `detail.generation_mode` 渲染 `<Tag color="green">AI 生成</Tag>` / `<Tag color="default">本次为规则生成</Tag>`。来自 `/status` 轮询拿到的 SSE `detail`，**仅在 LoadingPage 存活期间可见**。
- **打开看板（DashboardPage）——完全没有该逻辑（根因之三）**：`DashboardPage.tsx` 加载看板 `http.get('/dashboards/{id}')`→`setConfig(config)`（`:509-515`），全文件**无任何 `generation_mode`/`ai_participated`/`generated_by`/绿色/灰色/Badge 渲染分支**（仅有的 Badge 是 KPI 预警角标与聊天气泡角色角标）。即：打开看板后前端**读 config 但不渲染生成方式徽标**。
- **"什么都没显示"是双重失效**：①后端没把 `generation_mode`/`ai_participated` 写进 config；②即便写了，`DashboardPage.tsx` 也没渲染。

### 1.6 根因（三层叠加）
1. **生成时静默兜底（核心）**：`brain_run_sse.py:759-773` 超时分支规则兜底且不弹窗。
2. **标注字段未落库**：`generation_mode`/`ai_participated` 仅瞬时 SSE `detail` 计算，未写入 `Dashboard.config`。
3. **打开页前端不渲染徽标**：`DashboardPage.tsx` 无读取/渲染生成方式徽标逻辑。

### 1.7 为什么"对话修改"弹窗而"生成看板"不弹窗（一句话）
对话路径把任何 `ok=False` 包成 `ai_error` **必然下发**→前端**必然** Alert；生成路径的 M1 弹窗**只在 S3 非超时失败且用户停在 LoadingPage** 才出现，而限流最常被归为"**S3 超时**"这一**根本不弹窗**的分支。

### 1.8 修复方向（仅定位，不改动）
- **消除静默**：`brain_run_sse.py:759-773` 的 `except asyncio.TimeoutError` 分支也触发 `_request_user_choice`（或至少把 `ai_awaiting` 推前端）。
- **标注字段落库**：把 `generation_mode` 与 `ai_participated` 写入 `Dashboard.config`（与 `generated_by` 并列，`:1087` 附近）；DB 模型加专用列便于查询。
- **打开页渲染徽标**：`DashboardPage.tsx` 读取 `config.generation_mode`/`ai_participated`/`generated_by` 渲染绿/灰标，对齐 LoadingPage 已有的 `<Tag>` 逻辑（`:113-119`）。
- 改动量：中（3 处，后端 2 + 前端 1），风险低。

---

## 2. 问题 2：对话修改把多字段截断成单字段，且真实字段名仍"匹配不到"

### 2.1 为什么"每个：业务流程合规率"被截断成单字段
- 分句正则 `action_planner.py:19-21` `_SPLIT_PATTERN` 按 `，,；;、` 切（**全角冒号"："不在分隔符内**）。
- `split_clauses`（`:54-71`）把原消息在 5 个 `，` 处切成 5 子句：
  - 子句A：`...加上每个：业务流程合规率`（唯一带"加上"动词）
  - 子句B~E：`抵押登记合规率` / `档案管理合规率` / `制度执行到位率` / `内部审计问题整改率的平均值汇总`（裸字段名）
- `action_planner.py:240-248` 逐子句分类，未知/低置信子句直接丢进 `unparsed` 并 `continue`：**子句B~E 无动词 → 全被丢弃 → 5 字段→1 动作**，4 个字段结构性丢失。
- **`explicit_field_tokens`（`:84-112`，触发词 `:44-50`）**：字段触发词只有 `按/把/《》/（）`，**"每个：XXX" 不匹配** → 返回 `[]` → 反幻觉字段校验（`:259-273`）被跳过，既不校验也不提取。

### 2.2 为什么给了真实字段名还"匹配不到"
- **`_match_field`（`intent_classifier.py:582-602`）其实能匹配**：`nm in cand`（"业务流程合规率" ⊂ "每个：业务流程合规率"）子串命中即可解析出真实字段。**匹配器没问题，是"通往它的路"被切断。**
- **规则必然 miss**：子句A 无图表类型词（"图/饼图/柱图"）、"合规率"不在 `金额/数量` 关键词 → 所有 `INTENT_PATTERNS` 正则不中 → 进入 `_llm_classify` 兜底（`intent_classifier.py:196-207`）。
- **`_llm_classify`（`:210-258`）绕过所有字段解析**：直接 `analysis = data.get("analysis", {})` 采用 LLM 原始 JSON，**从不调用 `_extract_params`/`_match_field`**。字段能否解析完全取决于 LLM 吐出的 key 形状，与"用户给的是否真实字段名"无关。
- **执行器硬校验** `action_executor.py:300-304`：只认 `dimension_field/metric_field/value_field/y_field` 固定 key；LLM 若只回 `{chart_type:"bar"}` → 命中守卫 → 报"未能从数据中匹配到您提到的字段"。
- **非确定性实证**：同一条 5 字段消息既跑出 `unknown/0`（日志 316）也跑出 `add_chart/85`（317）——LLM 兜底不稳定，截图里的失败属 `add_chart` 执行路径报错。

### 2.3 影响面
**非常普遍，非边缘 case**。满足其一即触发：
1. 多字段逗号列举（"A，B，C 的平均值"）→ `split_clauses` 拆散丢字段；
2. 带"每个/所有/各"且无图表类型词；
3. 不用《》框字段、不点名图型、不出现 金额/数量 等关键词 → 规则必不中 → 必走 LLM 兜底 → 字段匹配被绕过。
结构化多图提取 `_extract_add_charts`（`:339-382`）被锁在"规则路径+图表类型词"之后，任何"用自然语言描述要什么指标但不说图型"的自由表述都进不去正确路径——基本涵盖业务人员最自然的说话方式。

### 2.4 修复方向（仅定位，不改动）
- **A 截断修复（action_planner.py）**：`split_clauses`（`:54`）在"加上/新增 + 每个/所有/各 + 字段列举"聚合句式内**不按逗号切**；或切完把"裸字段子句"回并到上一带动词子句；或上游把"X、Y、Z 的平均值"识别为**单条聚合动作**。改动量：中（需回归"删A并新增B"等复合指令，防误伤）。
- **B 真实字段匹配（intent_classifier.py）**：`_llm_classify`（`:210`）拿到 `analysis` 后**仍走一遍 `_extract_params`/字段规范化**，用 `_match_field` 把候选名 canonicalize 成真实字段并尽量组装 `charts` spec；让 `add_chart` 始终经 `_match_field`（当前仅规则路径走）；`explicit_field_tokens`（`:84`）增补 `每个/所有/各 + 冒号` 触发模式。
- **C 执行器更宽容（action_executor.py）**：`_execute_add_chart`（`:259`）`else` 分支除固定 key 外也接受 `metric_name`/`title` 并回退 `_match_field`；失败时不只报"匹配不到"，结合已有 `field_not_found` clarify（`:259-273`）**给出候选字段让用户选**。
- 改动量：中（A 需复合指令回归测试，风险点在此）。

---

## 3. 问题 3：KPI 卡片右侧空白

### 3.1 根因
- 组件 `frontend/src/views/dashboard/DashboardPage.tsx`，`renderKPILayer()`（`:1057-1076`）：
  ```tsx
  <Row gutter={[16,16]}>
    {kpiCharts.map((chart, index) => (
      <Col xs={24} sm={12} lg={6} key={`kpi-${index}`}>   // ★ 写死列宽
        <KPICard .../>
      </Col>
    ))}
  </Row>
  ```
- `lg={6}` 写死 = 桌面占 **1/4（25%）**，`sm={12}` = 平板 **1/2（50%）**；CSS `.kpi-layer`（DashboardPage.css:157-166）无 `flex/grid/justify` 撑满逻辑。
- **根因 = 卡片数量与栅格列宽解耦**：列宽按"最多 4 张一行"写死，看板只有 1 张 KPI（如"内审整改率汇总"）时桌面只占 25%、平板占 50%，右侧固定空白。**判定：bug（写死列宽，未随卡片数自适应），非设计。**

### 3.2 单一 KPI 时是否难看
**难看且明显**：顶部汇总区本应一行一张大卡或至少占满，实际只剩左侧 1/4~1/2 一张孤卡、右侧大片空地，信息层级被破坏。

### 3.3 修复方向（改同一处 `DashboardPage.tsx:1069`）
1. **（推荐，最小改动）响应式自适应 span**：`lg`/`sm` 按 `kpiCharts.length` 计算——1→`24`、2→`12`、3→`8`、≥4→`6`。
2. **CSS Grid `auto-fit`**：`.kpi-layer` 改 `display:grid; grid-template-columns: repeat(auto-fit, minmax(240px,1fr))`，`Row/Col` 换普通 `div`。
3. **`flex:1` 占满**：保留 flex 行，给 `Col/Card` 设 `flex:1; min-width:240px`。

---

## 4. 问题 4：附录表格右侧留白

### 4.1 三表位置与列宽
组件 `frontend/src/components/appendix/AppendixPanel.tsx`（A/B/C 同 `Tabs` 组件树，非后端生成 HTML）。

| 表 | 列 `width`（写死 px） | 弹性列（无 width） | `scroll.x` |
|---|---|---|---|
| A 字段字典（`:91-113`，scroll `:112`） | 90/90/100/180（合 460） | 字段名 | `'max-content'` |
| B 清洗质检（`:119-150`，scroll `:122`） | 60/90/120/130/160/100（合 660） | 说明（长文本） | `'max-content'` |
| C 指标明细（`:155-188`，scroll `:157`） | 200/80/100（合 380） | 计算口径（公式） | `'max-content'` |

### 4.2 根因
AntD 规则：**一旦设 `scroll.x`（含 `'max-content'`），表格切 `table-layout:fixed`，`<table>` 宽=内容最大宽之和，不拉伸到容器 100%**；无 `width` 的弹性列只按内容算，不吸收剩余空间。容器可用宽典型 **900~1400px**：A 内容≈560px、C≈580~780px ≪ 900 → 右侧留白 ❌；B 内容≈660+长"说明"≈860px+ ≥ 容器 → 恰好撑满 ✅。**差异不在 scroll/width 写法（三表一模一样），而在"列数+弹性列文本量"**，B 被内容自然撑满，A/C 内容不够宽而留白，是偶然结果。

### 4.3 修复方向（只改 `AppendixPanel.tsx`）
1. **（推荐，最省事）去掉三表 `scroll.x:'max-content'`** → 回到 `table-layout:auto` + 100% 宽，弹性列自动吸满右侧：
   - A：`:112` `scroll={{ x:'max-content', y:360 }}` → `scroll={{ y:360 }}`
   - B：`:122` `scroll={{ x:'max-content' }}` → `scroll={{}}` 或删
   - C：`:157` 同上
2. **（可选）写死 px 列宽改百分比**（需配合"去掉 scroll.x"才生效）。
3. **不推荐**：把 `scroll.x` 设成大于容器的固定值"骗"弹性列吸空白——折叠聊天栏（`DashboardPage.css:53` `padding-right` 由 436px 变 24px）下很脆弱。

---

## 5. 优先级与路演影响

| 优先级 | 问题 | 路演影响 | 修复量 | 建议时机 |
|---|---|---|---|---|
| **P0（先修）** | **问题 1 限流静默兜底** | ★★★★★ 必现、信任杀手（日志 315/316 + `_start.log` rule_engine 实锤）；用户以为"AI 正常生成"实则规则兜底，且打开无绿/灰标 | 中（后端 2+前端 1） | **路演前必修** |
| **P0（先修）** | **问题 2 多字段截断+匹配失败** | ★★★★★ 同 session 日志 316/317 实锤；自由表述必触发，演示"下指令改图"必然翻车 | 中（A 需回归测试） | **路演前必修** |
| P1 | 问题 3 KPI 卡片空白 | ★★★ 顶部汇总区像错位 | 小 | 与问题 1/2 同批 |
| P2 | 问题 4 附录表格留白 | ★★ 仅附录 Tab，非主屏 | 极小 | 可稍后，成本低建议顺手 |

**先修顺序**：① 问题 1（消除静默+落库+打开页渲染徽标）② 问题 2（截断+LLM 路径字段解析+执行器容错）③ 问题 3 ④ 问题 4。
理由：问题 1/2 是唯一"功能级崩 + 演示必现"且已有生产日志实锤；问题 3 同属主屏观感、成本低，一起收口；问题 4 仅在附录 Tab、影响最小。

---

## 6. UI 修复验收要求（强制）

> **所有 UI 修复（问题 3/4）验收必须附视觉截图，不能只 `tsc --noEmit` 通过就视为完成。**

- 每个 UI 修复提交前，需在同一测试看板 `risk_demo_v2_05_合规月度表看板` 下截图对比：
  - 问题 3：看板仅 1 个 KPI 时，卡片应占满整行（无右侧空白）。
  - 问题 4：A/C 两表应撑满容器宽度（无右侧留白），B 表保持原样。
- 截图需覆盖"单 KPI / 多 KPI""窄屏(≤768px) / 宽屏"两种断面。
- `tsc` 仅作类型门禁，不替代视觉验收。
- 问题 1/2（AI 行为）验收需附：**后端日志片段**（证明 `generation_mode` 落库 / 字段解析成功）+ **前端弹窗/绿灰标截图**。

---

## 7. 本次未做 / 不碰

- 未改任何源文件、未跑任何写操作；未碰生产库与 `.env`。
- 问题 1/2 仅给方案与文件定位，待下一步排期实现。
- 残留根因已定位：①生成路径 S3 超时静默兜底（brain_run_sse.py:759-773）；②标注字段不落库（:1082-1099 仅写 generated_by）；③打开页前端不渲染徽标（DashboardPage.tsx 无逻辑）；④对话字段解析被 LLM 兜底路径绕过（intent_classifier.py:210-258 不调用 _extract_params）；⑤分句截断丢字段（action_planner.py:54）。
