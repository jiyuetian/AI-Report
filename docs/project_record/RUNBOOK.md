<!-- 权威治理源文件：由 _coach_input/ 于 night8 Item3 步骤7 迁入 docs/project_record/。其他文档引用请以本文件为准。 -->

# 运行手册（RUNBOOK.md）

> 出问题先查本文件，90% 的常见故障能自己 1 分钟搞定。
> 和 `FACTS.md` 配合：FACTS 说"是什么"，RUNBOOK 说"怎么办"。
> **本版：v2，2026-10-03（草稿转正，对齐 night18 现状）。**

---

## 一、启动

1. 起后端：`cd backend && python run_backend.py`（系统 Python312，端口 8000；启动器含 B5 单实例守卫 + DuckDB fail-fast）
2. 起前端：`cd frontend && npm run dev`（端口 5173）
3. 验证：`curl http://127.0.0.1:8000/api/v1/health` → 200

> 一键启动：根目录 `一键启动.bat`（⚠️ 其内部 `vm\tools\python` 本机缺失，若报错改用上面的 `run_backend.py`）。

---

## 二、停止

- 按 `Ctrl+C` 优雅停
- **不要硬杀**（DuckDB 单写锁，硬杀可能损坏）

---

## 三、常见故障

| 症状 | 原因 | 处置 |
|---|---|---|
| 图表全空 | DuckDB 路由错 / 静默建空库 | 检查 `DUCKDB_PATH=./data/duckdb/aibi.db`；看启动日志 `[DUCKDB-OK]` / `[DUCKDB-FAIL]` |
| 端口被占 | 残留进程 | `netstat -ano \| findstr :8000` → `taskkill /PID <pid> /F` |
| 后端起不来（B5 拒绝） | 残留死 pidfile 误判存活 | 删 `backend/.backend.pid` 再起（ISS-057 已修 `_pid_alive`） |
| LLM 不可达 | 代理挂了 / 资源包到期 | 重启 Clash（7897）；查 `.env` `LLM_PROVIDERS`；glm 资源包到期见 ISS-030 |
| 前端白屏 | 构建旧了 | `cd frontend && npm run build` |
| 登录后跳 403 | 前端守卫缺角色 | localStorage 注入 `user={roles:['admin']}`（自动化截图场景） |
| LLM 返回带 ``` 围栏 JSON | 智谱 json_mode 不稳 | ISS-044 已加剥围栏 + 重试 + 切 provider |

---

## 四、测试 / 准出

```powershell
# 后端语法
cd backend && python -m py_compile app/core/action_executor.py   # 目标文件

# 隔离回归（gitignored）
python _verify_iss058.py     # 例：ISS-058 阈值调整 5 场景
python _verify_taskjk.py     # 例：Task J/K 19 场景

# 前端类型
cd frontend && npx tsc --noEmit      # EXIT=0

# 健康
curl http://127.0.0.1:8000/api/v1/health   # 200
```

**准出线**：`_verify_*.py` 全 PASS + `py_compile` 全绿 + `tsc --noEmit` EXIT=0 + `/health` 200。

---

## 五、git push（绕过代理陷阱）

```powershell
# 沙箱 53012 代理对 GitHub 502，必须显式走 7897 + 带凭据
git -c http.proxy=http://127.0.0.1:7897 -c http.extraHeader="Authorization: Basic <base64(user:token)>" push origin p0-security-fixes
```

- token 从 Windows 凭据管理器取：`git credential fill`
- 7897 代理已**永久配置**（`netsh winhttp` + 注册表），普通 `git push` 一般可直接用

---

## 六、数据库纪律

- **禁止触碰生产 DuckDB**（红线）；验证优先"零 DB / 内存态"
- 迁移 / 清理前：**备份 → 打印要删什么 → 用户拍板 → 才执行**
- 关键库：DuckDB `backend/data/duckdb/aibi.db`（业务）/ SQLite `backend/data/aibi.db`（元数据）

---

## 七、内部端点 env 闸门（ISS-025 Batch2）

- **是什么**：73 个内部/系统端点（/brain/*、/llm/*、/exceptions/*、/dependency-graph、/trigger、/recover、/skills、/stats、/status、/chat/test/*、/tokens/_internal/* 等）受 env 闸门 `ENABLE_INTERNAL_ENDPOINTS` 保护。
- **prod 默认收口**：不设或 `=false` → 这些端点必须带有效 bearer 令牌，否则 401（关闭匿名访问缺口）。**生产部署务必保持收口。**
- **dev 放开**：`.env` 设 `ENABLE_INTERNAL_ENDPOINTS=on`（on/true/1 均可）→ 放行匿名访问，方便本地联调。仅本机 dev 用，切勿上生产。
- **验证**：
  ```powershell
  # dev（.env=on）重启后端后，匿名应 200
  curl http://127.0.0.1:8000/api/v1/skills        # 200
  # prod（未设/false）匿名应 401
  curl http://127.0.0.1:8000/api/v1/skills        # 401
  ```
- **改完重启才生效**：`settings` 在进程启动时读取一次，改 `.env` 后必须重启后端（见第一节，勿硬杀）。

## 八、最后更新

- **时间**：2026-10-03
- **版本**：v2（草稿 → 转正）
- **状态**：启动 / 停止 / 故障 / 测试 / push / DB 纪律 六节已齐
## ENABLE_API_DOCS（night25 Task G · API 文档暴露闸门）

- **作用**：控制 FastAPI 的 `/docs`（Swagger）、`/redoc`、`/openapi.json` 三个公开文档端点是否暴露。
- **取值**：`on`/`true`/`1` 放开；其余（含未设置）= 隐藏。
- **默认值**：`False`（prod 安全）。与 `DEBUG` **解耦**——即便 `DEBUG=true`，prod 部署也应显式 `ENABLE_API_DOCS=false` 隐藏文档，避免公开 schema 暴露后端路由面。
- **dev**：`backend/.env` 已设 `ENABLE_API_DOCS=on`，保留文档便利。
- **prod**：`.env.example` 默认 `false`；上线时务必确认未设 `on`（或删除该行）。
- **安全影响**：隐藏后，openapi 路由从「无鉴权 15」降为「无鉴权 12」（减少 3 个公开 schema 端点）；dev 仍 15。验证见 night25 Task G。
