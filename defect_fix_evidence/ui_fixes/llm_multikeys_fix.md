# 第 0 项：LLM 多 key 容错 —— 修复记录

> 基线：`3e0f631` → 方案：`294a0cf` → 本修复提交见 git log
> 范围：仅 `backend/app/core/config.py` + `backend/app/core/llm_gateway.py` + 新增测试，调用方零改动。

## 改动摘要（diff）

### `backend/app/core/config.py`
- 新增字段 `LLM_PROVIDERS: str = ""`（JSON 数组 provider 列表）。
- 新增 `get_llm_provider_list()`：
  - `LLM_PROVIDERS` 配合法非空 JSON 数组 → 归一化返回（每项可省略 base_url/model 继承默认）。
  - 否则回退单 key（`LLM_API_KEY/BASE_URL/MODEL` 构造一个 provider）。
  - 都没有 → 返回 `[]`（网关进 mock 模式）。
  - **向后兼容**：不配 `LLM_PROVIDERS` 时行为与旧版单 key 完全一致（已冒烟验证：返回 1 个 `default` provider）。

### `backend/app/core/llm_gateway.py`
- `MAX_RETRIES = 1` → **`2`**（每 key 内瞬时重试 2 次，对齐「每个 key 重试 2 次」）。
- 新增 `_mask()`：脱敏响应错误中的密钥片段（`sk-/nvapi-/agnes-` 前缀），日志绝不打印完整 key。
- `LLMGateway.__init__(providers=None)`：持 provider 列表 + 惰性 client 池 `_clients`（按 name 缓存），`mock_mode = not providers`。
- 新增 `_build_client(prov)` / `_get_client(prov)`：按每个 provider 的 base_url/api_key 建客户端（SenseNova `business_type`、kimi `temperature=1` 等 quirks 改按 per-provider 判定）。
- `chat_complete` 重构为**双层循环**：
  - **外层**：逐个 provider 容错（多 key / 跨 provider 切换）。
  - **内层**：单 key 瞬时重试（沿用 `MAX_RETRIES` + 指数退避 `2**retry`）。
  - 错误分流（核心决策）：
    - `429 限流` → 内层重试（优先用 `Retry-After`，否则 `2**retry`），耗尽后切 key。
    - `超时 / 网络错误 / 5xx` → 内层重试后切 key。
    - `4xx 非 429`（key 无效）→ **不重试，立即跳下一 provider**。
    - `JSON 解析失败` → 本 key 仅重试 1 次，仍失败则切 key。
  - 切换日志：`[LLM-FAILOVER] provider X 失败(...) 切换下一 provider`（脱敏）；全败：`[LLM-ALL-KEYS-FAILED] N 个 provider 均失败，进入降级`。
  - 全部失败才返回 `success=False, fallback_used=True` —— **上层弹窗/兜底语义不变，仅全败才触发**（解决「问题 1 限流静默」的基础设施）。
- `close()`：关闭 `_clients` 池中所有客户端。

## 实测验证

`backend/tests/test_llm_multikeys.py`（httpx.MockTransport 拦截 `/chat/completions`，不联网、无新依赖）：

| 用例 | 行为 | 期望 | 结果 |
|------|------|------|------|
| 切 key 成功 | p0 返 429 → p1 返 200 | success=True 且 p1 被调用 | ✅ |
| 全败降级 | p0、p1 均 429 | success=False, fallback_used=True | ✅ |
| 4xx 立即跳 | p0 返 401 → p1 返 200 | success=True 且 p0 仅调用 1 次（不内层重试） | ✅ |
| 超时切 key | p0 抛 TimeoutException → p1 返 200 | success=True 且 p1 被调用 | ✅ |

运行结果：**`4 passed`**（见 `llm_multikeys_test.out`）。

向后兼容冒烟：无 `LLM_PROVIDERS` 时 `get_llm_provider_list()` 返回 1 个 `default` provider，网关 `mock_mode=False`、构造正常、无导入错误。

## 与现有重试的关系（不打架）
- 网关 `MAX_RETRIES` 仅常量改动（1→2），原有退避/错误分类逻辑原样复用。
- `brain_run_sse.py:_retry_s3_with_ai`（8/16/24s 阶段重试）与 `s3_llm_enhancer.MAX_RETRIES=2` 正交：`llm_chat` 现在内部多 key 容错，二者组合；`BRAIN_S3_LLM_TIMEOUT=180s` 仍是最终安全墙（限流是即时 429，切换很快不撞墙）。

## 部署注意（待你确认后填 .env）
- 多 key 仅在 `LLM_PROVIDERS` 配置后生效；当前 `.env` 未动，仍是单 key。
- 启用示例：`LLM_PROVIDERS=[{"name":"sensenova","base_url":"https://token.sensenova.cn/v1","api_key":"sk-...","model":"kimi-k3"},{"name":"nvidia","base_url":"https://integrate.api.nvidia.com/v1","api_key":"nvapi-...","model":"nvidia/nemotron-3.5-lightning-30b-a3b"}]`
- 注意：`.env` 中 JSON 含引号/逗号，需确认加载器正确解析（pydantic_settings 读取整行）。
