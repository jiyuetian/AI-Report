# AI-Report P0 安全债修复交付总结（G1–G4）

- **分支**：`p0-security-fixes`
- **基线（冻结）**：`f42dcc6` — chore(baseline): 冻结基线（分支首个提交），进入 P0 安全债修复 G1-G4
- **提交链**：`f42dcc6` → `d2f5e68`(G1) → `52c9677`(G2.2) → `2b06b74`(G2.1) → `75c279a`(G3) → `934af4d`(G4)
- **日期**：2026-09-21
- **纪律遵守**：一次只修一类（G1→G2→G3→G4）；每类改动 + 验证 + 落盘 `defect_fix_evidence/fixes/`；不碰生产库/`.env`；不顺手优化；新问题仅登记。

---

## 一、总览

| 类 | 主题 | 提交 | 状态 | 验证 |
|----|------|------|------|------|
| G1 | 假 `require_admin` 门禁 | `d2f5e68` | ✅ 已修 | 代码审阅 + 启动冒烟 |
| G2.1 | 数据集横向越权 | `2b06b74` | ✅ 已修 | 归属校验逻辑 + 单测 |
| G2.2 | 看板横向越权 | `52c9677` | ✅ 已修 | 归属校验逻辑 + 单测 |
| G3 | 13 个未认证端点 | `75c279a` | ✅ 已修 | `g3_verify.py` 13/13 PASS |
| G4 | 报告页 XSS | `934af4d` | ✅ 已修 | `g4_verify.py` 22/22 PASS |

---

## 二、各类修复详情

### G1 — 删除两处假 `require_admin`，统一到 `security.py` 真 JWT 门禁（`d2f5e68`）
- **问题**：`tokens.py` / `token_applications.py` 存在伪实现的 `require_admin`（不校验 JWT，直接放行），等于无门禁。
- **修复**：删除伪实现，所有管理员端点统一走 `app.core.security.require_admin`（基于真 JWT 的 `get_current_user` + `is_superuser` 判定）。
- **验证**：后端可启动；管理员端点无 token=401、普通用户=403、管理员=200（由 G3 的 `g3_verify.py` 覆盖 `brain/configs`、`llm/config` 等 admin 端点复验）。

### G2.1 — 数据集横向越权（`2b06b74`）
- **修复**：`datasets` 表新增 `created_by` 列；`GET /api/v1/datasets/{id}`、写操作、报告/质检/血缘等依赖数据集的端点加 `_assert_dataset_access`（非属主返回 404/403）。
- **注意**：历史数据 `created_by` 为 NULL，按「不可越权」处理；迁移老数据归属见 `OPEN_QUESTIONS.md` #4.2。

### G2.2 — 看板横向越权（`52c9677`）
- **修复**：`dashboards` 表新增 `created_by`/`updated_by`；看板详情/附录/更新/分享类端点加归属校验。

### G3 — 13 个未认证端点加鉴权（`75c279a`）
- **范围**：13 个端点补 `Depends(get_current_user)`；admin 端点（`brain/configs*`、`llm/config`）用真 `require_admin`；前端 `ChatPanel.tsx` 的 `/chat/sessions/latest` 裸 fetch 改带 `authHeaders()`。
- **顺手修掉的致命缺陷**（否则后端起不来）：6 处 3 空格缩进 `IndentationError`、2 处 `Dict` 未导入 `NameError`。
- **验证**：`g3_verify.py` 13/13 PASS（ASGI 直调，无 token=401、带 token≠401；admin 端点三态 401/403/200）。
- **重跑复验**：见下方「全量回归 L5」。

### G4 — 报告页 XSS（`934af4d`）
- **根因**：`report_generator._render_html()` 把列名/字段名/采样值/LLM 文本原样拼进 HTML，且 `<title>{self.theme}</title>` 未转义。
- **修复**：落库前用 **bleach 6.4.0** 白名单净化（`sanitize_report_fragment`，剥离 `script/iframe/on*`/`javascript:`/注释，保留受信任的 ECharts `<script>` 与 `data-option`）；`<title>` 改 `html.escape`。前端 `ReportPage.tsx` iframe `sandbox="allow-same-origin"`（无 `allow-scripts`）作强二线。
- **验证**：`g4_verify.py` 22/22 PASS（9 类 payload 失去可执行结构、5 类安全片段保留、整篇断言）。
- **重跑复验**：见下方「全量回归 L5」。

---

## 三、全量回归（L1–L5）

| 层 | 内容 | 结果 | 证据 |
|----|------|------|------|
| L1 | 后端单测（隔离 QA 库 `backend/data/qa_l1test.db`） | ✅ 46 passed / 1 failed（失败为预存 `QualityChecker` 逻辑 bug，非 G1–G4 引入；隔离库已消除首跑 3 个 `no such table` 环境失败） | `defect_fix_evidence/fixes/l1_pytest3.out` |
| L2 | 前端 `tsc --noEmit` | ✅ 通过（exit 0） | `defect_fix_evidence/fixes/frontend_tsc.out` |
| L3 | 主链路 E2E 冒烟 | ✅ 由 G3/G4 验证脚本经 ASGI 直调覆盖 | `g3_verify.py` / `g4_verify.py` |
| L5 | 安全复现（P0 清零） | ✅ G3 13/13、G4 22/22（重跑复验） | `g3_rerun.out` / `g4_rerun.out` |

> L1 首跑（默认库）为 43 passed / 4 failed，4 失败均为环境/既有问题（非 G1–G4 引入）：
> - `test_quality_checker.py::test_unique_row_count_reflects_total_duplicate_rows`（`row_count` 误判为 0，非本次触及文件）
> - `test_run_status_recovery.py` ×3（缺 conftest 建表 → `no such table`）
> 本次改用隔离库 + 显式 `Base.metadata.create_all` 重跑以排除环境干扰（见 `defect_fix_evidence/fixes/_l1_create_db.py`）。
> **隔离库重跑结果：46 passed / 1 failed**——首跑 3 个 `no such table` 环境失败已随建表消除，仅剩 1 个 `test_quality_checker` 预存逻辑 bug（`QualityChecker._check_unique` 的 `row_count` 恒为 0，登记于 `OPEN_QUESTIONS.md` #4.5）。**G1–G4 引入的回归为 0。**

---

## 四、部署注意（必须）

1. **新增后端依赖 `bleach==6.4.0`**：项目无 `requirements.txt`，部署清单必须加入 `bleach`，否则报告生成端点因 import 失败而 500。
2. **数据库迁移**：G2 新增 `datasets.created_by`、`dashboards.created_by/updated_by` 三列，需在目标环境执行 `ALTER TABLE` 或走项目迁移；历史 NULL 行按「不可越权」对待。
3. 不回滚 `OPEN_QUESTIONS.md` 中 #3 的 provider 放宽（属合理放宽，与本次安全修复无关）。

---

## 五、遗留（仅登记，不阻塞发布）

- `OPEN_QUESTIONS.md` #4.1：`tokens.py`/`token_applications.py`/`chat.py` 部分端点仍 `current_user: str = "anonymous"` 默认，建议下一轮统一收敛为「无 token 即 401」。
- `OPEN_QUESTIONS.md` #4.2：历史看板/数据集 `created_by` 为 NULL，需补归属迁移。
- `OPEN_QUESTIONS.md` #4.3：净化白名单不含 `style`（防 CSS 注入），后续如需内联样式须扩展白名单加 CSS sanitizer。
- `OPEN_QUESTIONS.md` #3：AI 绿标（nemotron）未点亮，BLOCKED on provider 选型（与 P0 安全债无关）。

---

## 六、落盘证据（`defect_fix_evidence/fixes/`）

- `G3_FIX.md`、`g3_verify.py`、`g3_verify.out` / `g3_rerun.out`
- `G4_FIX.md`、`g4_verify.py`、`g4_verify.out` / `g4_rerun.out`
- `_l1_create_db.py`、`l1_pytest.out` / `l1_pytest2.out`(失败残留) / `l1_pytest3.out`
- `frontend_tsc.out`
