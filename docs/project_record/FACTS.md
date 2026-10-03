<!-- 权威治理源文件：由 _coach_input/ 于 night8 Item3 步骤7 迁入 docs/project_record/。其他文档引用请以本文件为准。 -->

# 环境事实（FACTS.md）

> 本文件只列**事实**，不写解释。
> AI 接手第一件事就是读它，不用你重复讲。
> 出问题时，先查本文件排除环境因素。
> **本版：v3，2026-10-03（对齐 night18 现状：Python/SQLite 澄清 + LLM 七层链 + 代理永久化）。**

---

## 一、运行时

- **后端启动**：`cd backend && python run_backend.py`（端口 8000，HOST 127.0.0.1；启动器内含 chdir + B5 单实例守卫 + DuckDB fail-fast）
- **一键启动**：根目录 `一键启动.bat`（先释放 5173，再起后端健康探活，最后起前端并开浏览器）
- **后端 Python**：`C:/Users/Asus009/AppData/Local/Programs/Python/Python312/python.exe`（**实测 `3.12.10`，2026-10-03 核对**）
  - ⚠️ 订正 v2：曾写"非 workbuddy venv"，属实；但 `01_CURRENT_STATE.md` 旧稿把 workbuddy `3.13.12` 写成后端解释器是**错的**——那是 agent 工具链，**不是后端运行时**
  - ⚠️ `一键启动.bat` 里 `%~dp0vm\tools\python\python.exe` 指向的项目内 `vm/` **本机不存在**（未随仓分发）→ 该 bat 直跑会失败，改用系统 Python312 或 `run_backend.py`
- **前端启动**：`cd frontend && npm run dev`（端口 5173）
- **API 前缀**：`/api/v1`（`/health`=404，正确是 `/api/v1/health`）
- **工作目录**：`C:/Users/Asus009/Desktop/临时/ai大赛/AI-Report`
- **分支**：`p0-security-fixes`

---

## 二、数据

- **DuckDB 业务库**：`backend/data/duckdb/aibi.db`（约 134MB，518 张 `ds_*` 表）—— 图表读取的真相库
  - `DUCKDB_PATH=./data/duckdb/aibi.db`（`config.py`，已绝对路径化 + fail-fast）
- **SQLite 元数据**：`backend/data/aibi.db`（约 6.1MB）—— **已确认，不再"待核实"**
  - 依据：`backend/.env` 的 `DATABASE_URL=sqlite+aiosqlite:///./data/aibi.db`
  - 装 `user` / `dashboard` / `dataset` / `chat_session` / `chat_message` / `dashboard_version` / `analysis_template` / `token_quota` 等
  - ⚠️ 与 `duckdb/aibi.db` **同名不同文件不同目录**，勿混
- **历史遗留库**（不再被后端连接，仅留备份，清理归第 5 层）：
  - `backend/data/qa_aibi.db`（旧元数据库副本）
  - `backend/data/duckdb/qa_aibi.db`（曾装 36 张 ds_* 业务表，P0-2 双库错配源头，表已迁入主库）
- **上传目录**：`backend/data/uploads/`（09-28 清空，旧文件归档 `backend/data/_archive/uploads_pre_clean_20260928/`）
- **测试数据**：`tests/_fixtures/ai_test/`（14 文件，8 类）
- **备份**：`backend/data/backups/aibi.db.bak_20260922_220253`（140MB，DuckDB，恢复验证 488 表全回）

---

## 三、外部依赖

### LLM Provider（**七层 failover，2026-10-03 现行 = `.env` 真值**）
| 层 | Provider | 模型 | 备注 |
|---|---|---|---|
| 主用 | sensenova | `kimi-k3` | 付费，图表 JSON 稳定；网关仅允许 `temperature=1` |
| 备 1 | 智谱 | `glm-4.5-air` | 免费 1200 万专属包（10-25 到期）优先消耗；推理型不主用 |
| 备 2 | 智谱 | `glm-4.7-flash` | 免费 |
| 备 3 | 智谱 | `glm-4.6v` | 免费 |
| 备 4 | sensenova | `deepseek-v4-flash` | 免费，轻量 |
| 备 5 | agnes | `agnes-2.0-flash` | 免费 |
| 备 6 | sensenova | `sensenova-6.8-flash-lite`（全小写） | 免费，推理型，末位兜底 |

- **⚠️ 订正 v2**：v2 的"六层链（含 `glm-5.3-flash`）"已作废。night14 Task A（`50308ea`，D-020）调整为**七层**，顺序以 `backend/.env` 的 `LLM_PROVIDERS` 数组为准
- **failover 机制**：顺序切（主挂才切备），非轮询；网关要求 `business_type=chat`
- **配置**：`backend/.env` 的 `LLM_PROVIDERS`；**改后必须重启后端**
- **已知不稳**：智谱 `json_mode` 偶发返回带 Markdown 围栏（ISS-044，已加剥围栏 + 重试 + 切 provider 防护）
- **不可用**：glm-5.5-flash（资源包已有但 API 未上线，1211）、deepseek-v4.1-flash（403）
- **弃用史**：b.ai（从未充值）、NVIDIA nemotron（推理超时）、GLM-5.2（下架）

### 代理
- **7897**：Clash（本机代理，真实存在）；**已永久配置**（`netsh winhttp` + 注册表 `HKLM\...\4073` 双写），无需每次 `set https_proxy`
- **53012**：沙箱注入的 git 代理（**对 GitHub 502，必须绕过**）
- **git push 配方**：`git -c http.proxy=http://127.0.0.1:7897 -c http.extraHeader="Authorization: Basic <base64(user:token)>" push origin <branch>`（token 从 Windows 凭据管理器 `git credential fill` 取）

---

## 四、账号

- **管理员**：`admin` / 密码见 `.env`
- **测试账号**：`e2e_test`（用于自动化测试）
- **⚠️ `_push_cred.txt`**：含 GitHub token（私有项目，用户明确说不管）

---

## 五、已知坑（血泪）

### 坑 1：DuckDB 静默建空库
- **对不存在的路径，DuckDB 会静默建空库，不报错**
- 后果：图表全空、用户以为数据丢了
- **已修**：`config.py` 加 fail-fast（绝对路径化 + 启动校验 `[DUCKDB-FAIL]` 退出）
- 残留风险：绕过 `run_backend.py` 启动仍可能建空库

### 坑 2：多实例问题
- **同一时刻只允许 1 个后端进程**（DuckDB 单写锁）
- 启动前查 `run_backend.py` 的 B5 守卫（pidfile + 端口检测；`_pid_alive` 已改 ctypes，ISS-057 修 Windows 误杀）
- 历史踩坑：5 个后端进程各指一个库 → 数据"时有时无"
- 端口占用检查：`netstat -ano | findstr :8000`

### 坑 3：git-bash shim 缺命令
- **缺**：`ls` / `cat` / `head` / `tail` / `grep` / `dirname` / `cd`
- **替代**：用 `python -c` / Read / Glob / Write

### 坑 4：Edit 偶发不落盘
- 本项目已发生 3+ 次"Edit 返回成功但实际未写入"
- **必做**：改完立即 Read 回读确认

### 坑 5：git push 需绕过代理
- 沙箱注入的 53012 代理对 GitHub 502
- **直连配方**：见 §三「代理」

### 坑 6：antd Dragger 上传难自动化
- `input[type=file]` 无常驻 DOM
- 绕法：CDP `DOM.setFileInputFiles` 直注

### 坑 7：failover 模型透传 bug（已修）
- 曾因 `request.model` 锁死 `kimi-k3` → 备胎永不命中（`9c9e1b7` 修）
- 教训：改 failover 链后必验证"主挂时备胎真被调用"

---

## 六、截图 / 测试能力

- **Playwright + 系统 Edge 可用**（订正旧"沙箱无浏览器"结论）
- 可做：UI 真截图、E2E 测试
- 脚本 `backend/scripts/_ui_shots.py`；前端守卫需同时注入 `localStorage['token']` 与 `localStorage['user']={roles:['admin']}`
- 限制：antd Dragger 的上传难自动化

---

## 七、性能 / 阈值

- `TIMEOUT_SECONDS=120`（网关超时）
- `MAX_RETRIES=1`（网关重试）
- `BRAIN_S3_LLM_TIMEOUT=180`（S3 外层超时）
- `BRAIN_TASK_TOKEN_BUDGET=8000`（Token 预算）
- ISS-045 LLM 失败指数退避重试：最多 3 次（8/16/24s）

---

## 八、最后更新

- **时间**：2026-10-03
- **版本**：v3
- **状态**：
  - 运行时 / 数据 / 外部依赖 / 账号 / 已知坑 五块已刷新到 night18 现状
  - **订正**：后端 Python = 系统 Py312 3.12.10；SQLite 元数据 = `backend/data/aibi.db`（已确认）；LLM = 七层链
  - 落盘 `FACTS.md`（✅ 在 `docs/project_record/`）