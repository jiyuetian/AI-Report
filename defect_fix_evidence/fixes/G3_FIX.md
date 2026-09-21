# G3 修复记录 — 13 个未认证端点加鉴权

**类目**：G3（P0 安全债第四类：未认证端点越权访问）
**分支**：`p0-security-fixes`
**日期**：2026-09-21

## 1. 修复范围与目标

为 13 个此前不带任何鉴权的端点补上登录门禁，区分「仅管理员」与「登录即可」：

| # | 端点 | 鉴权方式 | 说明 |
|---|------|----------|------|
| 0 | `GET /api/v1/datasets` | `get_current_user` | 数据集列表（保留 legacy 可见性） |
| 1 | `GET /api/v1/datasets/{id}` | `get_current_user` + 归属 | 已被 G2.1 覆盖 |
| 2 | `GET /api/v1/brain/report/{dataset_id}` | `get_current_user` + 数据集归属 | 落库前已生成报告，需防越权读取 |
| 3 | `GET /api/v1/quality/{dataset_id}/issues` | `get_current_user` + 数据集归属 | 质检问题 |
| 4 | `GET /api/v1/lineage/graph/{dataset_id}` | `get_current_user` + 数据集归属 | 血缘图谱 |
| 5 | `GET /api/v1/lineage/stats/{dataset_id}` | `get_current_user` + 数据集归属 | 血缘统计 |
| 6 | `GET /api/v1/llm/config` | `require_admin` | 防泄露内网 LLM 地址/密钥状态 |
| 7 | `GET /api/v1/chat/sessions/latest` | `get_current_user` | 前端恢复对话历史 |
| 8 | `GET /api/v1/brain/configs` | `require_admin` | 策略大脑配置 |
| 9 | `GET /api/v1/brain/configs/{category}` | `require_admin` | 单类配置 |
| 10 | `GET /api/v1/brain/configs/{category}/history` | `require_admin` | 配置变更历史 |
| 11 | `GET /api/v1/shares/my/list` | `get_current_user` | 改用真实 user_id，移除 `anonymous` 默认值 |
| 12 | `GET /api/v1/exports/my/list` | `get_current_user` | 改用真实 user_id，移除 `anonymous` 默认值 |

## 2. 变更文件

后端（8 个）：
- `backend/app/api/brain.py` — `/configs`、`/configs/{category}`、`/configs/{category}/history` 改 `require_admin`；`/report/{dataset_id}` 加 `get_current_user` + `_assert_dataset_access`
- `backend/app/api/chat.py` — `/sessions/latest`、`/sessions/{id}/history` 加 `get_current_user`
- `backend/app/api/llm.py` — `/config` 改 `require_admin`
- `backend/app/api/datasets.py` — `list_datasets` 加 `get_current_user`（legacy 数据仍对登录用户可见）
- `backend/app/api/exports.py` — `/my/list` 改 `get_current_user`，移除 `user_id="anonymous"`
- `backend/app/api/lineage.py` — `/graph/{id}`、`/stats/{id}` 加 `get_current_user` + `_assert_dataset_access`
- `backend/app/api/quality.py` — `/{id}/issues` 加 `get_current_user` + `_assert_dataset_access`
- `backend/app/api/share.py` — `/my/list` 改 `get_current_user`，移除 `user_id="anonymous"`

前端（1 个）：
- `frontend/src/components/chat/ChatPanel.tsx` — `loadHistory()` 中 `/chat/sessions/latest` 裸 `fetch` 改为带 `authHeaders()`（避免 401 白屏）；补 `import { authHeaders } from '../../utils/request'`

## 3. 修复过程中发现并修正的关键缺陷（否则服务器无法启动）

G3 改动在落地时引入了若干会导致模块 `ImportError`/`IndentationError`、进而**整个后端无法启动**的缺陷，已一并修复：

1. **缩进错误（致命）**：`chat.py`、`llm.py`、`exports.py`、`lineage.py`、`quality.py`、`share.py` 中的新增 import 行被错误地加了 3 个前导空格（`   from app.core.security import ...`），会触发 `IndentationError`。已全部改为顶格。
2. **`Dict` 未导入（致命）**：`share.py` 原仅 `from typing import Optional`，新增 `current_user: Dict` 注解会触发 `NameError`；`exports.py` 原仅 `from typing import Optional, Literal`，同样缺 `Dict`。已分别补 `Dict, Any` / `Dict`。

> 上述两类缺陷经 `py_compile` 全量语法校验 + `g3_verify.py` 实跑验证，均已消除。

## 4. 验证

脚本：`defect_fix_evidence/fixes/g3_verify.py`
- 运行环境：`/c/Users/Asus009/.workbuddy/binaries/python/envs/default/Scripts/python.exe`
- 隔离：临时 QA 库 `backend/data/qa_g3/qa_g3_verify.db` + 独立 DuckDB，不触碰生产 `backend/data/aibi.db`
- 方式：`httpx.AsyncClient` + `ASGITransport` 直调 ASGI app（本机 starlette 0.36.3 与 httpx 0.28 的 TestClient 不兼容，故绕过）
- 判定：普通端点「无 token=401 且 带 token≠401」；管理员端点「无 token=401、普通用户=403、管理员=200」

**结果**：13/13 全部 PASS（详见 `g3_verify.out`）。

## 5. 仅登记、未顺手修复的问题（G3 范畴之外/其他端点）

- `tokens.py`、`token_applications.py`、`chat.py` 中部分端点仍使用 `current_user: str = "anonymous"` 默认匿名（属鉴权规范化遗留），需在后续统一排查，本次不顺手改。
- `reports.py` 报告页 XSS（G4）单独处理。
