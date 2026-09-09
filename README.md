# AI 智能 BI 报表工具（开发版 v2.0）

基于数据血缘六层架构 + S1–S5 五阶段策略管道，自动从上传数据生成可视化看板，并支持自然语言对话修改图表。

> 技术栈：FastAPI + SQLAlchemy(async) + DuckDB + SQLite ｜ React + TypeScript + Vite + Ant Design 5 + ECharts ｜ LLM：Sensenova glm-5.2（OpenAI 兼容）

---

## 一、快速启动（本地, 无需装数据库/Redis/docker）

**方式 A（推荐）：双击 `一键启动.bat`**

它会自动：释放 8000/5173 端口 → 启动后端(自动用 SQLite + Sensenova LLM) → 启动前端 → 打开浏览器到 `http://localhost:5173`。

**方式 B：一键启动（复制到 PowerShell 整段运行）**

在项目根目录打开 PowerShell，把下面整段复制粘贴执行，会自动起后端+前端并打开浏览器：

```powershell
$ROOT = "C:\Users\Asus009\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\work-mode-projects\6a85720443a69020367ec184"
$PY = "C:\Users\Asus009\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\vm\tools\python\python.exe"
# 1. 释放端口
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'uvicorn|vite' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep 1
# 2. 启动后端（新窗口）
Start-Process powershell -WorkingDirectory "$ROOT\backend" -ArgumentList '-NoExit','-Command',"& `"$PY`" -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
Start-Sleep 6
# 3. 启动前端（新窗口）
Start-Process powershell -WorkingDirectory "$ROOT\frontend" -ArgumentList '-NoExit','-Command','npm run dev'
Start-Sleep 6
# 4. 打开浏览器
Start-Process "http://localhost:5173/"
Write-Host "启动完成：前端 http://localhost:5173  后端 http://localhost:8000"
```

**方式 C：手动两步**

后端（新开终端 1）：
```powershell
cd backend
& "C:\Users\Asus009\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\vm\tools\python\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

前端（新开终端 2）：
```powershell
cd frontend
npm run dev
```

> 若遇启动异常或提示「无法连接到后端」，先双击 **`环境自救.bat`** 清理残留进程再启动。

---

## 二、环境变量（backend/.env）

| 变量 | 值 | 说明 |
|------|----|------|
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/aibi.db` | 自动用 SQLite，无需 Postgres |
| `REDIS_URL` | `redis://localhost:6379/0` | 无 Redis 时自动降级本地信号量 |
| `LLM_API_KEY` | `sk-jYzkpXrm...` | Sensenova API Key |
| `LLM_BASE_URL` | `https://token.sensenova.cn/v1` | Sensenova OpenAI 兼容端点 |
| `LLM_MODEL` | `glm-5.2` | 智谱 GLM-5.2 模型 |

> ⚠️ 改 key 后**必须重启后端**才生效。

---

## 三、目录结构

```
backend/            FastAPI 后端
  app/
    api/            brain_v2.py / chat.py / dashboard / upload / quality 等接口
    core/           brain_modules (s1..s5) / llm_gateway / action_executor / intent_classifier ...
frontend/           React 前端 (最终构建也可 npm run build)
data/               运行时数据(SQLite/DuckDB/uploads)
一键启动.bat        本地一键启动入口（推荐）
环境自救.bat        环境锁/残留进程急救（启动异常时双击）
整体逻辑说明.html    详细系统逻辑(S1-S5 + M3对话 + 异常处理)
```

---

## 四、LLM 接入说明

- 默认走 **Sensenova glm-5.2**（OpenAI 兼容，`/v1` 端点）。
- `llm_gateway.py` 自带：JSON 稳健解析（从 ```json 代码块提取）、超时(60s)+重试(2次)、并发限流、Redis 降级。
- 换 key：改 `.env` 三行（KEY/BASE_URL/MODEL）后重启后端。

---

## 五、常见问题排查

| 现象 | 原因 | 解决 |
|------|------|------|
| 前端 5173 打不开 | 端口占用或被 3000/3001 漂移 | 双击 `一键启动.bat`（自动释放5173） |
| 看板生成 S1 超时(30s) | 讯飞对长 prompt 响应 13–17s，旧超时偏短 | 已改为 60s；仍超时双击 `环境自救.bat` 重启 |
| LLM 报 401/AppIdNoAuth | 端点或 key 不对 | 确认 `.env` 用 `/v2` + 正确 APIPassword，重启后端 |
| 「Toolhost 环境被锁」类错误 | 长后台任务残留 | 双击 `环境自救.bat`，或重启 TRAE 客户端 |

---

## 六、环境自救.bat 说明

当出现**工具执行环境被锁**（如 `Toolhost lifecycle is blocked`）、或端口被占、后端/前端起不来时，双击 `环境自救.bat`：
1. 结束所有残留 python/node 进程
2. 清理临时 job 状态目录
3. 弹出提示，随后用 `一键启动.bat` 正常启动

> 若救急后仍锁死，彻底重启 TRAE 客户端（完全退出再打开）可 100% 解除。

---

## 七、自测报告与已知问题清单（截至 2026-09-04）

> 代码唯一目录：本仓库 `AI-Report`。旧的「代码」快照与 TRAE 工作区镜像已删除，git `main` 分支已含截至本日最新提交（`fe1b22a`），本地只保留这一份最新代码。任何改动都在本目录进行，勿再建立第二份副本。

### 7.1 本次接口级自测结果（读侧 / 规则引擎：全部通过）

| 模块 | 接口 | 结果 |
|------|------|------|
| 健康 | `GET /api/v1/health` | ✅ 200 |
| 看板 | `dashboards/my`、`/{id}`、`stats/overview` | ✅ 200 |
| 数据集 | `datasets/{id}`、`preview`、`chart-data` | ✅ 200 |
| 质检 | `quality/check`（规则引擎）、`quality/{id}/issues` | ✅ 200 |
| 血缘 | `lineage/graph`、`stats`、`impact` | ✅ 200 |
| 生成管道 | `brain/configs`、`brain/s1/dictionary`、`brain/s2/types`、`brain/s3/rules|field-types|chart-types` | ✅ 200 |
| Token | `tokens/quota`、`tokens/status` | ✅ 200 |
| 导出/分享 | `exports/my/list`、`shares/my/list` | ✅ 200 |
| 登录 | `auth/login`（真实查库+密码校验+锁定） | ✅ 200 |

### 7.2 尚未收敛 / 与产品原型的差距（开源待办）

| # | 差距 | 说明与建议做法 |
|---|------|----------------|
| 1 | **LLM 生成整链路未做无死角回归** | 「上传 → S1主题 → S2目标 → S3图表 → S5评分 → 落库看板」依赖讯飞星火；同一批**真实模板数据**+可用 key 从上传页完整跑通并验收每个阶段结果 |
| 2 | 质检「AI 补充检测」依赖 LLM | key 不可用时降级标注"暂不可用"，需在真实验证里确认降级提示正确 |
| 3 | KPI / 看板卡片可能残留示例数据 | 需按真实生成结果核对每个卡片的数值来源，不应依赖演示数据 |
| 4 | 看板操作（分享/导出/版本/删除/重命名）前后端逐一对齐 | 接口已存在，需逐个点击验收并与 PRD 原型比对 |
| 5 | 权限/多用户为单机演示态 | `tokens` 返回 `anonymous`，企业微信会议纪要等外围模块未包含在本仓库 |
| 6 | 图表规则矩阵(14条)+LLM 补充 | 对真实表结构的推荐合理性需批量抽样核对 |
| 7 | 前端生产构建与一键部署（`npm run build` / `一键打包.sh`） | 本轮未验证，交付前需跑通一次 |

### 7.3 历史上已修复并合入仓库的问题（备忘）

- **启动**：`一键启动.bat` 引号嵌套 bug 导致 `uvicorn` 被截成 `vicorn`、后端起不来 → 已改 `pushd`+无嵌套引号。
- **数据库**：SQLite 并发写锁 `database is locked` → 连接 `timeout=30s` + `_safe_trace` 失败自动回滚自愈。
- **生成超时**：统一轮询协议；LLM 超时 60s、重试 2 次、支持从 JSON 代码块提取。
- **上传**：会话状态持久化（fileList/previewMap/datasetMap/activeFileId/genMap），重试免重选文件；网络错误与文件错误分级提示。
- **质检面板**：6 类校验、90s 超时保护、AI 补充检测异步后台；fix 网络错误/403 单独提示。
- **图表渲染**：折线图日期按月归并、环形图自动识别分类列、KPI 大数字紧凑格式化、自动补全缺失分布图（贷款类型/地区/担保类型）。
- **看板页**：对话面板可折叠/全屏；血缘页与看板页共用同一 `ChatPanel` 组件（一套样式标准）。
- **血缘**：六层节点渲染 + 右侧问答面板。
- **登录/安全**：登录改为真实查库（非硬编码）；Redis 不可用时自动降级。

### 7.4 常规使用须知

- 验收改动请 **Ctrl+Shift+R 硬刷新**；改 LLM key 后**重启后端**才生效。
- 报"无法连接后端/启动异常"：先双击 `环境自救.bat` 清理残留进程再启动。
- 首次启动后端较慢（依赖导入数十秒），健康检查窗口 30s 基本够，必要时可增大 `一键启动.bat` 的重试次数。

### 7.5 六层对话能力链路自测（成败关键项，2026-09-04）

> 目标：验证 AI 助手对 **6 层数据链路** 的对话修复/加工能力是否从意图识别 → 动作执行 → 数据库落库全链路闭环。
> 测试脚本：`backend/_test_6_scenarios.py`（端到端 SSE 全流程）、`backend/_test_intent.py`（意图识别单元）。

| # | 覆盖层级 | 测试指令 | 识别意图 | 执行动作 | 落库 | 结果 |
|---|----------|----------|----------|----------|------|------|
| 1 | 清洗层(原始→修复后) | 质检发现借据号有重复，帮我修复去重 | `quality_fix` 置信95 | 真实去重写入 DuckDB 清洗层 | quality_fix_log+1 | ✅ |
| 2 | 业务加工层(新增指标) | 看板指标新增借据总笔数 | `add_chart` 置信75 | 新增 KPI 卡(指标名"借据总笔数") | charts 新增 | ✅ |
| 3 | 图表层(换图) | 把第一个柱状图改成折线图 | `change_chart` 置信85 | 改 chart_type=line | charts 更新 | ✅ |
| 4 | 图表层(新增图) | 右侧再新增一个担保类型占比饼图 | `add_chart` 置信75 | 新增饼图 | charts 新增 | ✅ |
| 5 | 聚合层(筛选下钻) | 只查看华东地区的担保数据 | `filter_drill` 置信70 | 写入 filters(地区=华东) | config 更新 | ✅ |
| 6 | 分析层(归因溯源) | 为什么本期贷款金额较上期上升 | `attribution` 置信75 | 血缘下钻+归因结果 | config 更新 | ✅ |

**链路判定 6/6 PASS**（每场景均拿到 `complete` + `DONE`，且动作真正落库）。

本次修复要点：
1. **新增 `quality_fix` 意图/动作**：此前"质检发现…修复去重"被识别为 UNKNOWN 仅降级回复。现补全 `IntentType.QUALITY_FIX` + `ActionType.QUALITY_FIX`，真实调用 DuckDB 清洗层去重（`keep_first`），并把修复历史写入看板 config。
2. **参数提取修正**：问题列名 "借据号"（原误提取成"号有"）、KPI 指标名 "借据总笔数"（原落回默认"新增指标"）。
3. **看板 config 持久化修复（关键）**：`execute_action` 原地 mutate `dashboard.config` 返回同一对象，SQLAlchemy 对 JSON 做身份比较检测不到变更，`commit` 不生成 UPDATE 导致所有对话动作刷新即丢 → 改用 `flag_modified(dashboard,"config")` 强制标脏。修复后 charts 从 5 条正确增至 7 条（新增 KPI + 饼图）。

**回归脚本**：`backend/_test_6_scenarios.py`（需后端 8000 运行）、`backend/_test_intent.py`（无需后端）。

**遗留说明（去重外部可验证性，2026-09-04）**：
- **幂等性**：去重是幂等的——二次运行时清洗层已无重复，所以 `removed=0`，但 `real=True` 仍证明真实写入了 DuckDB。
- **外部验证**：DuckDB 被后端进程独占，外部无法再开连接验证。已新增只读端点 `GET /api/v1/quality/debug/clean-stats?dataset_id=…`，在 uvicorn 进程内复用全局 DuckDB 连接查询清洗层实时统计（原始层/清洗层行数、去重列、剩余重复数）；并新增 `POST /api/v1/quality/debug/inject-dup`（仅调试）用于造重复→对话修复→查询归零的端到端演示。`_verify_dedup.py` 走通闭环：注入 5 条 → 对话修复（场景1指令）→ DuckDB 剩余重复归 0。
- **本次实测（`_test_6_scenarios.py` 场景1）**：`raw=1020 → cleaned=514，diff=506，去重列=借据号，剩余重复=0`，DuckDB 无重复 ✓，从外部经 HTTP 取得真实数据而非 config 日志推断。

### 7.6 多场景 + 并发压力自测（2026-09-04）

> 目标：扩大覆盖 7 类意图变体 + 边界降级，并验证高并发下对话链路的稳定性。

**① 语义多场景测试**（`backend/_test_extended.py`，35 例）：经修复后意图识别 **35/35**。
本次修复覆盖三类缺口：
- "来一张散点图"→ 补 `ADD_CHART` 的"来/来一张"句式；
- "说明下这个波动"→ 补 `ATTRIBUTION` 的"说明/说下/讲下+波动"句式；
- "把标题改成贷款分析"→ 原被 `CHANGE_CHART` 过宽规则(`把..改成..`)误判，收敛为需出现图表类型词后正确归到 `edit_title`。

**② 并发压力测试**（`backend/_test_stress.py`）：

| 并发 | 修复前 | 修复后 |
|------|--------|--------|
| 12 并发 | 全部通过，总耗时 6.5s | 全部通过 |
| 24 并发 | **17/24，7 个 HTTP 500**，总耗时 36.5s | **24/24 全部通过**，总耗时 6.9s |

根因与修复：
- 根因：每个 SSE 流式响应**全程持有一个 DB 连接**，默认 `QueuePool(size=5, overflow=10)` 最多 15 连接，十几路并发即被占满，等待 30s 超时抛 `TimeoutError` → 500。
- 修复：`backend/app/core/database.py` 对 SQLite 连接池扩容至 `pool_size=40, max_overflow=0, pool_timeout=90`（WAL 下并发读自由，写仍单写但事务 ms 级）；PostgreSQL 分支相应调大。

**并发覆盖修复**：并发新增图表时，看板 config 为全量 JSON 覆盖写入，多路并发曾存在"最后写者胜"的丢失更新（多路同时新增，图上限判断基于各自旧配置）。已在 `backend/app/api/chat.py` 用**每看板一把进程内 `asyncio.Lock`** 包裹"读-改-写"事务串行化，并在锁内基于最新 config 对 `add_chart` 做图上限（10）兜底。
- 验证（`backend/_test_overwrite.py`）：干净 5 图并发 4 路新增 → **5+4=9，无丢失更新**；并发 8 路新增 → **封顶 10 图，后 3 路被上限拦截，无崩溃**。

局限说明：锁为进程内锁，仅对单进程部署保证串行；多进程/多 worker 部署时需改用数据库行锁（`SELECT ... FOR UPDATE`）+ 版本号重试。

**回归**:连接池改动后 6 场景端到端仍 **6/6 全 PASS**。

### 7.7 问题复盘日志（2026-09-04 上线期集中复盘 · 后续新改动务必回看本节避免重犯）

> 目的：把本阶段踩过的每一类问题**根因→修复→规避**沉淀为规则，开发/测试前先对照本节，减少"修好这里、又坏那里"的循环。配套验证脚本见 `backend/_verify_fix.py`（纯逻辑）与 `backend/_verify_llm_charts.py`（LLM 维度贴合，需后端无需 DB）。

#### P1. 后端进程悄然掉线 → "看板/接口全部 404/空" 假象（本次用户"走不通"首因）

- **现象**：明明生成过看板，但打开"我的看板"为空、进详情提示"看板不存在"、上传页停在未生成态。
- **根因**：前端全部请求打向 `http://localhost:8000`，但 uvicorn 进程若未运行，前端拿不到任何数据 → 三种表象全部由"后端没起"一个原因造成。代码层看板/接口本身健康。
- **规避**：
  1. 排障先做健康检查：`curl http://localhost:8000/api/v1/health`，`netstat -ano | findstr 8000` 确认进程在监听，**不要先怀疑前端**。
  2. 后端统一用 `一键启动.bat`（独立窗口 + `pushd` 安全写法）拉起，避免依赖本会话后台任务。
  3. 用户报"看不见/空/不存在"时，第一优先确认为**后端存活**而非改代码。

#### P2. "我的看板"列表 owner 硬编码过滤 → uploaded 看板永远不可见（真 bug）

- **现象**：上传/对话生成的看板不出现"我的看板"列表，统计数也偏少。
- **根因**：`dashboards.py` 的 `/my` 与 `/stats/overview` 用**硬编码 `user_id='anonymous'`** 过滤 `created_by`，而上传/对话生成看板的 owner 是 `'current'` → 被过滤掉。
- **修复**：owner 条件放宽为 `created_by/updated_by IN ('anonymous','current')`。
- **规避**：新增"列表/统计"类查询，owner 过滤必须与**写入侧 owner** 保持一致；改用统一 `_OWNERS` 常量，禁止裸写单一 user_id。

#### P3. 看板分析"维度思路不对"（用户画像却只出单位性质/失信占比）

- **现象**：`risk_demo_v2_02_客户风险画像表` 数据里 `婚姻状况/单位所属行业/借款人年龄` 都有，但生成看板没做这些分布。
- **根因**（故障链三层，须一起修）：
  1. **字段语义识别弱**：`s3_chart_engine.py` 的字段类型靠关键词白名单，`婚姻状况/单位性质/单位所属行业` 被误判为`text`，引擎识别不出它们是"可做分布的维度"。
  2. **主题与维度不联动**：`theme`（如"客户画像"）只是 LLM prompt 背景文字，没有把主题翻译成"该优先做哪些维度的分布"。
  3. **LLM prompt 无字段类型/业务引导** + **无数值分桶能力**：模型想造 `借款人年龄_分桶` 这类字段做年龄分布 → Schema 校验"字段不存在"被拦，随后超时降级到 rule 引擎 → 维度更单一。
- **修复**：
  1. 扩充 `FieldAnalyzer` 中文字段语义（婚姻/状况/性质/行业/人员→category；年龄/月数/次数/比→number），并强制 ID/编号→text；
  2. 新增 `THEME_DIMENSION_HINTS`（客户画像/信贷/风险场景→建议优先维度），`_build_prompt` 注入"字段类型说明 + 主题维度建议"，并**硬性禁止臆造不存在的字段名**；
  3. LLM 更从容：`llm_gateway.TIMEOUT_SECONDS` 25→60s，减少超时降级；
  4. rule 兜底在多个 category 字段时让 bar/pie **轮流用不同维度**，避免所有图挤在同一对字段。
- **验证**（`_verify_fix.py` + `_verify_llm_charts.py`）：字段语义 9/9 正确、占位符 0 残留、rule 兜底多维覆盖；LLM 生成 **婚姻状况分布 / 单位所属行业分布 / 借款人年龄分布 / 失信人员占比 / 历史逾期次数分布**，婚姻/年龄/行业 core 命中 **3/3**（修复前仅 1/3）。
- **规避**：新增图表推荐逻辑时，字段类型识别、主题维度引导、LLM 字段约束三者必须同步考虑；用 LLM 生成时**永远显式约束"只准用数据集真实字段名"**。

#### P4. 模板占位符未渲染（`总{field}`、`{number_field1} vs {number_field2}`）

- **根因**：`s3_chart_rules.yaml` 标题用 `{field}/{number_field1}/{number_field2}/{number_fields}/{category_field1/2}`，但 `s3_chart_engine.py` 的 title 替换只处理了部分占位符。
- **修复**：`_match_rule` 补全所有占位符的 title 替换（含`{number_fields}`复数拼接、`{category_field1/2}`），并给缺失字段以兜底文本。
- **规避**：新写占位符模板时，必须在替换器里**同步注册**；交付前用 `_verify_fix.py` 断言生成结果不含 `{`。

#### P5. 含括号/特殊字符的中文列名导致 SQL 语法错误

- **现象**：`/datasets/{id}/profile` 报 `Scalar Function with name 职业稳定性 does not exist`，`画像生成失败`。
- **根因**：字段 `职业稳定性(连续工作年限)` 含全角括号，SQL 拼接未加引号，被 DuckDB 解析成标量函数调用。
- **修复**：`duckdb_manager.py` 新增 `quote_ident()`，`get_profile` 内所有列名/表名统一安全引用。
- **规避**：**任何**把用户字段名拼进 SQL 的地方都必须 `quote_ident()` 包裹；禁止裸 `f"...{column}..."`。审查点：`quality.py`、`data_cleaner.py`、`action_executor.py` 等所有列名拼接。

#### P6. `_match_rule` 未校验规则 `keywords` 条件 → "总借款人年龄" 错误 KPI

- **根因**：yaml KPI 规则带 `keywords:["金额","total"...]`，但匹配器只校验 `field_types`，导致任意数值字段（如借款人年龄）都触发"总金额KPI"，生成 `总借款人年龄`。
- **修复**：`_match_rule` 增加 `keywords` 命中校验（字段名需含规则关键词）。
- **规避**：规则条件里出现的关键词约束，匹配器必须实现；交付前验证不要出现语义不合理的标题。

#### P7. 前端标题文字被截断（最后几个字看不到）

- **根因**：KPI 卡 `.kpi-title` 与图表卡 `antd Card head-title` 默认 `nowrap + ellipsis` 单行省略，长标题被截。
- **修复**：`.kpi-title` 改为 `white-space:normal; word-break:break-all`；`.widget-card .ant-card-head-title` 同样允许换行，保证标题完整展示。
- **规避**：标题类元素如需"完整可见"，不要用单行省略；用多行换行 + `word-break`。

---

#### 备忘：为什么"测试通过，用户却走不通"（本次最大教训）

不是玄学，是**环境/链路差异**：
1. 接口级/子代理测试大多在**保证后端存活**的前提下直达 API 或打开已就绪页面；而用户常在后端进程已掉时打开浏览器 → 全断。
2. 用户走的是**端到端长链路**（上传→清洗→质检→S3→看板→对话），任一层（如 P5 的 profile、P3 的 rule 兜底）失败，表象都落到上层"看板/图表不对"。
3. 因此**交付评审前必须**：`health` 探活 → `_verify_fix.py` 纯逻辑 → 关键接口抽查（`/dashboards/my`、`/datasets/{id}/profile`）→ 浏览器端到端走一遍真实上传生成链路，四层都绿再交付。

---

## 八、能力基线 + 成长机制（打磨就是打磨下面这些能力）

本产品定位不是"一次性工具"，而是通过**规则库可生长 + 与 AI 上下文对齐 + AI 有节制介入**持续进化的能力体。
下面把"当前能力基线"和"如何让他生长"固化成本章节，供后续每次迭代对齐、验收和回顾。

### 8.1 一条核心原则：规则为主，AI 为辅，但可生长

| 层级 | 职责 | 是否依赖 AI | 演进方式 |
|------|------|-----------|---------|
| **规则引擎** | 覆盖高置信、可确定性判断的问题（如文本型数字、空值、主键重复、格式）| 否 | 通过集中常量库不断增补行业规则 |
| **AI 补充检测** | 承接规则"低置信/五五开"的复杂场景，做语义与类型裁定 | 是（异步后台）| 先喂给 AI 我们的规则与已发现项，让 AI **先了解再介入** |
| **修复管道** | 规则/AI 都只产出修复建议，实际落库走同一套 coerce/填充策略（只写清洗层）| 否 | 修复策略与检测规则严格同源，杜绝"判可转、却置 NULL" |

### 8.2 能力台账（截至本版本已落地）

**A. 文本型数字检测 + 一键转数值（本次新增 · 用户"成功率成败关键"）**
- 检测：识别"数值被读成文本"（千分位 `1,234`、货币 `￥100`、`'5000'`、混入 `N/A`/`未知` 导致整列文本）。
  - 高置信（脏值占比≤30%）→ **阻断**，提示一键强转；
  - 五五开（>30%）→ 降为**提示**，交 AI 验证后决定。
- 修复 `coerce_numeric`：**三步真正转数值**，非"伪转数"——
  1. 清洗显示值（货币符/千分位/空白/NBSP）；
  2. 不可转残留（如 `N/A`）置 NULL；
  3. `ALTER ... SET DATA TYPE DOUBLE` **真正改列类型**，让下游 SUM/报表能识别聚合。
- 可生长规则库常量（集中管理，按行业持续扩充）：
  ```
  _NUMERIC_SUFFIXES    # 尾缀单位：万元/千元/%/个/笔/人/次…
  _NUMERIC_RATIO       # 可转率≥50% 才判"疑似数值列"（低置信交 AI）
  _NUMERIC_DOMINANT_RATIO  # 脏值占比阈值：≤30% 高置信阻断强转，否则提示
  ```
- 编号/标识类列（借据编号、客户编号）天然被"可转率"门槛与主键关键词挡掉，**不会误转**。

**B. 既有质检能力（六类）**：空值/格式/唯一性/范围/逻辑/码值，规则驱动实时判定，AI 异步补充。

**C. 数据血缘六层架构**：原始→字段标准化→清洗→业务加工→聚合→看板输出，质检/修复始终读**最上层（清洗层）**、只写清洗层、不动原始层（DuckDB 持久化防重启丢失）。

**D. LLM 接入**：OpenAI 兼容（`/api/v1/llm/chat/completions`），`LLM_API_KEY/BASE_URL/MODEL` 配置，无 Key 时自动 mock 降级，不影响规则主链路。

### 8.3 AI 协同原则（让 AI 先"懂规则"再介入）

1. **先给规则再让 AI 介入**：AI 质检 prompt 显式注入"已检测到的问题清单"，避免 AI 重复、与规则冲突或臆造字段。
2. **AI 只做规则覆盖不了的裁定**：如"文本型数字五五开时该不该转数值""编号列别误转"这一类需要语义的判定；AI 输出必须是带 `coerce_numeric` 等**既有修复策略 ID** 的结构化建议，不能发明清理逻辑。
3. **AI 慢/不可用不阻塞主链路**：AI 补充检测走后台异步 + 缓存轮询，LLM 失败仅提示"AI 补充检测暂不可用"，阻断性判定由规则引擎守护。
4. **模型能力提升自动升级**：规则阈值和 AI prompt 是"上下文契约"，模型换代（如更强的 Spark-X）不需要改产品逻辑，只需让 prompt 更胜任复杂裁定，能力随之生长。

### 8.4 迭代日志（如何"打磨"一条能力）

新增/增强某项能力时，**按此清单落地并回到本节登记**，供参与人员对齐"产品现在能做到什么"：
1. 更新规则库常量或 JSON，让规则引擎优先覆盖（不依赖 AI、可离线验证）；
2. 同步 AI prompt 的"分析要求 + 修复方案要求"，保证 AI 与规则上下文对齐；
3. 抽出自测脚本（如 `backend/_verify_type_consistency.py`），覆盖检测→分级→修复→聚合全链路；
4. 交付前四层验收：`health` 探活 → 纯逻辑自测 → 关键接口抽查 → 浏览器端到端；
5. 在此记录"新增能力、变更的文件、验证结果"。

> 变更登记（2026-09-04-1）：新增「文本型数字检测 + coerce_numeric 三步真转数值（含列类型改DOUBLE）」。
> 涉及 `backend/app/core/quality_checker.py`（检测+可生长规则库/阈值）、`backend/app/api/quality.py`（三步转数值+过滤隐藏对象自检）、`backend/app/core/ai_quality_checker.py`（AI 类型一致性验证）、`backend/_verify_type_consistency.py`（全链路自测）。
>
> 变更登记（2026-09-04-2）：**提示词外置落地** —— 让"AI 先读提示词"成为真实机制。
> 节点1（AI质检）、节点4（S3图表主生成）的提示词迁出到 `backend/app/core/prompts/ai_quality_checker.md` 与 `s3_llm_main.md`；
> 新增 `core/prompt_loader.py`（`load_prompt(slug, default, **tokens)`：优先读文件并替换 `{token}`，缺失/异常回退内置默认，mtime 缓存改文件自动重载）。
> 涉及：`core/ai_quality_checker.py`、`brain_modules/s3_llm_enhancer.py`、`_verify_prompt_externalize.py`（`PROMPT_EXTERNALIZE_TESTS_OK`）。控制文档见 `docs/六层管线与被控提示词.md` 第五/六/七节。