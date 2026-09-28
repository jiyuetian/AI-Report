# NAMING.md — 命名规范（后端 / 前端 / API / 库表）

> 配套 `01-代码规范与约定.md` / `10-命名目录规范CONVENTIONS.md`。本文收敛「命名」这一维，给正反例，供 PR 自查与模型接手参考。
> 约定优先于习惯；与本文件冲突时以本文件为准，并回提 PR 修正本文件。

---

## 0. 语言与命名法对照

| 层 | 语言 | 命名法 | 示例 |
|---|---|---|---|
| 后端 Python | py | `snake_case` 变量/函数/模块；`PascalCase` 类；`UPPER_SNAKE` 常量 | `run_backend.py` / `def check_feasibility` / `class FeasibilityChecker` / `LLM_PROVIDERS` |
| 前端 TS/TSX | ts/tsx | `camelCase` 变量/函数/hook；`PascalCase` 组件/类型/接口；`UPPER_SNAKE` 常量 | `const [skills,setSkills]` / `function SkillPanel` / `interface SkillMetaLite` / `API_BASE` |
| API 路径 | — | `kebab-case` 路径段；资源用名词复数 | `/api/v1/datasets`、`/api/v1/brain/run` |
| 请求/响应体 | json | `snake_case` 字段（与 Pydantic 模型一致） | `{"dashboard_id": "..."}`、`generation_mode` |
| 库表 | sql | `snake_case`；业务表 `ds_` 前缀；看板 id `dash_` 前缀 | `ds_04d68399_*`、`dash_04d68399_50adf8` |

---

## 1. 后端 Python

- 模块/文件：`snake_case.py`，动词性模块用动名词（`feasibility_checker.py`）；启动器 `run_*.py`。
- 函数：`snake_case`，意图清晰、不带类型后缀（`check_feasibility` ✅ / `feasibilityCheck` ❌ / `do_check` ❌）。
- 类：`PascalCase` + 业务含义（`FeasibilityChecker`、`LLMGateway`）。
- 常量：`UPPER_SNAKE`（`LLM_PROVIDERS`、`BRAIN_AI_CHOICE_TIMEOUT`）。
- 私有辅助：模块级 `_func`（单下划线）；类内 `_attr`。
- 异常：`XxxError` / `XxxException`。

**正反例**
```
✅ def _check_field_existence(message, field_names) -> Optional[Dict]:
✅ class FeasibilityChecker:
❌ def CheckField(message):        # 类/函数 Pascal/动词混用
❌ LLMProviders = [...]            # 常量未全大写下划线
```

---

## 2. 前端 TS / TSX

- 组件文件：`PascalCase.tsx`，与默认导出组件同名（`SkillPanel.tsx` → `export function SkillPanel`）。
- 工具/类型文件：`camelCase.ts`（`request.ts`、`themeContext.ts`）。
- 变量/函数：`camelCase`；React 状态用 `[x, setX]`。
- Hook：`useXxx`（`useNavigate`、`useState`）。
- 接口/类型：`PascalCase`（`SkillMetaLite`、`ChatMessageRequest`）。
- 事件处理：`handleXxx` / `onXxx`（`handleAbandon`、`onChange`）。

**正反例**
```
✅ const [skills, setSkills] = useState<SkillMetaLite[]>([])
✅ export function SkillPanel() { ... }
❌ const SkillsList = []          # 变量用 Pascal
❌ function skill_panel() { }      # 组件未 Pascal + 文件未对齐
```

### 2.1 API 调用（强制统一封装）

- **所有 HTTP 调用走 `frontend/src/utils/request.ts` 的 `http`（`get/post/put/delete/patch`）或 `request()`**，禁止裸 `fetch`（eslint `no-restricted-globals` 已禁）。
- 鉴权头由 `request()` 自动注入（`Authorization: Bearer <token>`），无需各组件手动 `authHeaders()`。
- 401 由 `request()` 统一兜底（清 token + 跳登录）。
- ✅ `http.get<{skills?:SkillMetaLite[]}>('/skills')`
- ❌ `fetch(`${API_BASE}/skills`, { headers: authHeaders() })`

> 注：`10-命名目录规范CONVENTIONS.md` §4 写的是 `http.ts`，实际文件为 `utils/request.ts`（同一封装），以代码为准。

---

## 3. API 契约

- 前缀统一 `/api/v1/`；新增端点进 `backend/app/api/<domain>.py`，用 `APIRouter(prefix="/<domain>")`。
- 路径段 `kebab-case`、资源名词复数：`/datasets`、`/dashboards`、`/brain/run`、`/chat/message`。
- 方法语义：`GET` 查、`POST` 建、`PUT/PATCH` 改、`DELETE` 删。
- 请求/响应体：Pydantic 模型（`PascalCase` 模型名，`snake_case` 字段）；禁止裸 `dict` 进出。
- 改后端鉴权端点（增 `Depends(get_current_user)` / `require_admin`）**必须同步改所有前端调用点**（统一走 `request.ts`，自动带 token）。
- 路径参数/查询参数命名 `snake_case`：`<dashboard_id>`、`?dataset_id=`。

**正反例**
```
✅ @router.post("/brain/run")  async def brain_run_pipeline(req: BrainRunRequest)
✅ GET /api/v1/dashboards/{dashboard_id}
❌ @router.post("/BrainRun")              # Pascal 路径
❌ GET /api/v1/dashboard/getById?id=1     # 动词 + 驼峰查询
```

---

## 4. 库表与 ID 命名

- 业务数据表（DuckDB）：`ds_<8位哈希>_<序号>`（如 `ds_04d68399_*`），由上传数据集自动生成，禁止手改表名。
- 元数据表（SQLite `aibi.db`）：`snake_case` 名词，`dashboard` / `dataset` / `chat_session` / `chat_message` / `dashboard_version` / `analysis_template`。
- 看板业务 id：`dash_<8位哈希>_<6位后缀>`（如 `dash_04d68399_50adf8`），全局唯一。
- 字段：`snake_case`；布尔用 `is_/has_` 前缀（`is_legacy`、`ai_participated`）。
- 版本快照表：`dashboard_versions`（存 `config_snapshot`，可作看板还原源）。

**正反例**
```
✅ table ds_04d68399_a1b2c3   col generation_mode
✅ dashboard.id = "dash_04d68399_50adf8"
❌ table DS1 / t_user1          # 无前缀、无哈希
❌ col genMode / isAI          # 驼峰
```

---

## 5. 目录与临时产物

- 一次性诊断脚本：`backend/scripts/_archive/` 或删；根目录禁止留 `_*.py` / `_*.txt` / `defect_fix_evidence/`（防 `git add -A` 误入库）。
- 归档优先：`_archive/`（日志/历史库/旧报告），删前先移出项目到外部 `_trash_*` 可恢复。
- 前端 `dist/` 由构建生成，gitignore；调试截图 `dashboard_*.png` gitignore。
- 治理文档入 `docs/project_record/`，编号文件（00~14）为权威索引，新文档优先归位此处而非散落根目录。

---

## 6. 提交 / 分支

- 分支：`p0-<topic>` / `fix-<topic>` / `feat-<topic>`。
- commit：`<type>(<scope>): <简述>`；type ∈ {fix, feat, docs, refactor, chore, test}。
- 高风险 commit body 附：①影响面 ②备份/回滚 ③测试。
- 每个 commit 的 diff 应可在报告/PR 全文查看（红线要求）。
