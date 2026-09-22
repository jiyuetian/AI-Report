# 证据 · 3.2a-e 加载页 UI 行为

> 任务性质：加载页 5 项 UI 行为。纪律：tsc + 本机验证清单 + 真实执行后端验证。
> 结论先行：b/c/d 三项此前已在代码中实装（本轮核实确认），本轮实际改的是 **a（ETA）** 与 **c（加载中区分）**；e 经核实后端约束+前端控件已覆盖。

## 一、逐项核实（读代码 + 真实调用，非推断）

| 项 | 结论 | 证据 |
|---|---|---|
| **3.2a 时间预估准确性** | 本轮改（前端） | 原 ETA 为纯瞬时 rate，长 AI 阶段失真 → 改为 EMA 平滑 + 卡住检测 + 阶段步序展示（见下） |
| **3.2b 离开后恢复** | 已实装（核实，不改） | `LoadingPage.tsx` localStorage `RUN_KEY(datasetId)`(L28) + 挂载恢复(L232-243)；后端 `/status` 带 `dataset_id` 反查最近看板(L1436) |
| **3.2c AI vs 规则区分** | 本轮增强（前端+后端） | 原仅完成态显示 Tag(`L384`)；本轮后端 S2 后下发 `generation_mode` + 前端加载中即显示「AI 增强生成中/规则引擎生成中」徽标 |
| **3.2d 完成通知** | 已实装（核实，不改） | `applyStatus` 完成时 `message.success`/`message.warning`(L116-119) + 完成态 Tag |
| **3.2e AI 跑动约束** | 已覆盖（核实，不改） | 后端 `BRAIN_S3_LLM_TIMEOUT=180s`(config.py:54) + token 预算熔断(`budget.is_cut()` S4b L935) + `/cancel` 端点；前端取消按钮 + 跳过 + 底部约束说明(L421) |

## 二、本轮改动

### 后端 `brain_run_sse.py`
1. S2 结束后写入状态缓存（L701 后）：
   `_RUN_STATUS.setdefault(run_id, {})["generation_mode"] = "ai" if s2_generated_by=="llm" else "rule"`
2. `/status` 响应增字段 `"generation_mode": cache.get("generation_mode")`（L1336 附近）

### 前端 `LoadingPage.tsx`
3. **3.2a ETA**：`applyStatus` 内 ETA 由纯瞬时 rate 改为
   - EMA 平滑（`etaEmaRef`，α=0.4）避免 2.5s 轮询跳动
   - 卡住检测：`pct` 连续 >10s 未推进且已耗时>15s → 显示「AI 阶段处理中，请稍候」（长 AI 阶段诚实提示，不报误导小数字）
   - 进度区展示「正在：{阶段名}（第 N/5 步）· {ETA} · 已自动重试 N 次」
4. **3.2c 加载中徽标**：新增 `genModeLive` 状态，读取 `data.generation_mode`；运行中显示绿标「AI 增强生成中」/ 灰标「规则引擎生成中」；`startRun` 重置

## 三、验证

### 3.1 前端类型检查
```
cd frontend && node tsc --noEmit -p tsconfig.json  →  TSC_EXIT=0（无错误）
```

### 3.2 后端真实执行（verify_32_generation_mode.py，直接 await get_run_status）
```
[3.2c] generation_mode='ai'   -> /status 回传 'ai'   PASS
[3.2c] generation_mode='rule' -> /status 回传 'rule'  PASS
[源码] SSE 写入点存在: True | /status 读取点存在: True
RESULT: ALL PASS
```
> 说明：绕过 FastAPI `Depends(get_current_user)`，将 `current_user={}` 作为普通参数直传；`_RUN_STATUS` 为 SSE 写/ `/status` 读同一模块级字典，模拟 S2 写入后调用端点，确属真实执行路径，非"应该生效"。

### 3.3 本机验证清单（沙箱无浏览器，需用户本机开生成流程确认）
- [ ] 触发一次 AI 生成（S2 用 LLM）→ 加载中进度区出现绿标「AI 增强生成中」，且显示「正在：{阶段}（第 N/5 步）」
- [ ] 触发一次规则生成（关 LLM）→ 加载中灰标「规则引擎生成中」
- [ ] 长 AI 阶段（progress 卡住）→ ETA 显示「AI 阶段处理中，请稍候」而非跳动小数字
- [ ] 生成进行中刷新页面（F5）→ 从 localStorage 恢复进度，不重复生成（3.2b）
- [ ] 完成后 → message 通知 + 完成态「AI 生成/本次为规则生成」Tag（3.2c/d 一致）
- [ ] 暗色模式下徽标/进度区可读

## 四、影响 / 风险
- 后端仅增 1 个缓存字段 + 1 个响应字段，无新依赖、无破坏既有 payload（完成态 `detail.generation_mode` 仍由原逻辑写入，二者同源一致）
- 前端仅新增状态/ref + 渲染分支，不改动既有完成/失败/恢复逻辑
- `genModeLive` 与完成态 `dashboardAiParticipated` 并存但不冲突（运行中显示 live 徽标，完成态显示最终 Tag）
