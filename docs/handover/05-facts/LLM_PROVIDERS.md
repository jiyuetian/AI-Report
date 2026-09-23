# LLM Providers 交接档（ISS-025 路线 A · A4）

> 适用分支：`p0-security-fixes`
> 代码真源：`backend/app/core/llm_gateway.py`、`backend/app/core/config.py`
> 本文档不写真实密钥；真实 key 在 `backend/.env`（gitignored），本档只给结构/位置/加 key 方法。

---

## 1. Token 池清单（provider / key 数 / 模型 / 主备）

- **配置源**：`backend/.env` 的 `LLM_PROVIDERS`（JSON 数组，支持多 key / 多 provider）；不配时回退单 key（`LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`）。
- **每项结构**：`{ name, base_url, api_key, model, function_calling, json_mode }`
- **当前生产形态**（来自交接记忆，非源码硬编码）：
  - 主用：`sensenova` 聚合网关 `https://token.sensenova.cn/v1`，模型 `kimi-k3`，**单 key**（`sk-...` 经商汤网关出网）。
  - 备：历史上接过的 `deepseek-v4-flash` / `glm-5.2` / `sensenova-6.8-flash-lite` / `nvidia/nemotron-3.5-lightning` —— **均已弃用**（弃用原因见 §5），不在当前 `LLM_PROVIDERS` 中。
- **key 数**：当前 1 个主 key。要多 key 容错，在 `LLM_PROVIDERS` 数组里加多项（同 `base_url`、不同 `api_key`）即可，网关按数组顺序尝试。
- **主备优先级**：数组顺序即优先级；`LLMGateway.chat_complete` 外层 `for pi, prov in enumerate(self.providers)` 逐 provider 容错（详见 §2）。

---

## 2. 轮训 / 切换机制（代码位置 + 逻辑 + 触发条件 + 熔断）

**代码位置**：`backend/app/core/llm_gateway.py` → `LLMGateway.chat_complete()`（约 `L338–L528`）

**双层重试结构**
- 外层：遍历 `self.providers`（多 key / 跨 provider 切换）。
- 内层：单 key 内瞬时重试 `MAX_RETRIES` 次（当前 `=1`，即初始 1 次 + 重试 1 次 = 每 key 最多试 2 次；原 2 已改为 1 以 fail-fast 切 key）。

**退避**
- 超时 / 网络错误：`await asyncio.sleep(min(2**retry, 0.5))`（指数退避，封顶 0.5s，快速切 key）。
- `429`：优先用服务端 `Retry-After` 头，否则 `2**retry` 秒。

**切换触发条件**
| 异常 | 行为 |
|------|------|
| `httpx.TimeoutException` | 重试耗尽 → `key_exhausted=True` → 切下一 provider |
| `httpx.NetworkError` | 重试耗尽 → 切下一 provider |
| `429` (限流) | 重试耗尽 → 切下一 provider |
| `4xx` 非 429（key 无效） | **立即跳下一 provider，不重试**（日志 `LLM-FAILOVER ... key无效`） |
| `ValueError`（JSON 解析失败） | 重试 1 次仍失败 → 切下一 provider |

**熔断 / 预算（防 LLM 成为主流程单点）**
- `BRAIN_TASK_TOKEN_BUDGET = 8000`：单次 `/brain/run` 累计 token 预算；达 80% 告警、100% 熔断，跳过后续 LLM 调用并保留已生成图表/看板。
- `BRAIN_S3_LLM_TIMEOUT = 180.0`：`S3` 图表生成外层墙钟上限（`asyncio.wait_for`），杜绝 LLM 不可达时 S3 永久卡在「正在推荐图表…」。
- `TIMEOUT_SECONDS = 120`：单次调用超时（原 60 → 120，容纳慢推理模型）。
- `MAX_RETRIES = 1`、`CONCURRENCY_LIMIT = 2`：并发槽（Redis 可用时排队，否则本地信号量降级）。
- 全 provider 失败：返回 `fallback_response`（`success=False, fallback_used=True`）；无 fallback 时 `success=False`。

**限流后端**：`RateLimiter` 优先用 Redis（`llm:running_count` / `llm:request_queue`）排队；Redis 不可用降级为按运行 loop 的本地 `asyncio.Semaphore`（惰性 `_loop_sem` 避免 "Event loop is closed"）。

---

## 3. 配置位置（`.env` 键名 + `.env.example` 脱敏版）

**文件**
- `backend/.env` —— 真实密钥（gitignored，**不要提交**）。
- `backend/.env.example` —— 脱敏模板（应随真实配置同步更新，但目前**已脱节**，见下）。

**键名清单**
| 键 | 作用 | 默认 |
|----|------|------|
| `LLM_API_KEY` | 单 key 回退 | 空 |
| `LLM_BASE_URL` | 单 key 回退 base_url | 空 |
| `LLM_MODEL` | 单 key 回退模型 | 空 |
| `LLM_PROVIDERS` | 多 provider JSON 数组（**主用路径**） | 空 |
| `LLM_FUNCTION_CALLING` | 模型是否支持函数调用（L3） | `True` |
| `LLM_JSON_MODE` | 是否强制 JSON 输出 | `True` |
| `BRAIN_S2_USE_LLM` | S2 目标生成开关 | `True` |
| `BRAIN_TASK_TOKEN_BUDGET` | 单任务 token 预算（熔断） | `8000` |
| `BRAIN_S3_LLM_TIMEOUT` | S3 图表生成墙钟上限（秒） | `180.0` |
| `REDIS_URL` | 限流队列后端 | `redis://localhost:6379/0` |

**`.env.example` 现状（脱节，需新 agent 修正）**：仍是 `LLM_BASE_URL=https://api.moonshot.cn/v1` + `LLM_MODEL=kimi-latest` 的旧 moonshot 模板，与当前商汤 `kimi-k3` 网关实际不符。建议同步为 `LLM_PROVIDERS=[{"name":"sensenova","base_url":"https://token.sensenova.cn/v1","api_key":"<your-sk>","model":"kimi-k3"}]`。

---

## 4. 切模型时承接历史（已做 / 未做，如实写）

**已做**
- 网关无状态：每次 `chat_complete` 独立按 `self.providers` 数组顺序选 provider；`LLMRequest.model` 支持单调用覆盖模型。
- 对话历史不在网关内：持久化在 DB（`chat_messages`），以 `messages` 传入 → 中途换 provider / model **不丢上下文**。
- 各阶段有确定性规则兜底：LLM 失败 / 超时由兜底接管，不中断主流程（原则移植自 InsightDesk 经验，见 `llm_chat` 注释）。
- `temperature` 规则已硬编码兼容：`kimi` 系列强制 `temperature=1`（否则商汤 400）；`sensenova` 网关自动注入 `business_type=chat`。换非 kimi 模型会自动回落 `request.temperature`。

**未做（如实写，避免误导）**
- 无「某阶段失败自动换特定模型重跑」逻辑：每个调用独立按 provider 顺序尝试，失败后直接降级，不会针对特定阶段挑特定模型。
- 无模型能力画像运行时探测：`L2/L3` 标记是配置项，非运行时探针结果。
- 无「切换模型自动迁移历史会话向量」等跨模型语义承接 —— 历史靠 DB 原文 messages 传递，语义一致性依赖模型自身。

---

## 5. 踩过的坑（按发生频率/影响）

- **Agnes 免费版**：持续 `429` 限流 → 弃用。
- **商汤 SenseNova 间歇性 429**（尤高峰）：需 `business_type=chat` 否则 `400`；`kimi` 仅允许 `temperature=1`。
- **NVIDIA nemotron-3.5-lightning**：推理模型带 thinking，图表 JSON 真实生成常需 50~120s；原 `TIMEOUT_SECONDS=60` 未返回即重试/降级 → 放宽到 `120` + `BRAIN_S3_LLM_TIMEOUT=180` 才点亮绿标。该路径经 `7897` 代理出口。
- **deepseek-v4-flash**：间歇 `429` → 弃用。
- **sensenova-6.8-flash-lite**：推理模型 `json_mode` 无 content → 弃用。
- **GLM / 部分模型下架**：切换前确认模型名仍在线。
- **Redis 不可用**：限流器降级本地信号量（跨 loop 用惰性 `_loop_sem` 防 "Event loop is closed"）。
- **多 loop httpx client**：按 `(loop_id, name)` 分键缓存，避免跨 loop "Event loop is closed"。
- **`.env.example` 与实际脱节**（见 §3）—— 已写文档但未修正文件。

---

## 6. 新 agent 怎么加 key / 加 provider

**加 key（同 provider 多 key 容错）**
编辑 `backend/.env` 的 `LLM_PROVIDERS`，数组里加一项（同 `base_url`，不同 `api_key`），网关按数组顺序轮询：
```json
LLM_PROVIDERS=[
  {"name":"sensenova","base_url":"https://token.sensenova.cn/v1","api_key":"sk-AAA","model":"kimi-k3"},
  {"name":"sensenova-b","base_url":"https://token.sensenova.cn/v1","api_key":"sk-BBB","model":"kimi-k3"}
]
```

**加 provider（换模型 / 换厂商）**
在 `LLM_PROVIDERS` 数组加 `{name, base_url, api_key, model}`，**顺序即优先级**（主在前）：
```json
LLM_PROVIDERS=[
  {"name":"sensenova","base_url":"https://token.sensenova.cn/v1","api_key":"sk-AAA","model":"kimi-k3"},
  {"name":"backup","base_url":"https://other.example/v1","api_key":"sk-YYY","model":"gpt-4o"}
]
```

**仅单 key（最简）**
直接填 `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`，`LLM_PROVIDERS` 留空即可（向后兼容）。

**生效方式**
改完重启后端（`run_backend.py`，它 `chdir` 到 backend 根并加载 `.env`；`config.py` 用 pydantic-settings 读 `.env`）。

**验证连通**
- 看后端日志：`[LLM] provider {name} attempt 1/2, request_id=...` 表示正常出网。
- 或调 `/api/v1/health` 探针（网关侧 `max_tokens=64` + `business_type` 适配）确认链路通。
- 限流/切换：制造一个失效 key 观察日志出现 `LLM-FAILOVER ... 切换下一 provider`。

**配套动作（务必做）**
- 同步更新 `backend/.env.example` 脱敏版，保持与真实配置一致（当前已脱节，见 §3）。
- 注意约束：`kimi` 系列必须 `temperature=1`；`sensenova` 网关必须 `business_type=chat`，**代码已自动注入，无需手动**。

---

*生成于 ISS-025 路线 A（A4）。与 `docs/handover/07_ENV_SECRETS.md`（密钥管理）、`05_KNOWN_TRAPS.md`（通用陷阱）互为补充。*
