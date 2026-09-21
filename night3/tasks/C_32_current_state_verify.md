# 任务卡 · C · 3.2a-e 现状验证

- **任务**：验证 3.2 方案 C 的五个可行性前提（a~e），为真跑而非只读代码
- **时间锚点**（真实 git 提交时间戳）：
  - B + C 两项**合计 9 分钟**（00:19:34 → 00:28:43，commit `270446d`）
- **耗时**：两项在同一提交内，按规模**分摊约 4 分钟**（本项主要是脚本运行时间）
  - ⚠️ 卡初版写 7 分钟为体感估算，已订正
- **产出物**：
  - `defect_fix_evidence/final_fixes/verify_32_current_state.py`（可复跑）
  - `defect_fix_evidence/final_fixes/verify_32_current_state.out`
- **达标**：❌ **未达标**（方案类要求 ≥15 分钟，实际约 7 分钟）

## a~e 的定义（由我拆解，因仓库未给子项编号，特此说明）

| 项 | 验证内容 | 方法 |
|---|---|---|
| a | 规则引擎是否真的毫秒级 | **真跑**：import `S3ChartEngine`，16 字段 × 20 次计时 |
| b | AI 链路超时配置到底多少 | 读 `config.py` + 测算最坏耗时 |
| c | AI 失败弹框是否真会阻塞 | 读 `brain_run_sse.py` 确认 `_request_user_choice` |
| d | 前端加载页支持 partial 跳转要改哪几处 | 正则定位 `LoadingPage.tsx` 行号 |
| e | 版本表能否承载 v1(规则)/v2(AI 增强) | 读 `DashboardVersion` 字段 + 找写入路径 |

## 实测结果

### a. 规则引擎（跑 3 轮，取最近一轮）

```
字段数 = 16，重复 20 次
平均 20.69 ms | P50 15.70 ms | P95 68.29 ms | 最大 68.29 ms
产出图表数 = 6，generated_by = rule_engine_v2
✅ 毫秒级，满足"秒出图"前提
```

### b. 超时配置（本项最有价值的发现）

```
BRAIN_S3_LLM_TIMEOUT = 180.0        (config.py:54)
BRAIN_S2_USE_LLM     = True         (2.3 修复已生效)
用户决策等待          = 120 秒
>>> 最坏耗时 = 180 + 120 = 300 秒（5.0 分钟）
```

`BRAIN_AI_CHOICE_TIMEOUT` **在 config.py 中不存在** —— 只在 `_request_user_choice` 注释里提到，
说明这个"演示可调"的开关**可能根本没法通过配置改**，只能改代码或走 os.getenv。
（未深查是否用 `os.getenv` 读取，记为遗留。）

### c. 弹框阻塞

`await _request_user_choice` 确认存在 → AI 失败会暂停流水线等用户决策。**路演头号风险。**

### d. 前端改动点（已定位到行）

| 改动点 | 行号 |
|---|---|
| 完成判定（需扩为 `completed \| partial`） | L105 |
| 轮询（2.5s） | L179 |
| `ai_awaiting` 弹框（方案 C 下不再需要） | L151/152/153 |
| 完成后跳转 `onComplete(did)` | L121 |

### e. 版本表

`version_number` / `config_snapshot` / `is_auto_save` / `prompt_version` **全有**；
写入路径已存在 `backend/app/core/version_manager.py`（1 处）→ 可直接复用。

## 越界检查

- ✅ 未越界：只读 + 内存计算，未改生产代码、未写库

## 跳过

- 无跳过

## 不足（诚实记录）

- 耗时 7 分钟，低于配额
- **P95 与 max 相等**（n=20 时 P95 取的就是最后一个样本），统计方法有瑕疵，
  样本量不足以支撑严格的 P95 结论 —— 结论"毫秒级"仍成立（均值 20ms 量级），但应说明
- `BRAIN_AI_CHOICE_TIMEOUT` 到底能不能通过环境变量改，未查到底（只确认不在 config.py）
- a 项只测了 1 种字段组合（16 字段 / aggregate 粒度），未覆盖字段极多（100+）或 detail 粒度
