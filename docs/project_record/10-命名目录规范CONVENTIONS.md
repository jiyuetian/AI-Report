# 约定细则 CONVENTIONS（大扫除后新秩序）

> 与 `RULES.md` 配套，提供更细的工程约定与模块地图。新人 / 新模型接手前先读 `RULES.md` 与本文。

---

## 1. 目录与模块地图

```
AI-Report/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI 入口 + lifespan（含 .env 加载提示，已修 693d90c）
│   │   ├── core/
│   │   │   ├── config.py      # pydantic-settings；DUCKDB_PATH 绝对路径；env_file=backend/.env
│   │   │   ├── security.py    # create_access_token / require_admin / require_roles / get_current_user
│   │   │   └── database.py    # SQLAlchemy async engine（SQLite 元数据）
│   │   ├── api/               # 路由层（admin/brain/brain_run_sse/chat/dashboards/datasets/llm/tokens…）
│   │   ├── models/            # ORM 模型（User/File/Dataset/.../AnalysisTemplate）
│   │   └── services/brain/    # S1-S5 大脑执行链路（质检→清洗→生成看板→附录→血缘）
│   ├── alembic/               # schema 迁移（唯一定制 schema 入口）
│   ├── data/
│   │   ├── duckdb/aibi.db     # 业务主库（DuckDB，488 张 ds_* 表）★受保护
│   │   ├── aibi.db            # 元数据库（SQLite）★受保护
│   │   ├── _archive/          # 已归档的历史分身/QA 库（20 个，勿动）
│   │   └── backups/           # 主库手动备份（含 .wal）
│   ├── scripts/               # 后端脚本（一次性诊断脚本请入 _archive/）
│   └── run_backend.py         # 启动器（chdir backend/ + B5 守卫 + DuckDB fail-fast）
└── frontend/
    └── src/
        ├── App.tsx            # 路由 + ProtectedRoute（前端 admin 门禁，仅 UX）
        ├── views/             # 页面（admin/ 管理后台等）
        └── ...                # 28 tsx + 8 ts + 19 css（camelCase 约定）
```

---

## 2. LLM 网关约定

- 主用模型：`kimi-k3`，经商汤 SenseNova 聚合网关 `https://token.sensenova.cn/v1`（OpenAI 兼容单 key 路由）。
- 网关要求 `business_type=chat`；kimi 系列仅允许 `temperature=1`（否则 400）。
- 多 key 容错：`LLM_PROVIDERS`（JSON 数组） failover；未设则回退单 key（`LLM_API_KEY/BASE_URL/MODEL`）。
- 已弃用：NVIDIA nemotron（重型图表 JSON 180s 不返回）、Agnes 免费版（持续 429）、deepseek-v4-flash（间歇 429）。
- 出口代理：本机 `7897`（Clash）；`run_backend.py` 在 import 网络库前强制注入，可用 `LLM_PROXY` 覆盖。

---

## 3. 大脑执行链路（S1–S5）

- S1 上传 → S2 目标/意图（默认走 LLM，`BRAIN_S2_USE_LLM=True`）→ S3 图表生成（LLM 决策 + 规则兜底）→ S4 看板拼装 → S5 多模态视觉抽检。
- 绿标（AI 生成徽标）判定链：`brain_run_sse.py` 写 `generated_by=llm` / `ai_participated` / `generation_mode=ai` → 前端 `LoadingPage.tsx` 渲染绿色「AI 生成」Tag。
- S3 单任务 Token 预算：`BRAIN_TASK_TASK_TOKEN_BUDGET`（默认 8000），达 80% 告警、100% 熔断跳过后续 LLM。

---

## 4. API 契约约定

- 路由前缀 `/api/v1/...`；请求 / 响应体用 Pydantic 模型（PascalCase 名）。
- 新增 / 修改端点：必须同步更新**所有调用点**（前端 `http.ts` 的 `request()` 封装、测试用例）。
- 公开 / 非公开端点分类见安全审计文档；未认证端点补 `Depends(get_current_user)` 或 `require_admin`（见 `RULES.md §4`）。

---

## 5. dev 密钥方案（不写码）

- 禁止在代码里硬编码任何 `sk-*` / `api_key` 字面量。
- 本地值只进 `backend/.env`（已 gitignore）；CI / 路演通过环境变量或密钥管理器注入。
- 若需临时换网络：设环境变量 `LLM_PROXY`（自定义键，不被工具 shell 锁定）。

---

## 6. 提交 / 分支约定

- 分支命名：`p0-<topic>` / `fix-<topic>` / `feat-<topic>`。
- commit 规范：`<type>(<scope>): <中文/英文简述>`；type ∈ {fix, feat, docs, refactor, chore, test}。
- 高风险改动 commit body 附：①影响面 ②备份/回滚方式 ③测试结果。
- 见 `CHANGELOG.md` 历史样例。

---

## 7. 测试数据 / 调试产物

- 上传样例存 `backend/data/uploads/`（gitignore）。
- 一次性诊断脚本（`_diag_*` / `_verify_*` / `_probe*`）入 `backend/scripts/_archive/` 或删；根目录禁止留 `_*.py` / `_*.txt` / `defect_fix_evidence/`（补 `.gitignore`）。
- 浏览器截图调试产物（`dashboard_*.png`）已 gitignore。
