# AI 智能 BI 报表工具（开发版 v2.0）

基于数据血缘六层架构 + S1–S5 五阶段策略管道，自动从上传数据生成可视化看板，并支持自然语言对话修改图表。

> 技术栈：FastAPI + SQLAlchemy(async) + DuckDB + SQLite ｜ React + TypeScript + Vite + Ant Design 5 + ECharts ｜ LLM：讯飞星火 Spark-X（OpenAI 兼容）

---

## 一、快速启动（本地, 无需装数据库/Redis/docker）

**方式 A（推荐）：双击 `一键启动.bat`**

它会自动：释放 8000/5173 端口 → 启动后端(自动用 SQLite + 讯飞 LLM) → 启动前端 → 打开浏览器到 `http://localhost:5173`。

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
| `LLM_API_KEY` | `NXec...QyU` | 讯飞星火 APIPassword |
| `LLM_BASE_URL` | `https://spark-api-open.xf-yun.com/v2` | **必须用 /v2**（Spark-X 走这里） |
| `LLM_MODEL` | `spark-x` | Spark-X 模型 |

> ⚠️ 曾踩坑：端点 `/agent/v1` 是 X2-Flash 的，Spark-X 应用走 `/v2/chat/completions`（见 `.env` 当前值）。改 key 后**必须重启后端**才生效。

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

- 默认走 **讯飞星火 Spark-X**（OpenAI 兼容，`/v2` 端点）。
- `llm_gateway.py` 自带：JSON 稳健解析（从 ```json 代码块提取）、超时(60s)+重试(2次)、并发限流、Redis 降级。
- 换 key：改 `.env` 三行（KEY/BASE_URL/MODEL）后重启后端。
- 曾用 Sensenova（需 `business_type` 字段），已按 base_url 自动判断是否附带，兼容两种提供商。

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