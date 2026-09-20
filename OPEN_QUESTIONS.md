# OPEN QUESTIONS

> 本文件记录 AI-Report 项目待澄清/待验证的关键问题。
> 注：原项目无此文件，2026-09-20 由验证流程新建，先沉淀 #3（AI 成功路径验证）。#1/#2 如有待补，请在此追加。

---

## #3 AI 成功路径（绿标）在 nemotron 下是否真实验证通过？

**结论：❌ 未通过。绿标（generated_by=llm / ai_participated=true / generation_mode=ai）在 NVIDIA nemotron-3.5-lightning 下 6 次真跑全部未点亮，S3 一律退回规则兜底（rule_engine）。**

### 验证时间与环境
- 时间：2026-09-20（实测），首次排查 2026-09-10
- 后端：本地 `backend/`（SQLite，无 Redis，代理出口 7897/Clash）
- Provider：NVIDIA `integrate.api.nvidia.com`，模型 `nvidia/nemotron-3.5-lightning-30b-a3b`，key 为用户已有 `nvapi-`
- 数据集：`verify_dataset.csv`（区域销售业绩，24 行 × 8 列，dataset_id `d9fcd451-1468-4b26-8ff8-2a171ace0a1b`）
- 触发：注册用户 `aibiverify` 登录 → 上传 → 建数据集 → `POST /api/v1/brain/run`

### 6 次 run 关键字段（终态均为 completed，但 generated_by 全为 rule_engine）
| run_id | generated_by | ai_participated | generation_mode | S3 阶段耗时 | 说明 |
|---|---|---|---|---|---|
| 4edb69da | rule_engine | false | rule | ~111s(等用户选择超时) | 入口探针单次失败→规则兜底 |
| 62d37707 | rule_engine | false | rule | ~111s | 同上 |
| 1836b0d8 | rule_engine | false | rule | ~111s | 同上（纯碰探针过关，未过） |
| 75c4efd0 | rule_engine | false | rule | 141s(探针重试后仍败) | 探针重试修复前 |
| 059ce246 | rule_engine | false | rule | 50s | 探针重试修复后，探针过关，但 S3 真实 LLM 调用超时 |
| 74c61899 | rule_engine | false | rule | 171s(撞 180s 包裹) | 超时放宽后，仍超时兜底 |

### 根因（两层，均已定位并实测）
1. **入口探针 fail-closed 单次无重试（已修复）**
   - 原 `_check_llm_reachable()` 单次 httpx 调用，撞 NVIDIA ~30% 的 15s 超时即判不可达 → S3 整条降级规则。
   - 修复：`health.py` 加 3 次重试 + 2s 退避（`attempts` 参数，health 端点用 1 保持快、运行期用 3）。run #5 起入口探针已能过关（不再卡 111s）。
2. **S3 真实 LLM 生成调用 nemotron 超时（未解决，模型不适配）**
   - `generate_charts_with_llm` → `llm_chat`(json_mode) → httpx 调 nemotron，日志明确 `LLM超时 (attempt 1/2)` → 重试仍超时 → 降级响应 → `rule_engine`。
   - S1 主题识别（`detect_theme`, use_llm=True）同样超时兜底。
   - 即便把 `BRAIN_S3_LLM_TIMEOUT` 50→180s、`TIMEOUT_SECONDS` 60→120s（config.py / llm_gateway.py），run #6 S3 仍跑满 171s 被切断兜底——**nemotron 对该重型图表 JSON 请求在 180s 内未返回**。
   - 对照：同一 key 对小请求（probe / `quick_nvidia.py`）响应 1–3s、200 OK。即 **nemotron 小请求快、重型生成任务超时/被限流**，在本环境（推理模型 + 7897 代理出口 + 会话内密集调用触发 40/min 限流）跑不通 S3 生成路径。

### 已落地改动（均未回滚，属合理放宽，但未能点亮绿标）
- `backend/app/api/health.py`：`_check_llm_reachable` 加 3 次重试 + 2s 退避；health 端点 `attempts=1`。
- `backend/app/core/config.py`：`BRAIN_S3_LLM_TIMEOUT` 50.0 → 180.0。
- `backend/app/core/llm_gateway.py`：`TIMEOUT_SECONDS` 60 → 120。
- `backend/run_backend.py`：启动早期注入活代理 7897（覆盖工具锁定的不稳定 59106），让后端 Python 进程能访问外网 LLM。

### 验证产物（实测证据，落盘于 WorkBuddy 会话目录）
- 探针/代理：`health_loop.txt`（连续 10 次 llm_reachable 闪烁）、`proxy_diag2.txt`（直连/7897/59106 各 5 次，401 证明网络通）、`nvidia_probe.txt`（run#6 前 2/3 可达，1–3s）
- 各 run 终态：`s3_status2~6.txt`（KEY FIELDS 段）、`s3_run*.txt`（RUN_ID）
- 后端日志：`backend_run_v3/v4/v5.log`、`llm_lines.txt`/`llm_v5.txt`/`s3_llm_log2.txt`（含 `LLM超时 (attempt 1/2)`、`调用失败，已重试1次，使用降级响应`）

### 下一步建议
- **Plan B（商汤）应启用**：用户原定 nemotron 主用、商汤备选。nemotron 不适配 S3 重型生成，建议提供商汤 key 切换验证绿标（商汤非推理模型、延迟更低，S3 成功率更高）。
- 若坚持用 NVIDIA：换更小/更快的 NVIDIA 模型（非 reasoning），或分离代理直连降低延迟，并严格控调用频率避开 40/min 限流；但 路演可靠性存疑。
- 截图路径：无绿标看板截图（绿标从未点亮，前端无需截图）。

> 状态：BLOCKED on provider 选型。绿标验证需换可用模型（商汤 Plan B）方能闭环。
