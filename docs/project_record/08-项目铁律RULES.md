# 项目规范 RULES（大扫除后新秩序）

> 适用分支：`p0-security-fixes` 及后续维护分支
> 目的：把本次「最后一次放开权限的大扫除」沉淀为可执行规矩，供后续接手者（含明早新模型）遵循，避免历史坑复发。
> 配套文档：`docs/CONVENTIONS.md`（更细的约定）、`CHANGELOG.md`（变更流水）、`docs/PROJECT_HEALTH_CHECK.md`（现状体检）。

---

## 0. 总则（提交纪律）

- **分支策略**：功能/修复改动开独立分支（如 `p0-security-fixes`），禁止直接推 `main`/`master`。
- **一次只改一类**：安全档（注释/类型/lint/笔误）→ 中风险档（命名/目录/签名对齐）→ 高风险档（API 契约 / 数据模型 / 主库 schema）。禁止一类未完就开另一类。
- **每类独立 commit**：commit message 带 `(scope)` 前缀；高风险改动附回滚说明。
- **push 前必须全绿**：后端 `py_compile` + `/health 200`；前端 `tsc --noEmit` + `5173 200`。任一红则 `git revert`。
- **失败即回退**：测试不通过立即 `git revert` 该 commit，不就地修补掩盖。

---

## 1. 代码命名

| 层 | 约定 | 反例（禁止） |
|----|------|------|
| 后端函数/变量 | `snake_case` | `myFunc` / `userName` |
| 后端类/异常/Pydantic 模型 | `CapWords`（PascalCase） | `login_request` / `userRepo` |
| 前端文件/变量/函数 | `camelCase` | `user_name` |
| 前端组件 | `PascalCase` | `userCard` |

- Pydantic 请求/响应模型统一 PascalCase（`XxxRequest` / `XxxResponse`），这是**正确**写法，不要改成 snake。
- 现状体检（阶段 0）确认：后端 / 前端命名已一致，0 处函数级 camelCase 违规、0 处类名违规、0 处前端 snake 违规。新增代码须维持。

---

## 2. 配置与密钥

- **唯一 `.env` = `backend/.env`**。`app.core.config` 的 `env_file` 已指向它（`_PROJECT_ROOT` = backend/）。
- 切勿新建「仓库根/.env」或 backend 目录外的 `.env` —— 旧 `main.py` 曾误查仓库根/.env 打印假告警，已修（commit `693d90c`）。
- `.env` 永不入库（`.gitignore` 已忽略 `backend/data/` 与 `.env`）。
- 密钥从环境变量 / LLM 网关注入；**禁止硬编码**（含 dev secret）。dev 密钥方案见 `docs/CONVENTIONS.md`。

---

## 3. 数据库（最高风险区）

- **业务主库（DuckDB）**：`backend/data/duckdb/aibi.db`，由 `config.DUCKDB_PATH` 绝对路径指向，488 张 `ds_*` 表。图表数值来源。
- **元数据库（SQLite）**：`backend/data/aibi.db`，存 users / token_quota / chat_session / audit 等。
- **铁律（改 schema / 数据模型 / 主库前）**：
  1. 停后端（`taskkill /PID <pid> /F` 或结束占用 8000 的进程）。
  2. 备份 `aibi.db` + `.wal` 到 `backend/data/backups/`，**校验备份大小 == 源大小**。
  3. 列出全部调用 / 引用点（grep `DUCKDB_PATH` / 相关表名）。
  4. schema 改动带**回滚脚本**（alembic downgrade 或 SQL 回退）。
- **严禁相对路径指向 DuckDB**：历史坑——相对路径依赖 cwd，绕过 `run_backend.py` 起服务时 DuckDB 对不存在路径**静默新建空库**，表现为看板「该图表无可绘制数据」，极难排查。已通过 `DUCKDB_PATH` 绝对路径化 + 启动 fail-fast 根治（commit `718019d`）。
- **schema 变更走 alembic**（`backend/alembic/`），禁止在业务代码里裸 DDL 漂移。
- 测试/分身库统一归档到 `backend/data/_archive/`（已归档 20 个，见 `CHANGELOG.md`），勿留散落。

---

## 4. 鉴权

- 管理端点**服务端**必须 `Depends(require_admin)` 或 `Depends(require_roles(["admin"]))`（`app.core.security`）。
- 前端 `ProtectedRoute`（`frontend/src/App.tsx`）仅做 UX 门禁（读 `localStorage['user'].roles`），**不是安全边界**。任何新增 admin 路由必须双端都有校验。

---

## 5. 启动与运行

- 启动后端：`python run_backend.py`（位于 backend/，会 `chdir` 到 backend/ 根，自带 B5 单实例守卫 + DuckDB 启动 fail-fast 校验）。
- **禁止绕过 `run_backend.py`** 从其他 cwd 直接 `uvicorn app.main:app` —— 会绕过 DuckDB 绝对路径防护与单实例守卫。
- 端口默认 `127.0.0.1:8000`。pidfile = `backend/.backend.pid`（进程退出自动清理）。

---

## 6. 测试门槛（阶段 5 / 阶段 7）

| 项 | 命令 / 判据 |
|----|------|
| 后端语法 | `python -m py_compile` 全量 |
| 后端存活 | `GET /health` → 200 |
| 前端类型 | `npx tsc --noEmit` 零错误 |
| 前端存活 | vite dev `5173` → 200 |
| 核心链路 | `/brain/run` SSE 跑通到生成看板 |
| UI 真验 | Playwright 真截图（注入 localStorage token + user.roles=[admin]） |

---

## 7. 本机已知陷阱（务必先看）

- **Git-Bash shim 损坏**：`dirname` / `cd` / `grep` / `sleep` 等缺失（exit 127）。shell 一律用 **PowerShell** 或 `git -C <绝对路径>`；禁止依赖 `cd`/`wc`/`grep`。
- **Edit / Write 偶发不落盘**：写完务必 `Grep` / `Read` 复核关键改动。
- **DuckDB 静默建空库**：启动 fail-fast 已防，勿关闭该校验；路径永远绝对。
- **PowerShell 工具 stdout 捕获偶发失效**：关键扫描/核对结果写文件后 `Read`，不要只信终端回显。
- **GBK 编码**：`netstat` 等系统命令输出为 GBK，Python 解析用 `decode('gbk','ignore')`。

---

## 8. 文档约定

- 规范/状态/诊断类文档统一入 `docs/`；仓库根仅留 `README.md` + `RULES.md` + `CHANGELOG.md`。
- 一次性调试脚本入 `backend/scripts/_archive/` 或直接删除，禁止留根目录造成误 `git add -A` 入库。
- 变更须记 `CHANGELOG.md`；重大根因修复记 `docs/PROJECT_HEALTH_CHECK.md` 或对应审计文档。
