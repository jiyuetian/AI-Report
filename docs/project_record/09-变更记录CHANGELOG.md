# 变更日志 CHANGELOG

> 反向时间序（新→旧）。本文件记录「大扫除」全过程与历史根因修复，供接手者追溯。
> 配套：`RULES.md`、`docs/CONVENTIONS.md`、`docs/PROJECT_HEALTH_CHECK.md`。

---

## 2026-09-22 · 大扫除（分支 p0-security-fixes）

### 阶段 2 · 定规范（本次提交）
- 新增 `RULES.md`（根）：提交纪律 / 命名 / 配置 / 数据库铁律 / 鉴权 / 启动 / 测试门槛 / 本机陷阱 / 文档约定。
- 新增 `docs/CONVENTIONS.md`：目录模块地图、LLM 网关、S1–S5 链路、API 契约、dev 密钥方案、提交约定。
- 新增 `CHANGELOG.md`（本文件）。

### 阶段 1 · 遗留问题
- **1.1** `fix(app)`：修正 `main.py` 启动打印误查「仓库根/.env」的假告警，改为二级 dirname 对齐 `backend/.env`。（commit `693d90c`，已 push origin）
- **1.2** 前端守卫越权核查结论：前端 `ProtectedRoute` 仅 UX 门禁（读 `localStorage['user'].roles`），服务端已由 `app.core.security.require_admin` / `require_roles(["admin"])` 在全部 admin 端点强制。**无需改代码**。
- **1.3** 历史分身库清理：
  - 停后端（PID 68992，占用 8000）。
  - 备份真实业务库 `data/duckdb/aibi.db`（134.3 MB，大小校验一致）至 `data/backups/`。
  - 归档 20 个分身 / QA / 验证库到 `data/_archive/`（保留相对结构，避免同名冲突）。
  - 受保护文件 `data/aibi.db`（SQLite 元数据）、`data/duckdb/aibi.db`（业务主库）原样保留。
  - 删除过期 `backend/.backend.pid`。`data/` 现仅余 2 个真实库。
  - 注：归档/备份均在 `backend/data/`（已 gitignore），git 不跟踪，故本步无 commit。

### 阶段 0 · 全项目扫描（只读）
- 新增 `docs/PROJECT_HEALTH_CHECK.md`：命名现状（后端/前端均一致，0 违规）、目录结构、文档散落（10 个根级 .md + 未跟踪诊断残留）、数据库现状（22 个 .db → 澄清 SQLite 元数据与 DuckDB 业务库同名冲突已根治）。

---

## 历史根因修复（已落地，供追溯）

### 2026-09-XX · env 四类根治（commit `718019d`）
- `backend/app/core/config.py`：`DUCKDB_PATH` 改为绝对路径（按 backend 根解析），相对路径不再静默建空库。
- `backend/run_backend.py`：新增 `_validate_duckdb()` 启动 fail-fast（库缺失 → `[DUCKDB-FAIL]` 退出；表=0 → 告警；正常 → 打印 ds_* 表数）。
- 删除旧误导告警（原建议 `export qa_aibi.db`）。
- 同步修正 `.env.example`。

### 关键历史坑（勿复犯）
- **DuckDB 静默建空库**：相对路径 + 绕过 `run_backend.py` 起服务 → 看板「该图表无可绘制数据」。现由绝对路径 + fail-fast 防护。
- **双库错配**：误 `export` 到 `qa_aibi.db` → 新数据集进旧库、老看板读不到表。现启动告警仅对「显式指向非默认仓库」触发。
- **Git-Bash shim 损坏**：`dirname/cd/grep/sleep` 缺失。shell 用 PowerShell 或 `git -C`。
- **Edit/Write 偶发不落盘**：写完 Grep 复核。
