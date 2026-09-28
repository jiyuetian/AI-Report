<!-- 权威治理源文件：由 _coach_input/ 于 night8 Item3 步骤7 迁入 docs/project_record/。其他文档引用请以本文件为准。 -->

# 环境事实（FACTS.md）

> 本文件只列**事实**，不写解释。
> AI 接手第一件事就是读它，不用你重复讲。
> 出问题时，先查本文件排除环境因素。
> **本版：v2，2026-09-28（LLM 六层链 + 数据状态刷新）。**

---

## 一、运行时

- **后端启动**：`cd backend && python run_backend.py`（端口 8000，HOST 127.0.0.1）
- **后端 Python**：`C:/Users/Asus009/AppData/Local/Programs/Python/Python312/python.exe`（**非 workbuddy venv**）
- **前端启动**：`cd frontend && npm run dev`（端口 5173）
- **API 前缀**：`/api/v1`（`/health`=404，正确是 `/api/v1/health`）
- **工作目录**：`C:/Users/Asus009/Desktop/临时/ai大赛/AI-Report`
- **分支**：`p0-security-fixes`

---

## 二、数据

- **DuckDB 业务库**：`backend/data/duckdb/aibi.db`（67MB，518 张 ds_* 表）
  - `DUCKDB_PATH=./data/duckdb/aibi.db`（`config.py:62`）
- **SQLite 元数据**：**待最终核实**
  - 候选 1：`backend/data/qa_aibi.db`（757KB）
  - 候选 2：`backend/data/aibi.db`（6.2MB）
  - 前后说法冲突，未最终澄清
- **上传目录**：`backend/data/uploads/`（09-28 已清空，旧文件归档至 `backend/data/_archive/uploads_pre_clean_20260928/`）
- **测试数据**：`tests/_fixtures/ai_test/`（14 文件，8 类）
- **备份**：
  - `backend/data/backups/aibi.db.bak_20260922_220253`（140MB，DuckDB）
  - 恢复验证过：488 表全回
  - SQLite 备份删 6 留 1（保 `pre_recover_20260922_230907`）

---

## 三、外部依赖

### LLM Provider（六层 failover，2026-09-28 现行）
| 层级 | Provider | 模型 | 状态 |
|---|---|---|---|
| 主用 | sensenova | `kimi-k3` | 付费，图表 JSON 稳定 |
| 备 1 | 智谱 | `glm-5.3-flash` | 免费，健康 |
| 备 2 | sensenova | `deepseek-v4-flash` | 免费，轻量 |
| 备 3 | 智谱 | `glm-4.5-air` | 免费 1200万专属包（10-25 到期）优先消耗；推理型不主用 |
| 备 4 | agnes | `agnes-2.0-flash` | 免费 |
| 备 5 | sensenova | `sensenova-6.8-flash-lite`（全小写） | 免费，推理型，末位兜底 |

- **failover 机制**：不是轮询，是顺序切（主挂才切备）
- **配置**：`backend/.env` 的 `LLM_PROVIDERS` 数组；**改后必须重启后端**
- **不可用**：glm-5.5-flash（资源包已有但 API 未上线，1211）、deepseek-v4.1-flash（403）
- **弃用史**：b.ai（从未充值）、NVIDIA nemotron（推理超时）、GLM-5.2（下架）

### 代理
- **7897**：Clash（本机代理，真实存在）
- **53012**：沙箱注入的 git 代理（**对 GitHub 502，必须绕过**）

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
- **已修**：`config.py` 加 fail-fast
- 残留风险：相对路径依赖 cwd，绕过 `run_backend.py` 启动可能又建空库

### 坑 2：多实例问题
- **同一时刻只允许 1 个后端进程**（DuckDB 单写锁）
- 启动前查 `run_backend.py` 的 B5 守卫（pidfile + 端口检测）
- 历史踩坑：5 个后端进程各指一个库 → 数据"时有时无"
- 端口占用检查：`netstat -ano | findstr :8000`

### 坑 3：git-bash shim 缺命令
- **缺**：`ls` / `cat` / `head` / `tail` / `grep` / `dirname` / `cd`
- **替代**：用 `python -c` / Read / Glob / Write

### 坑 4：Edit 偶发不落盘
- 本项目已发生 3+ 次"Edit 返回成功但实际未写入"
- **必做**：改完立即 Read 回读确认

### 坑 5：git push 需绕过代理
- 普通：`git push origin ...`（沙箱会挂）
- **直连**：`git -c http.proxy= -c https.proxy= push origin ...`

### 坑 6：antd Dragger 上传难自动化
- `input[type=file]` 无常驻 DOM
- 绕法：CDP `DOM.setFileInputFiles` 直注

---

## 六、截图 / 测试能力

- **Playwright + 系统 Edge 可用**（订正旧"沙箱无浏览器"结论）
- 可做：UI 真截图、E2E 测试
- 限制：antd Dragger 的上传难自动化

---

## 七、性能 / 阈值

- `TIMEOUT_SECONDS=120`（网关超时）
- `MAX_RETRIES=1`（网关重试）
- `BRAIN_S3_LLM_TIMEOUT=180`（S3 外层超时）
- `BRAIN_TASK_TOKEN_BUDGET=8000`（Token 预算）

---

## 八、最后更新

- **时间**：2026-09-24
- **版本**：v1
- **状态**：
  - 5 块（运行时 / 数据 / 外部依赖 / 账号 / 已知坑）已齐
  - 6 个已知坑已列
  - **待核实**：SQLite 元数据路径 / 智谱余额真伪
  - 落盘 `FACTS.md`（**待做**）