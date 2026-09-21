# 1.6 AI 失败弹窗（生成看板路径）— 实测结论

> 用户原判断："之前只覆盖对话路径，生成看板时 AI 挂了也要弹窗。"
> 实测结论：**生成路径的弹窗已在之前的提交实现并可用**，本会话做了端到端验证。

## 结论
✅ **1.6 已具备且验证通过**。无需新增代码（除非要覆盖 S4b 边界，见下"残留"）。

## 代码证据（已实现）
- 后端触发：`backend/app/api/brain_run_sse.py`
  - `:188` `_RUN_STATUS.setdefault(run_id, {})["ai_awaiting"] = payload` —— 在 probe / S3 阶段检测到 AI 不可达/失败并暂停等待用户抉择时写入。
  - `:1323` `get_run_status` 回传 `ai_awaiting` 字段。
  - 触发点：`_request_user_choice`（probe 暂停 :566 / S3 暂停 :802）。
- 前端弹窗：`frontend/src/components/charts/LoadingPage.tsx`
  - `:61` `const [aiAwaiting, setAiAwaiting] = useState<any>(null)`
  - `:152-153` `applyStatus` 读 `data.ai_awaiting` → `setAiAwaiting(...)`
  - `:425-455` `<Modal open={!!aiAwaiting} ...>` 渲染选择框（规则兜底 / 等恢复 / 取消）。

## 端到端实测（造 AI 限流场景）
启动方式：强制 LLM 不可达，使 probe 阶段必定暂停弹窗。

```
DUCKDB_PATH=./data/duckdb/qa_aibi.db LLM_BASE_URL=http://127.0.0.1:9/v1 python run_backend.py
```

- `/api/v1/health` → `llm_reachable = False`
- `POST /api/v1/brain/run` `{dataset_id: 3716856d-...}` → `200`，`run_id=31565938-...`
- 轮询 `GET /api/v1/brain/run/{run_id}/status`：

```
 t=1s  status=running stage=       ai_awaiting=no
 ...
 t=15s status=running stage=probe   ai_awaiting=YES
```

- `ai_awaiting` 内容：
  - `stage = probe`
  - `options = ["rule_fallback", "wait_retry"]`
  - `message = "AI 服务当前暂不可用（模型限流或超时）。您可以：用规则引擎立即生成基础看板 / 或等待 AI 恢复后重试"`
  - `reason = HTTP 502`

**判定**：`/status` 真实返回 `ai_awaiting` → 前端 `LoadingPage` 的 `Modal open={!!aiAwaiting}` 必定弹出选择框。链路闭合。

## 残留（非阻塞，待拍板）
- S4b 分析说明文本（brain_run_sse.py:1011）的 LLM 调用失败仅静默回退为规则文案，**不暂停/不弹窗**。
  该步骤非核心（仅看板顶部分析摘要），看板仍正常生成；但若要求"任何 AI 失败都弹窗"，可把它也接入 `_request_user_choice`。
  已在 `OPEN_QUESTIONS.md` 记 `Q2`。

## 完成标准核对
- 后端改动：diff + 实测 API 响应 ✅（本项后端未改，仅验证既有机制；实测 `ai_awaiting` 如期出现）
- UI 改动：diff + 视觉截图 + tsc —— 本项 UI 未改；视觉弹窗需在用户浏览器确认（沙箱无浏览器），触发源已用真实 API 证明。
- 不模糊：非"应该生效"，而是真实 `POST /brain/run` → 第 15s `ai_awaiting=YES` 实测。
