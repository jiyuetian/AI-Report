# LLM 多 Key 容错方案（待确认后再改）

> 状态：**方案阶段**。本文件只描述设计与决策，不含实现代码。
> 基线：`3e0f631`（在前一任务诊断报告落库后冻结）。
> 依赖：本项是后续「问题 1 限流静默兜底」的基础设施——多 key 让「AI 失败弹窗」只在**全部 key 都失败**时才触发，否则静默切 key 自愈。

---

## 1. 现状：当前是单 key

| 位置 | 事实 |
|------|------|
| `backend/app/core/config.py:24-26` | `LLM_API_KEY / LLM_BASE_URL / LLM_MODEL` 三个**单值**字段 |
| `backend/app/core/llm_gateway.py:67-69` | 模块导入时从 `settings` 读这三个值，写死进模块级常量 `LLM_API_KEY/LLM_BASE_URL/LLM_MODEL` |
| `llm_gateway.py:288-295` | `LLMGateway.__init__` 用**单一** `base_url+api_key` 建一个 `httpx.AsyncClient` 单例客户端 |
| `llm_gateway.py:349-444` | `chat_complete` 内 `for retry in range(MAX_RETRIES + 1)`，`MAX_RETRIES=1` → **每 key 仅 2 次尝试**，退避 `2**retry`（1s/2s）；`Timeout/Network/HTTPStatus` 重试，`Exception` 直接 break |
| `backend/.env` | **激活**：`LLM_API_KEY=sk-…`（SenseNova `kimi-k3`）；**注释备用**：`NV_LLM_*`（NVIDIA nemotron）、`AGNES_LLM_*`（AGNES flash） |
| 调用方 | 全部经 `llm_chat`（`action_executor / intent_classifier / s1_theme_detector / s2_goal_generator / s3_llm_enhancer / ai_quality_checker` 及对话改写）——**单点入口，适合在此做容错** |

**结论**：当前确为单 key。任何一次 key 限流/失效 → 网关 2 次重试耗尽 → `success=False` → 上层弹窗或静默兜底。没有「换一个 key 再试」的能力。

---

## 2. 多 key 配置设计（A/B/C 三方案 + 推荐）

### 方案 A：逗号分隔多 key（同 base_url/model）
```
LLM_API_KEYS=sk-aaa,sk-bbb,sk-ccc
```
- ✅ 改动最小，只把单值变列表。
- ❌ **无法携带不同 base_url/model**——而你的 `.env` 里 NV/AGNES 是**不同 provider**（不同 base_url、不同 model）。SenseNova 的 `business_type`、kimi 的 `temperature=1` 等 quirks 也是按 base_url/model 判定的。纯 key 列表表达不了「换 provider 重试」。

### 方案 B：provider 列表（JSON）
```
LLM_PROVIDERS=[{"name":"sensenova","base_url":"https://token.sensenova.cn/v1","api_key":"sk-…","model":"kimi-k3"},
               {"name":"nvidia","base_url":"https://integrate.api.nvidia.com/v1","api_key":"nvapi-…","model":"nvidia/nemotron-3.5-lightning-30b-a3b"},
               {"name":"agnes","base_url":"https://apihub.agnes-ai.com/v1","api_key":"sk-…","model":"agnes-2.0-flash"}]
```
- ✅ **完整表达「换 key / 换 provider 重试」**：每个条目自带 base_url/model/key，且允许省略 base_url/model 继承默认（即可「同 provider 多 key」也可「跨 provider」）。
- ✅ 你的 `.env` 注释掉的 NV/AGNES 块直接映射成列表项，迁移直观。
- ❌ 需要解析 JSON（但 `pydantic`/标准 `json` 即可，无新依赖）。

### 方案 C：独立配置文件 `llm_providers.json`
- 与方案 B 同结构，只是放文件里而非 `.env`。
- ⚠️ 多一个部署文件，运维成本更高；收益不明显。

### ✅ 推荐：**方案 B，且保留单 key 兼容回退**
- 新增可选 env `LLM_PROVIDERS`（JSON 数组）。
- **若 `LLM_PROVIDERS` 未设/为空 → 退回当前的 `LLM_API_KEY/BASE_URL/MODEL` 单 key 行为**（完全向后兼容，现有部署 `.env` 零改动）。
- 列表项支持字段缺省继承默认：`{"name":"sensenova-b","api_key":"sk-第二个key"}` 即「同 provider 第二个 key」。
- 理由：既满足你「好几个 token、可能跨 provider」的真实诉求，又不破坏已有单 key 部署；把跨 provider 的 base_url/model/quirks 差异显式化，避免方案 A 的信息丢失。

---

## 3. 重试策略（每 key 2 次，按错误类型分流）

### 3.1 两层重试的边界（明确不打架）
- **内层（per-key）**：单个 key 内的瞬时重试——沿用网关现有循环，但 `MAX_RETRIES` 由 `1` → **`2`**（即「初始 1 + 重试 2 = 3 次」，**对齐你要求的「每个 key 重试 2 次」**）。退避 `2**retry`（1s/2s/4s）。
- **外层（per-provider）**：某 key 内层耗尽后，**切到下一个 provider** 重试，外层同样每个 provider 走完整内层重试。
- 二者正交：内层解决「同一 key 瞬时抖动」，外层解决「这个 key 真挂了换下一个」。

### 3.2 什么错误 → 切下一个 key（关键决策表）
| 错误 | 本 key 内重试？ | 耗尽后切 key？ | 说明 |
|------|----------------|---------------|------|
| **429 限流** | ✅ 重试 2 次 | ✅ 切 | 限流 key 短时难恢复，换 key 才能摊薄配额（你要求的核心场景） |
| **超时（TimeoutException）** | ✅ 重试 2 次 | ✅ 切 | 模型不可达/慢；另一个 provider 可能更快 |
| **5xx** | ✅ 重试 2 次 | ✅ 切 | 该端点服务端错误 |
| **4xx 非 429（400/401/403）** | ❌ **不重试** | ✅ 立即切 | key 无效/无权限——重试无意义，直接放弃本 key 跳下一 key |
| **返回格式错（json_mode 下未解析出 JSON）** | ✅ 重试 1 次 | ✅ 切 | 当前代码 `raise ValueError` 被 `except Exception: break` 直接放弃；改为「本 key 重试 1 次，仍失败则切 key」——另一 provider 可能更听话地遵守 `response_format` |
| **网络错误（NetworkError）** | ✅ 重试 2 次 | ✅ 切 | 同超时 |

> 注：4xx 非 429 的处理与「每个 key 重试 2 次」不冲突——它属于「key 本身不可用」，直接跳走，不浪费 2 次重试。

### 3.3 切 key 之间要不要退避
- **不建议**长退避。理由：429/超时已在内层退避过；4xx 是瞬时判定无需等。
- 仅加一个**极短固定间隔（0.2s）**防止 tight loop 刷日志即可；或完全不加，让切换即时发生。
- 429 若响应带 `Retry-After` 头，**内层退避优先采用 `Retry-After` 秒数**（比固定指数更准）。

---

## 4. 切换日志（脱敏）

- 每次切 key **必打 INFO 日志**，格式：
  ```
  [LLM-FAILOVER] provider#0 sensenova 失败(429 RateLimitError)，切换 provider#1 nvidia
  ```
- **脱敏规则**：日志只打印 `provider 序号 + name`，**绝不打印完整 api_key**。如需定位，最多打印掩码 `sk-…abcd`（前 3 + 后 4）。
- 全部 key 耗尽时打 `ERROR [LLM-ALL-KEYS-FAILED] N 个 provider 均失败，进入降级`——这是触发上层弹窗的唯一点，日志要明确。

---

## 5. 与现有两套重试 / 弹窗的关系

### 5.1 网关 `MAX_RETRIES`（1→2）
- 仅改 `llm_gateway.py:80` 常量 `MAX_RETRIES = 1` → `2`。其余网关重试逻辑（退避、错误分类）**原样复用**，不重写。

### 5.2 `_retry_s3_with_ai`（brain_run_sse.py:213，退避 8/16/24s）+ `s3_llm_enhancer.MAX_RETRIES=2`
- 这是 **S3 阶段级**重试（整段图表生成重试），与「key 级」重试**正交、不冲突**：
  - 阶段重试调用 `generate_charts_with_llm` → 内部 `llm_chat` → 现在 `llm_chat` 自己会多 key 容错。
  - ⚠️ **组合最坏时长**：若 3 provider × 各 3 次 × `timeout=120s` → 理论上 1080s，但 `BRAIN_S3_LLM_TIMEOUT=180s`（`config.py:50`，`asyncio.wait_for` 墙钟）会掐断 → 落入规则引擎兜底（现有安全网）。
  - **实际无碍**：限流是「即时 429」，切换很快（ms 级），不会撞 180s；只有「某 provider 整体慢/超时」才会被 180s 截断——而这本就是预期降级路径。
  - 建议（非必须）：S3 路径不必再单独调大重试，多 key 已提供足够冗余；保持现状即可。

### 5.3 「AI 失败弹窗」语义不变（仅全败才弹）
- 多 key 只改变 `llm_chat` 内部行为：**只要还有任一 key 成功，就返回 `success=True`，上层无感知**。
- 仅当**所有 provider 都失败** → `llm_chat` 返回 `success=False, fallback_used=True`（与今日一致）→ 上层（S3 静默兜底 / 对话改写 `ai_error` 弹窗）照常触发。
- 这正是你要求的：「全部失败 → 才弹窗；不是每个 key 失败都弹窗」。

### 5.4 实施位置（单点）
- **只在 `llm_gateway.py` 改**（`LLMGateway.__init__` + `chat_complete` + `llm_chat` 可选透传）。
- 所有调用方（`llm_chat` 签名不变）**零改动**自动获得多 key 容错——入口探针、S3、S4b 叙述、对话改写、意图分类全覆盖。

---

## 6. 验证方案（模拟 key A 挂 → 切 key B 成功）

用 `httpx.MockTransport` 在**不联网**的情况下拦截 `/chat/completions`，无需新依赖（httpx 自带）：

| 用例 | provider#0 行为 | provider#1 行为 | 期望断言 |
|------|----------------|----------------|----------|
| 切 key 成功 | 返回 `429` | 返回 `200` + 合法 JSON | `resp.success == True` 且 `resp.model == "nvidia/..."`；日志含 `[LLM-FAILOVER]` |
| 全败降级 | 返回 `429` | 返回 `429` | `resp.success == False and resp.fallback_used == True`；上层弹窗路径不动 |
| 4xx 立即跳 | provider#0 返回 `401` | 返回 `200` | 不内层重试、直接切；`resp.success == True` |
| 超时切 key | provider#0 `TimeoutException` | `200` | `resp.success == True`（验证 timeout 也走外层） |

- 测试文件放 `backend/tests/test_llm_multikeys.py`（或 `defect_fix_evidence/ui_fixes/` 下），随实现一并落盘。
- 也可加一个「.MockTransport 让 #0 抛网络错误、#1 正常」的冒烟，覆盖 `NetworkError` 分支。

---

## 7. 改动文件清单（预览，待你确认后实施）
| 文件 | 改动 | 范围 |
|------|------|------|
| `backend/app/core/config.py` | 新增 `LLM_PROVIDERS: str = ""`（JSON），解析为 provider 列表；保留单 key 回退 | 仅新增字段 |
| `backend/app/core/llm_gateway.py` | ① `LLMGateway` 持 provider 列表 + 惰性 client 池；② `chat_complete` 外层 per-provider 循环 + 错误分流（4xx 立跳 / 429·超时·5xx 内层重试后切 / JSON 错重试后切）；③ `MAX_RETRIES=1→2`；④ 脱敏 failover 日志；⑤ SenseNova/kimi quirks 移到 per-provider client 构造 | 仅本文件 |
| `backend/tests/test_llm_multikeys.py` | MockTransport 四用例 | 新增 |
| `.env`（仅你确认后） | 取消 NV/AGNES 注释并整理为 `LLM_PROVIDERS` JSON；**当前不动** | 部署侧，按需 |

> 严格遵守约束：**不碰生产库和 `.env`**；本方案阶段 `.env` 完全不动，待你确认实现时再决定如何填 `LLM_PROVIDERS`。

---

## 8. 风险与注意
1. **单例客户端**：`get_llm_gateway()` 单例在首次调用时建 client。多 provider 下改为惰性建 client 池；若运行期改配置需重建（本任务不涉及热更新，忽略）。
2. **SenseNova/kimi quirks**：`business_type`、`temperature=1` 当前按 `LLM_BASE_URL`/`LLM_MODEL` 字符串判定（`llm_gateway.py:337-341`），改为 per-provider client 构造时须**保留这段判定**，按每个 provider 的 base_url/model 应用。
3. **S3 超时墙**：见 5.2，多 key 不会让正常限流场景变慢，仅「全慢」时按既有 180s 截断降级。
4. **向后兼容**：`LLM_PROVIDERS` 缺省时 100% 等同今日单 key 行为，可安全合入不破坏现有部署。

---
*待你确认「采用方案 B（provider 列表 + 单 key 回退）」后，我再按总纪律顺序实施：LLM 多 key → 问题1 → 问题2 → 问题3 → 问题4，每项落盘 `defect_fix_evidence/ui_fixes/`。*
