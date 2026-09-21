# 方案 O · AI 参与过程监控（★ 核心）

> 目标：把"这个看板 AI 参没参与"这个**布尔值**，升级为一条**可回放、可对账、可解释的 AI 参与时间轴**。
> 评委问"你怎么证明是 AI 干的"时，现在只能亮一个绿标；本方案之后可以放出完整证据链。

---

## 一、现状（全部已核实，附证据）

### 1.1 已有的东西（别重复造）

| 能力 | 位置 | 状态 |
|---|---|---|
| 一次生成的贯穿 ID | `brain_run_sse.py:1260` `run_id = str(uuid.uuid4())` | ✅ 有 |
| 五阶段 trace 落库 | `models/brain.py` `brain_traces` 表，含 `stage_input/stage_output/stage_metrics/error_info` | ✅ 表有 |
| trace 写入调用 | `brain_run_sse.py:649/703/784/863/890` `complete_stage(db, trace_id, {...})` | ⚠️ 写了，但**只传 output** |
| 参与标记（看板级） | `:1095` `ai_participated = (generated_by=="llm") or (s2_gen=="llm")` → `:1107` 落 config | ✅ 有 |
| 参与标记（目标级） | `s2_goal_generator.py:268` 每个 goal 带 `generated_by` | ✅ 有 |
| 降级原因码 | `llm_gateway.py:517` `fallback_used=True`；`brain_run_sse.py:561` `llm_offline`；`:766` `asyncio.TimeoutError` | ⚠️ 散落，未统一 |

### 1.2 缺的东西（这才是方案要解决的）

| # | 缺口 | 证据 | 后果 |
|---|---|---|---|
| G1 | **LLM 调用零落库**：无 `llm_calls` / `prompt_logs` 表 | 现有 27 张表全列出来，无一张记录 LLM 调用 | 无法回答"调了几次、什么模型、多少 token、花了多久" |
| G2 | **`run_id` 没下沉到 LLM 调用** | `llm_gateway.py:118` `request_id: str = ""`，`:352` `request_id = request.request_id or str(int(time.time()*1000))` —— 调用方不传就退化成时间戳 | 无法把一次 LLM 调用回溯到某次生成 |
| G3 | **`stage_metrics` 恒为空** | 5 处 `complete_stage` 全部只传 3 个参数，没有 metrics | 表设计了却没用，耗时/token 无处可查 |
| G4 | **无结构化日志** | 全仓 `backend/app` 无 `logging.getLogger`，全是 `print()` | 出问题只能翻 stdout |
| G5 | **SSE 不带"当前是否 AI 在算"** | `StageProgress.to_event`（`:319-331`）字段为 run_id/stage/status/progress/message/detail；`detail` 只在 S3 完成时才带 `generated_by` | 前端过程页只能显示"第 3 步 60%"，说不清是谁在算 |
| G6 | **前端不用 SSE，是轮询** | `LoadingPage.tsx:164` 轮询 `/status` | 事件粒度信息本来就传不过来 |
| G7 | **降级原因没统一编码** | `llm_offline`/`TimeoutError`/`rule_engine_fallback`/`TokenBudget` 各处自己 print | 无法统计"这次为什么没用上 AI" |
| G8 | **图级别无来源标记** | `s3_llm_enhancer.py:465` 的 `generated_by` 是**整个 charts[] 批次**一个字段 | 无法说"这张图是 AI 选的、那张是规则兜的" |

**一句话**：可追溯性止于「看板级 + 目标级」，**调用级、步骤级、图级全部缺失**。

---

## 二、方案设计：四层监控

```
┌─ L4 展示层：AI 参与时间轴面板（过程页 + 看板详情抽屉）
├─ L3 推送层：/status 增加 ai_active + llm_call 摘要
├─ L2 链路层：stage_metrics 真正写入 + 统一降级原因码
└─ L1 埋点层：llm_chat 透传 run_id/stage，落 llm_calls 表
```

### L1 · 埋点层（最关键，其他三层都依赖它）

**1.1 新表 `llm_calls`**

```python
class LLMCall(Base):
    __tablename__ = "llm_calls"
    id            = Column(String(36), primary_key=True)
    run_id        = Column(String(36), index=True)   # 可空：对话/质检场景没有 run
    dataset_id    = Column(String(36), index=True)
    stage         = Column(String(20))               # S1/S2/S3/S4b/CHAT/QC/REPORT
    provider      = Column(String(30))               # 哪个 provider
    model         = Column(String(60))               # 实际用的模型
    prompt_key    = Column(String(60))               # 用的是哪个 prompt 模板（s3_llm_main…）
    prompt_chars  = Column(Integer)                  # prompt 长度
    prompt_digest = Column(Text)                     # 摘要：前 200 字 + 变量名列表（默认）
    prompt_full   = Column(Text, nullable=True)      # 全量（开关开启时才写）
    response_digest= Column(Text)
    tokens_in / tokens_out = Column(Integer)
    latency_ms    = Column(Integer)
    attempt       = Column(Integer)                  # 第几次尝试（自愈重试）
    success       = Column(Boolean)
    fallback_used = Column(Boolean)
    error_code    = Column(String(40))               # 统一降级原因码
    error_message = Column(Text)
    created_at    = Column(DateTime)
```

**1.2 `llm_chat` 增加上下文参数（向后兼容）**

```python
async def llm_chat(
    messages, ..., 
    run_id: str = "",        # 新增
    stage: str = "",         # 新增
    prompt_key: str = "",    # 新增
    log_full_prompt: bool = False,   # 新增，默认关
)
```
- 不传的调用点行为**完全不变**（默认空值），现有 8+ 个调用点零改动可跑
- 传了的调用点才有 trace —— 这样改造可以分批推进

**1.2b 新表怎么建（已核实，消除落地不确定性）**

| 机制 | 位置 | 说明 |
|---|---|---|
| Alembic | `backend/alembic/versions/001_init_tables.py` | **只有 1 个迁移**（001），即 alembic 目前不是高频演进的主路径 |
| 启动时建表 | `main.py:122` `await conn.run_sync(Base.metadata.create_all)` | 新增 Model 会在启动时自动建表 |
| 初始化脚本 | `init_brain_tables.py:31` 同样 create_all | brain 相关表的初始化 |

→ **结论**：新增 `llm_calls` 只需 ① 写好 Model ② 启动即自动建表（SQLite 场景）。
**建议同步补一个 `002_add_llm_calls.py` 迁移**，原因：让 `alembic upgrade head` 能复现表结构，
避免"本地靠 create_all、部署靠 alembic"两套不一致 —— 这类不一致在演示环境最容易翻车。

**1.3 落库必须"永不阻塞主链路"**

复用现有 `_safe_trace` 思路（`brain_run_sse.py` 已有该模式）：写库失败只 print，不抛异常。
**监控本身把生成搞挂是最糟的结果。**

### L2 · 链路层

**2.1 `complete_stage` 真正传 metrics**

现有签名 `complete_stage(db, trace_id, output)` → 增加可选 `metrics=None`。
五处调用点补上：

| 阶段 | metrics 内容 |
|---|---|
| S1 | `{"llm_called": bool, "dict_hit_score": float, "latency_ms": int}` |
| S2 | `{"goals_count": n, "generated_by": "llm"/"rule", "llm_called": bool, "latency_ms": int}` |
| S3 | `{"charts_count": n, "generated_by": ..., "retry_count": int, "validator_errors": [...], "latency_ms": int}` |
| S4/S5 | `{"coverage_score": float, "kpi_count": n, "final_score": float}` |

**2.2 统一降级原因码（这是 G7 的收口）**

```python
class FallbackReason:
    LLM_OFFLINE        = "llm_offline"         # 入口探测不可达
    LLM_TIMEOUT        = "llm_timeout"         # 单阶段超时
    SCHEMA_INVALID     = "schema_invalid"      # jsonschema 校验失败且重试耗尽
    PROVIDER_ERROR     = "provider_error"      # provider 返回错误（401/429…）
    BUDGET_EXCEEDED    = "budget_exceeded"     # Token 预算熔断，跳过 S4b
    EMPTY_OUTPUT       = "empty_output"        # LLM 返回空/不可解析
    DICT_HIT           = "dict_hit"            # 词典命中，主动不调 LLM（不是故障！）
```

**关键：区分「故障降级」与「主动不调 LLM」。**
`DICT_HIT`（S1 词典相似度 ≥0.8 就不调 LLM，`s1_theme_detector.py:238`）是**优化**不是故障，
如果笼统计成"降级"，监控面板会把正常优化显示成失败 —— 这属于新的失真。

### L3 · 推送层

`/status` 与 SSE 事件增加两个字段（`:319-331` `to_event`、`:1323-1337` `/status`）：

```json
{
  "stage": "S3",
  "ai_active": true,
  "llm_call": {
    "model": "qwen-plus",
    "attempt": 2,
    "elapsed_ms": 8300,
    "stage_desc": "图表推荐（AI 第 2 次尝试）"
  }
}
```
前端过程页即可显示「🤖 AI 正在生成图表配置（第 2 次尝试，已用 8.3s）」，
而不是现在的「第 3 步 60%」。

> 注：前端目前是轮询 `/status`（`LoadingPage.tsx:164`）而非 EventSource。
> 加字段对两种模式都生效，**不需要先改造成 SSE** —— 这样 P0 阶段省一大块工作。

### L4 · 展示层：AI 参与时间轴

在 LoadingPage（生成中）和看板详情抽屉（生成后）各放一份：

```
┌ AI 参与时间轴 ─────────────────────────────┐
│ ✅ S1 主题识别   规则·词典命中      12ms    │  ← 主动不调 LLM
│ 🤖 S2 目标生成   AI·qwen-plus     1.4s     │  ← 绿标
│ 🤖 S3 图表推荐   AI·qwen-plus     8.3s ⚠️重试2次 │
│ ⚪ S4+S5 编排    规则（纯统计）    45ms     │  ← 本来就是规则
│ ⏭️ S4b 分析说明  AI 已跳过（预算不足）      │  ← budget_exceeded
├──────────────────────────────────────────┤
│ 合计：AI 参与 2/5 阶段 · 9.7s · 3 次调用    │
└──────────────────────────────────────────┘
```

每条可展开看：使用的 prompt 模板名、prompt 摘要、输出摘要、token、错误码。

---

## 三、实施步骤与工作量

| 阶段 | 内容 | 依赖 | 估算 |
|---|---|---|---|
| **P0** | 建 `llm_calls` 表 + `llm_chat` 加可选参数 + S2/S3 两个调用点接入 + `stage_metrics` 写入 | 无 | **3~4 h** |
| **P1** | 统一 `FallbackReason` 编码，改造 5 处降级点；S1/S4b/CHAT/QC 调用点接入埋点 | P0 | 2~3 h |
| **P2** | `/status` 加 `ai_active`/`llm_call`；过程页显示"AI 正在算第 N 次" | P0 | 1.5 h |
| **P3** | 时间轴面板（生成中 + 生成后两处） | P0+P1+P2 | 3~4 h |
| **P4** | 图级来源标记（G8，需改 S3 输出结构） | 独立 | 2 h |

**P0 就能拿到 80% 的说服力**：跑完一次生成，数据库里有一次生成调了几次 LLM、什么模型、多久、成功没 —— 这是评委最想看的原始证据。

---

## 四、验收标准（可测，不是感觉）

| # | 断言 | 怎么验 |
|---|---|---|
| V1 | 一次 `brain/run` 结束后，`llm_calls` 有 ≥1 条记录且 `run_id` 与本次一致 | SQL 查 |
| V2 | 5 个阶段的 `brain_traces.stage_metrics` **全部非 NULL** | SQL 查 |
| V3 | 时间轴上"AI 阶段数" == `llm_calls` 中 `success=true` 的 stage 去重数 | 前后端对账 |
| V4 | **断网/停掉 LLM 后重跑** → 所有阶段显示"规则"，且时间轴给出 `llm_offline` 原因码（不许留白、不许谎报 AI 参与） | 手工 |
| V5 | 词典命中场景（S1）显示"规则·词典命中"而非"AI 失败" | 构造高相似度主题 |
| V6 | `llm_calls` 写库异常时，生成流程**照常完成**（埋点永不阻塞主链路） | 注入异常 |

V4/V5 是**诚实性验收**，与本项目 2.1/2.4 的"不谎报"原则一致 —— 监控面板本身不许造假。

---

## 五、风险与对策

| 风险 | 对策 |
|---|---|
| **prompt 含真实业务数据 → 落库泄隐私** | 默认**只存摘要**（前 200 字 + 模板名 + 变量名）；全量落库由环境变量 `LLM_LOG_FULL_PROMPT` 控制，演示/排障时才开 |
| 落库量撑爆库 | `llm_calls` 加 30 天保留策略；`response_digest` 限长 |
| 改造面太大影响稳定性 | `llm_chat` 新参数**全部带默认值**，老调用点零改动；分批接入 |
| token 数是估算值（`llm_gateway.py:163-168` 按 `len/4` 粗估） | 字段命名保持 `tokens_in/out`，但 API 返回里标注 `estimated: true`，**不假装是精确值** |
| 时间轴显示"AI 只参与了 2/5 阶段"反而减分 | 主动区分「AI 适用阶段」与「本就规则阶段」：S4+S5 是纯统计编排，用 AI 反而是浪费。时间轴上把这类标成"规则（设计如此）"而非失败 |

---

## 六、路演价值

1. **可回放的证据**：现场跑一次，直接打开时间轴 —— 比任何 PPT 描述都有力。
2. **敢展示失败**：断网重跑，时间轴如实显示"全部降级 + 原因码"，证明系统**知道自己什么时候没用 AI**。
   这是绝大多数参赛项目不敢做的，反而是差异化。
3. **回答"AI 到底干了什么"**：不再是一个绿标，而是「S2 目标由 AI 生成、S3 图表由 AI 推荐（重试 2 次）、
   S1/S4/S5 规则（设计如此）」的分阶段答案。
4. **可量化**：AI 参与阶段占比、平均耗时、token 消耗、降级率 —— 都是评委爱看的数字。

---

## 七、与已有工作的衔接

- 复用 `BrainTraceManager` 与 `_safe_trace` 落库模式，**不新造一套 trace 机制**
- 与 2.4 已落地的绿/灰标（`ai_participated` → 前端徽标）**互补**：徽标是结论，时间轴是证据
- 与 D2（3.5 归因实查）共用"诚实降级原因码"设计，避免两处各写一套
- 与方案 P（AI 结果检查）共享 `llm_calls` 表：检查器读该表判断"这张图是否经过 AI 且是否被校验过"
