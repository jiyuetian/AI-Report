# 项目健康体检报告（PROJECT_HEALTH_CHECK）

> 阶段：大扫除 · 阶段 0（全项目扫描，只读）
> 分支：`p0-security-fixes`
> 生成时间：2026-09-22
> 范围：代码命名 / 目录结构 / 文档散落 / 数据库现状（含 SQLite 元数据位置冲突澄清）
> 说明：本报告仅记录现状，不做任何改动。后续阶段按本报告结论逐项处理。

---

## 0. 上下文（已落地根治，非本报告产出）

本仓在 `718019d` 已提交 4 条根治（env 类），与本报告直接相关：

1. `backend/app/core/config.py`：`DUCKDB_PATH` 改为绝对路径（按 backend 根解析），相对路径不再静默建空库。
2. `backend/run_backend.py`：新增 `_validate_duckdb()` 启动 fail-fast（库不存在 → `[DUCKDB-FAIL]` 退出；表=0 → 告警；正常 → 打印 ds_* 表数）。
3. 删除 `run_backend.py` 中误导告警（原建议 `export qa_aibi.db`）。
4. `.env.example` 同步修正。

---

## 1. 代码命名现状

### 1.1 后端 Python（248 个 .py 文件，全部位于 `backend/`）

| 维度 | 约定 | 扫描结果 | 结论 |
|------|------|----------|------|
| 函数名 `def` | `snake_case` | 0 处 camelCase / 大写开头违规 | ✅ 一致 |
| 类名 `class` | `CapWords`（PascalCase） | 0 处 snake_case / 小写开头违规 | ✅ 一致 |
| Pydantic 模型 | `CapWords`（如 `LoginRequest`/`ChatMessageRequest`） | 全部合规 | ✅ 正确 |

- 扫描覆盖 `backend/**/*.py`（排除 `.pytest_cache`/`__pycache__`），逐行匹配 `def`/`class` 顶层声明。
- **澄清**：初版扫描曾报 125 处「camelCase 违规」，经复核全部为 Pydantic `class` 模型名（`LoginRequest`、`ConfigResponse` 等），属 PascalCase 正确写法，已排除。真实函数级违规为 **0**。
- 注意：局部变量 / 内部赋值命名未穷举扫描，建议阶段 4 命名子类做一轮 spot-check（若发现 camelCase 局部变量再修）。

### 1.2 前端 TS/TSX（`frontend/src/` 共 36 个源文件）

| 维度 | 约定 | 扫描结果 | 结论 |
|------|------|----------|------|
| 文件名 | `camelCase` / `kebab` | 0 个 snake_case 文件名 | ✅ 一致 |
| 标识符（`const`/`let`/`function`） | `camelCase` | 0 处 snake_case 标识符 | ✅ 一致 |
| 文件构成 | — | 28 × `.tsx`、8 × `.ts`、19 × `.css` | — |

- 前端命名规范已严格遵守，阶段 4 命名子类在前端侧工作量≈0。

**阶段 0 命名结论**：后端 / 前端命名约定均已落地，无系统性命名债。阶段 4「命名档」实际工作量极低（仅可能的局部变量 spot-check），可并入安全档一并处理。

---

## 2. 目录结构现状

```
AI-Report/
├── README.md                      # 唯一规范入口文档
├── <10 个根级 .md 状态/诊断文档>   # 见 §3，散落待整理
├── backend/
│   ├── alembic/                   # DB 迁移（schema 变更入口，阶段4 schema 子类相关）
│   ├── app/                       # 主代码（core/api/models/services/brain…）
│   ├── data/                      # 运行时数据（见 §4，已被 .gitignore 忽略）
│   │   └── duckdb/aibi.db         # 真相业务库（DuckDB）
│   ├── logs/                      # 日志（忽略）
│   ├── scripts/                   # 后端脚本（含 _diag_* / _admin_debug 等残留，待清）
│   ├── temp/                      # 临时
│   ├── tests/                     # 测试
│   └── .pytest_cache/             # 忽略
├── frontend/
│   ├── public/
│   └── src/                       # 28 tsx / 8 ts / 19 css
└── docs/                          # 已存在（本报告落位此目录）
```

观察：
- `backend/scripts/` 与根级 `scripts/`、`defect_fix_evidence/` 三处并存调试/证据脚本，无统一入口约定。
- `docs/` 已存在但内容稀疏；本报告及后续 RULES/CONVENTIONS/CHANGELOG/ISSUES/handover 均归入 `docs/`。

---

## 3. 文档散落现状

### 3.1 根目录 .md（10 个，项目级）

| 文件 | 性质 |
|------|------|
| `README.md` | 规范入口（保留） |
| `PROJECT_STATUS.md` | 项目状态（保留/移 docs） |
| `AI_DIALOG_AUDIT.md` | AI 对话审计 |
| `FIX_SUMMARY.md` | 修复汇总 |
| `UI_FIX_SUMMARY.md` | UI 修复汇总 |
| `UI_AND_AI_DIAGNOSIS.md` | UI/AI 诊断 |
| `NEW_ISSUES_DIAGNOSIS.md` | 新问题诊断（未跟踪） |
| `NEW_ISSUES_FIX.md` | 新问题修复（未跟踪） |
| `OPEN_QUESTIONS.md` | 开放问题 |
| `LLM_MULTIKEY_PLAN.md` | LLM 多 key 方案 |

→ 建议：状态/诊断类统一移入 `docs/`（保留 `README.md` 在根）。

### 3.2 未跟踪诊断残留（git status，待阶段 3 清理 / 忽略）

- 根级：`NEW_ISSUES_DIAGNOSIS.md`、`NEW_ISSUES_FIX.md`、`_tsc_out.txt`、`defect_fix_evidence/`（含 `final_fixes/diff_*.txt`、`ui_shots_20260922/`、`fixes/*`）。
- `backend/`：`*.env.bak`、`*.env.bak_xunfei`、`probe_out.txt`、`.backend.pid`、`magic1.dll`、`verify_n1_debug.py`、`verify_n1_realrun.py`、`scripts/_admin_debug.py`、`scripts/_diag_api.py`、`scripts/_diag_historical.py`、`scripts/_diag_tables.py`、`scripts/_run_probe.py`、`scripts/_ui_probe.py`、`scripts/_ui_shots.py`、`scripts/_verify_ui_api.py`。

→ 风险：上述文件 **未** 被 `.gitignore` 覆盖，若执行 `git add -A` 会被误入库。阶段 3 需：可删除的一次性脚本直接删；证据类移 `backend/scripts/_archive/` 或 `docs/`；补 `.gitignore` 规则。

---

## 4. 数据库现状（22 个 .db，含 SQLite 元数据冲突澄清）

### 4.1 真相库（2 个，需保留）

| 文件 | 引擎 | 大小 | 用途 |
|------|------|------|------|
| `backend/data/duckdb/aibi.db` | DuckDB | ~134 MB | **业务主库**（488 张 `ds_*` 表）。`config.DUCKDB_PATH` 已显式指向此（718019d） |
| `backend/data/aibi.db` | SQLite | ~6.1 MB | **元数据库**（users / token_quota / chat_session 等） |

### 4.2 历史路径冲突澄清（关键）

仓内曾并存两个同名 `aibi.db`：

- `backend/data/aibi.db` → **SQLite**（元数据）
- `backend/data/duckdb/aibi.db` → **DuckDB**（业务）

旧 `run_backend.py` 在 DuckDB 路径使用相对解析时，若目标不存在会**静默新建空库**；且旧告警误导建议 `export qa_aibi.db`。`718019d` 已根治：`DUCKDB_PATH` 绝对路径化 + 启动 fail-fast + 告警修正。当前二者职责清晰、无冲突。

### 4.3 克隆 / QA / 验证库（20 个，待阶段 1.3 归档）

> 全部位于 `backend/data/`，已被 `.gitignore`（`backend/data/`）忽略，**不会入库**，可安全归档/删除。

按来源分组：

- `backend/data/`（一级）：
  - `aibi_cap_d29372b3.db` (~5.2 MB)
  - `aibi_glm.db`、`aibi_glm_d911b4ff.db`、`aibi_glm_1adf0d3b.db`、`aibi_glm_99b4c369.db` (4 × ~5.2 MB)
  - `aibi_ui_742c4187.db`、`aibi_ui_ui3.db` (2 × ~5.2 MB)
  - `qa_aibi.db` (~0.7 MB)、`qa_l1test.db` (~0.3 MB)
- `backend/data/duckdb/`（一级）：
  - `aibi_cap_d29372b3.db` (~1.3 MB)、`aibi_glm.db` (~4.5 MB)、`aibi_ui_742c4187.db` (~1.3 MB)、`aibi_ui_ui3.db` (~6.0 MB)
  - `qa_aibi.db` (~9.8 MB)、`qa_aibi_g21.db` (~12 KB)
- `backend/data/qa_g3*/qa_g3_verify.db`（5 个，各 ~0.3 MB）：
  - `qa_g3/`、`qa_g3_58940/`、`qa_g3_61444/`、`qa_g3_61776/`、`qa_g3_68944/`

→ 阶段 1.3 动作：停后端 → 备份 `duckdb/aibi.db` + `.wal` → 将上述 20 个分身库整体移入 `backend/data/_archive/`（保留可恢复）。

---

## 5. 遗留问题预览（移交阶段 1，本报告不处理）

| 项 | 位置 | 现状 | 移交 |
|----|------|------|------|
| 假告警 | `backend/app/main.py:97` | 计算 `_env_path` = **仓库根**/.env（三次 `dirname` 上溯），实际 pydantic-settings 从 `backend/.env` 加载；打印的「.env 已加载」状态误导 | 阶段 1.1：改为检查 `backend/.env` 或移除该打印 |
| 前端守卫越权 | 前端权限判断（读 `localStorage['user'].roles`） | 待查后端是否真校验 | 阶段 1.2：仅查给结论 |
| 分身库清理 | `backend/data/` 20 个克隆/QA 库 | 已列清单（§4.3） | 阶段 1.3：停服 + 备份 + 归档 |

---

## 6. 阶段 0 结论

- ✅ 命名规范：后端 / 前端均一致，无系统性命名债。
- ⚠️ 目录：调试/证据脚本三处并存，缺统一入口约定（阶段 3 整理）。
- ⚠️ 文档：10 个根级 .md 散落 + 未跟踪诊断残留可被误入库（阶段 3 + .gitignore）。
- ✅ 数据库：真相库清晰，历史同名冲突已根治（718019d）；20 个分身库待归档（阶段 1.3）。
- 下一步：进入阶段 1（遗留问题修复：假告警 / 守卫 / 分身库）。
