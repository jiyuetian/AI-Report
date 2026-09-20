# AI 快速 BI 报表工具（AI-Report）

> 上传数据 → AI 自动理解 → 生成可交互看板 + 结构化报告 + 对话式分析的一体化智能 BI 工具。

---

## 1. 项目简介

AI-Report 面向「非技术用户也能用自然语言做数据分析」的场景：用户上传一份 Excel/CSV/文档，系统通过内置的「AI 大脑」流水线自动完成数据理解、质量探查、图表选型、报告撰写，并支持在对话中持续追问、对看板做增删改。

核心卖点：
- **零 SQL 分析**：用对话驱动数据探索，模型自动生成图表与洞察。
- **质量前置**：8 类数据质量问题在生成看板前被自动探查并提示。
- **异常不崩**：AI 生成链路（S1–S5）单步失败不影响整体，前端收到可读错误而非白屏。
- **可审计**：数据血缘、Prompt 中心、操作审计全程留痕。

---

## 2. 技术栈与架构

| 层 | 技术 |
|---|---|
| 前端 | React 18 + TypeScript + Vite + Ant Design 5 + ECharts 5 + Zustand + React Router |
| 后端 | FastAPI（Python 3.12）+ Uvicorn + SQLAlchemy 2.0（异步）|
| 业务元数据 | PostgreSQL（主）/ SQLite（开发 fallback，`DB_FALLBACK_SQLITE=true`）|
| 分析引擎 | DuckDB（列式分析，数据落 `data/duckdb/aibi.db`）|
| 缓存/队列 | Redis（可选，未配置时部分能力降级）|
| 大模型 | OpenAI 兼容协议（默认 Moonshot/Kimi，可换 DeepSeek、讯飞星火等）|

```
┌────────────┐     /api/v1      ┌──────────────────────────┐
│  Frontend  │ ───────────────► │  FastAPI (port 8000)      │
│  React+Vite│                  │  ├─ auth / upload / data  │
│  (port5173)│ ◄──── SSE ────── │  ├─ brain_run_sse (S1-S5) │
└────────────┘                  │  ├─ chat (对话式分析)     │
                                 │  └─ quality / dashboard   │
                                 └───────────┬──────────────┘
                                             │
                             ┌───────────────┼────────────────┐
                             ▼               ▼                ▼
                        PostgreSQL       DuckDB          LLM (HTTP)
```

---

## 3. 功能概要

| 模块 | 说明 |
|---|---|
| **数据接入** | 上传 Excel/CSV/Word/PDF，自动编码探测、字段类型识别、落 DuckDB。 |
| **质量探查** | 8 类质检（空值/格式/唯一性/范围/逻辑/编码/及时性/分布），给出修复建议。 |
| **智能看板** | AI 大脑自动选图（≥6 张且字段全可解析），支持对话式增删改图表。 |
| **报告生成** | 多章节结构化报告（封面/摘要/方法/维度分析/结论），内嵌 ECharts 图。 |
| **对话分析** | 基于看板上下文的自然语言问答，支持执行「加图/删图」等动作。 |
| **数据血缘** | 看板字段 ↔ 原始数据表的来龙去脉自动构建。 |
| **Prompt 中心** | 管理员可在线编辑各阶段提示词并热生效。 |
| **操作审计** | 登录、改密、动作执行等关键操作留痕。 |

---

## 4. 设计方案概要

### 4.1 AI 大脑流水线（S1–S5，异常隔离）

| 阶段 | 职责 | 异常流处理 |
|---|---|---|
| S1 理解 | 解析数据语义、识别指标与维度 | 失败标记 `stage_status=failed` + 中文消息，降级不阻断 |
| S2 目标 | 生成分析目标（默认规则引擎，可开 LLM）| 同上 |
| S3 图表 | 图表选型策略（全字段可解析 + 数量下限）| 同上；0 可视化字段返回 `no_chartable_fields` + 建议 |
| S4 评分 | 看板质量评分 | 同上 |
| S5 报告 | 多模态抽检 + 报告撰写 | 同上；5% 抽检兜底 |

每个阶段独立 `try/except`，失败写入 `_RUN_STATUS[run_id]["stage_errors"]` 并随 `/status` 回传；最外层汇总生成「分析已完成但存在失败步骤」的面向用户提示。

### 4.2 六层数据架构（L0–L5）

| 层 | 表命名 | 说明 |
|---|---|---|
| L0 原始 | `ds_{id}` | 原始落库 |
| L1 规整 | `ds_{id}_norm` | 类型/编码规整 |
| L2 清洗 | `ds_{id}_cleaned` | 空值/异常处理后 |
| L3 加工 | `ds_{id}_processed`（灰色预留）| 业务派生，非强制 |
| L4 聚合 | `ds_{id}_agg` | 预聚合加速 |
| L5 输出 | `output` 命名约定 | 对外服务结果 |

### 4.3 8 类质量探查
`NULL / FORMAT / UNIQUE / RANGE / LOGIC / CODE / TIMELINESS / DISTRIBUTION`，覆盖类型一致性、未来/过早日期、IQR×3 离群等。

### 4.4 图表选型策略（S3 不变量）
- 字段不可解析的图表一律剔除；
- `chart_count ≥ min(6, 可支撑图数)`；
- 纯文本数据集标记 `no_chartable_fields=True` 并给出「补充数值/分类/日期字段」建议。

### 4.5 可行性检查与引导话术（PRD 4.2）
对话中执行动作前做可行性检查：字段缺失 / 粒度不匹配 / 图表超限(≥10) / 删除唯一图 均 `blocking` 并返回引导话术；用户显式 `override` 时降级为可行（用户优先级最高）。

### 4.6 前端渲染加固
- 饼图 `legend.type:'scroll'` + 横向底部，避免多分类文字重叠；
- 报告内嵌 bar/line 图 `grid.containLabel:true`，轴标签不再裁切。

---

## 5. 环境要求

- Python ≥ 3.12（开发用 3.12）
- Node.js ≥ 18（前端用 Vite 5，建议 20+）
- PostgreSQL 12+（可选，不装则自动用 SQLite fallback）
- Redis（可选）

---

## 6. 快速启动

### 6.1 后端

```bash
cd backend

# 1) 安装依赖（建议使用虚拟环境）
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2) 配置环境变量
cp .env.example .env
#   编辑 .env：填 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL，按需改 DATABASE_URL

# 3) 数据库（PostgreSQL 场景需先建库；SQLite fallback 无需）
#    PostgreSQL: createdb aibi  (或执行 alembic upgrade head)
#    应用启动时 DEBUG=true 会自动 create_all，无需手动迁移

# 4) 启动
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

> 验证：`curl http://127.0.0.1:8000/api/v1/datasets/_internal/duckdb/tables` 返回 200；Swagger 文档：`http://127.0.0.1:8000/docs`

### 6.2 前端

```bash
cd frontend
npm install
npm run dev          # 默认 http://localhost:5173 ，已代理 /api → :8000
```

### 6.3 一键启动脚本（Windows）

项目根提供 `start_dev.ps1`，一键拉起前后端：

```powershell
# 在项目管理器以「用 PowerShell 运行」或终端执行：
.\start_dev.ps1
```

脚本会分别在 `backend`、`frontend` 目录后台启动 Uvicorn 与 Vite，日志见各自窗口。
（Linux/macOS 可类比写成 `start_dev.sh`，命令同上。）

---

## 7. 账户与登录（重要）

**应用没有内置默认账号/密码。** 密码以 bcrypt 哈希存储在数据库 `users` 表，登录接口仅 `/api/v1/auth/login`，无开放注册接口。

- **首次部署**需要创建一个管理员账号，使用项目提供的脚本：
  ```bash
  cd backend
  python scripts/init_admin.py            # 默认 admin / Admin@123456
  python scripts/init_admin.py 用户名 密码  # 自定义
  ```
- 前端登录页 `http://localhost:5173` → 输入用户名/密码即可；「忘记密码」走手机号验证码流程（需配置短信服务）。
- 登录失败 5 次账号锁定（`LoginLockManager`，可在 `auth.py` 调整阈值）。
- **数据库（PostgreSQL）连接密码**：默认 `postgres` / `postgres`（见 `.env.example` 的 `DATABASE_URL`），这是数据库密码，**不是**应用登录密码。

> ⚠️ 生产环境务必修改 `.env` 中的 `SECRET_KEY`（当前为占位符 `your-secret-key-here`）。

---

## 8. 测试

后端验收套件（pytest），覆盖六层、8 类质检、S3 策略、报告降级、大脑阶段隔离、动作失败回传、可行性引导、前端静态冒烟：

```bash
cd backend
pip install pytest pytest-asyncio httpx
python -m pytest tests/ -q
# 43 passed
```

---

## 9. 目录结构（要点）

```
AI-Report/
├── backend/
│   ├── app/
│   │   ├── api/            # 路由：auth/upload/brain_run_sse/chat/quality/dashboards...
│   │   ├── core/
│   │   │   ├── brain_modules/   # S3 图表引擎、规则、配置
│   │   │   ├── quality_checker.py  # 8 类质检
│   │   │   ├── report_generator.py # 报告生成
│   │   │   ├── duckdb_manager.py   # 六层物化
│   │   │   ├── security.py         # 密码哈希/JWT
│   │   │   └── config.py
│   │   ├── models/         # User/Dataset/Dashboard/Chart...
│   │   └── main.py         # FastAPI 入口
│   ├── scripts/            # init_admin.py / seed_*.py / 测试脚本
│   ├── tests/              # pytest 验收套件（43 用例）
│   └── requirements.txt
├── frontend/
│   ├── src/views/          # login/dashboard/quality/chat...
│   ├── src/components/charts/  # ChartRenderer（饼图 scroll legend 等）
│   └── vite.config.ts      # /api 代理到 :8000
├── ai-report-acceptance-report/  # 验收报告静态站点
├── start_dev.ps1           # 一键启动（Windows）
└── README.md
```

---

## 10. 常见问题

| 现象 | 处理 |
|---|---|
| 启动报数据库连接失败 | 安装 PostgreSQL 并建库 `aibi`，或在 `.env` 设 `DB_FALLBACK_SQLITE=true` 用 SQLite |
| 登录提示「账号不存在」 | 先跑 `python scripts/init_admin.py` 创建管理员 |
| 看板为空且无图 | 数据集可能无数值/分类/日期字段，参见 S3 `no_chartable_fields` 提示 |
| LLM 调用报错 | 检查 `.env` 的 `LLM_API_KEY / LLM_BASE_URL / LLM_MODEL` |
| 报告章节异常导致整页崩 | 已修复：`report_generator.generate()` 外层 try 降级，返回带 `error` 标记 |

---

© 2026 AI-RiskViz Team
