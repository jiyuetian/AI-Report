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