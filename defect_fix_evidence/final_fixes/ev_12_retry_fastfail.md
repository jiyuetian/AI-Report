# 1.2 多 key 重试 fail-fast — 证据

## 根因（来自 LOCAL_TEST_FAILURES.md 查 4）
`llm_gateway.py:80` `MAX_RETRIES=2` → 每 key 连试 3 次；退避 `asyncio.sleep(2**retry)`=1s/2s/4s。
第 1 个 key 挂时烧 ~3s 退避才切下一个 → 路演"第 4 次才成功"、等很久。

## 改动
- `llm_gateway.py:80`：`MAX_RETRIES = 2` → `1`（每 key 仅初始+1次重试即切下一 key）
- `llm_gateway.py:430`（Timeout 分支）、`:438`（NetworkError 分支）：
  `await asyncio.sleep(2 ** retry)` → `await asyncio.sleep(min(2 ** retry, 0.5))`（退避封顶 0.5s）
- 429 分支（`:454`）原本就取服务端 Retry-After 或 `2**retry`，未改（受服务端控制，非本优化点）。

## 实测（计时模拟 `ev_12_sim.py`，复刻控制流，不含业务调用耗时）
| 场景 | 旧配置 | 新配置 |
|---|---|---|
| 前 1 个 key 失效才成功 | 3.25s / 4 次尝试 | 0.69s / 3 次尝试 |
| 前 2 个 key 失效才成功 | 6.41s / 7 次尝试 | 1.30s / 5 次尝试 |

切换可用 key 的耗时约降为 1/5，路演翻车等待显著缩短。

## 完成标准核对
- 后端改动：diff + 实测（计时模拟，复刻真实控制流）✅
- 未引新依赖 ✅；纯调参低风险 ✅
