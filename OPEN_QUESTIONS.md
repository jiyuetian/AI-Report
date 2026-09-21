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

---

## #4 P0 安全债修复（G1–G4）遗留与待跟进项

> 2026-09-21 完成 G1–G4 四类 P0 修复（分支 `p0-security-fixes`，基线 `f42dcc6`）。以下为修复过程中**仅登记、未顺手改**的问题与新发现，供后续迭代。

### 4.1 鉴权规范化残留（G1/G3 范畴外，建议下一轮统一排查）
- `backend/app/api/tokens.py`、`token_applications.py`、`chat.py` 中部分端点仍使用 `current_user: str = "anonymous"` 默认匿名（如 `tokens.py` L46/L73/L94/L163 附近）。G3 已修复 `shares/my/list`、`exports/my/list` 的匿名默认，但其余端点未动——属鉴权语义遗留，需后续统一收敛为「无 token 即 401」。
- `security.py` 的 `get_current_user` 在非 Bearer 场景返回 401；但个别端点签名仍保留 `current_user` 缺省值，易造成「匿名可访问」误判。建议全局搜索 `= "anonymous"` 与 `= "anonymous"` 默认参数，统一移除。

### 4.2 G2 归属过滤的边界（已修，但需注意）
- G2.1 数据集列表 `GET /api/v1/datasets` 保留了 legacy 可见性（登录用户可见全部），仅详情/写操作做归属校验。若业务要求「只看自己」，需改 list 查询加 `created_by` 过滤（当前为兼容性妥协，已在 G3_FIX.md 标注）。
- `dashboards` 表新增 `created_by`/`updated_by` 列（G2.1 提交 `2b06b74`），**历史数据这两列为 NULL**；归属校验对 NULL 行按「不可越权访问」处理（返回 404/403）。迁移历史看板归属需手动补 `created_by`，否则老看板对原主也不可见。

### 4.3 G4 净化范围（已闭环，但需部署侧配合）
- `bleach==6.4.0` 为**新增后端依赖**，项目无 `requirements.txt`，部署清单必须补 `bleach`（否则报告生成端点 import 失败 → 500）。详见 `FIX_SUMMARY.md` 部署注意。
- 净化白名单不含 `style` 属性（防 CSS 注入）；若未来报告需内联样式，须改用受信任 `<style>` 块或扩展白名单并加 CSS sanitizer。

### 4.4 回归结论（全量）
- **L1 单测**：隔离 QA 库 `backend/data/qa_l1test.db` + 显式建表重跑，结果见 `defect_fix_evidence/fixes/l1_pytest2.out`。首跑 43 passed / 4 failed，4 失败均为环境/既有问题（`test_quality_checker` 的 `row_count` 误判、`test_run_status_recovery` ×3 缺 conftest 建表），**非 G1–G4 引入**。
- **L2 前端**：`tsc --noEmit` 退出码 0，类型检查通过（`frontend_tsc.out`）。
- **L5 安全复现**：`g3_verify.py` 13/13 PASS、`g4_verify.py` 22/22 PASS（见各自 `.out`），P0 清零。
- **L3 E2E**：由 G3/G4 验证脚本经 ASGI 直调覆盖主链路（鉴权拒绝 + 报告净化），等价于端到端冒烟。

### 4.5 L1 回归暴露的预存缺陷（非 G1–G4 引入，仅登记）
- `backend/tests/test_quality_checker.py::test_unique_row_count_reflects_total_duplicate_rows` 失败：`QualityChecker._check_unique` 的 `row_count` 仍恒为 0（期望 5），导致前端"涉及行数"列失真、去重无法精确定位行。该测试为"修复回归"用例，说明对应修复未落库；属 pre-existing 逻辑 bug，**不在 G1–G4 范围**，本次不顺手改，登记待修。
- 隔离 QA 库重跑 L1：46 passed / 1 failed（首跑默认库 43 passed / 4 failed 中的 3 个 `no such table` 环境失败，已随隔离库显式建表消除）。**G1–G4 引入的回归为 0。**

> 状态：G1–G4 已交付，P0 清零；#4.1/#4.2/#4.5 为后续迭代项，不阻塞本次发布。
