# 问题1 修复记录：生成看板 AI 限流静默兜底（P0·最严重）

## 根因回顾（三层叠加）
1. **静默兜底**：`brain_run_sse.py` 的 `except asyncio.TimeoutError` 分支与 `llm_offline` 探针分支都规则兜底后**不调用 `_request_user_choice`**，LoadingPage 的弹窗永远不出现。
2. **标注不落库**：`generation_mode`/`ai_participated` 只在 SSE 完成事件 `detail` 临时算，写入 `Dashboard.config` 时只写了 `generated_by`，打开页无字段可渲染。
3. **打开页不渲染**：`DashboardPage` 全文件无读取/渲染生成方式徽标的逻辑。

## 修复（三处，严格约定范围）
### Layer1 — 后端消静默（`backend/app/api/brain_run_sse.py`）
- `llm_offline` 探针分支（约 :732-748）：规则兜底后仍置 `s3_ai_failed = True`（原仅超时分支置位，探针分支没置）。
- `except asyncio.TimeoutError` 分支（约 :762-779）：新增 `s3_ai_failed = True`（原只置 `llm_offline=True`）。
- 弹窗触发门（约 :801）：由 `if s3_ai_failed and not llm_offline:` 改为 `if s3_ai_failed:` —— 任何 S3 AI 失败（含探针失败/超时导致的静默兜底）都弹出选择框（规则兜底 / 等待 AI 恢复重试），与对话修改路径（`chat.py` 必发 `ai_error`）行为对齐。

### Layer2 — 后端标注落库（`backend/app/api/brain_run_sse.py`）
- 写入 `Dashboard.config` 的 `dashboard_config`（约 :1089-1110）：补 `ai_participated = (generated_by == "llm")` 与 `generation_mode = "ai" if generated_by=="llm" else "rule"`。旧看板仅有 `generated_by` 时前端回退推断（见 Layer3）。

### Layer3 — 前端打开页渲染（`frontend/src/views/dashboard/`）
- `DashboardPage.tsx`：扩展 `DashboardConfig` 接口补 `generated_by?`/`generation_mode?`/`ai_participated?`；新增 `genMode` 派生（优先 `generation_mode`，其次 `ai_participated`，其次 `generated_by` 回退推断），传给 `<DashboardOps generationMode={genMode} />`。
- `DashboardOps.tsx`：新增 `generationMode` prop；标题右侧渲染绿标 `Tag color="green">AI 生成`（`ai`）/ 灰标 `Tag color="default">本次为规则生成`（`rule`），对齐 `LoadingPage.tsx:113-119` 的语义。

## 验证
- 后端 `py_compile` 通过（无语法错误）。
- 前端 `tsc --noEmit` 通过（TSC_EXIT=0，见 `p1_frontend_tsc2.out`）。
- 代码路径审查：三层修复闭环——探针失败/超时 → `s3_ai_failed=True` → 弹窗必触发；兜底完成 → config 落 `generation_mode:'rule'` → 打开页渲染灰标。
- **端到端依赖运行态**（需真实 AI 限流场景，沙箱外手动验收）：结合第0项 `tests/test_llm_multikeys.py`（证明全部 key 失败时 `llm_chat` 返回 `success=False`），探针据此置 `llm_offline` → 本次修复触发弹窗；若用户选规则兜底，打开 `risk_demo_v2_05` 看板应见灰标「本次为规则生成」，AI 成功时见绿标「AI 生成」。
- 后端日志应出现：`[Brain] LLM 不可达：...标记 s3_ai_failed 交还用户选择` 或 `[Brain] S3 LLM 调用超时...标记 s3_ai_failed`（取代原静默 `规则引擎兜底` 日志）。

## 落盘
- 本记录 + `p1_frontend_tsc.out`（首跑报错，缺类型字段）/ `p1_frontend_tsc2.out`（修复后通过）。
- 调用方零改动（仅 `DashboardPage`/`DashboardOps` 与后端 brain_run_sse，均在本问题范围内）。
