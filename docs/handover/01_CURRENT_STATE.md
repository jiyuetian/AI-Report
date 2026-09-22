# 01 · 当前状态快照（CURRENT_STATE）

> 时间：2026-09-22 夜 ｜ 交接 HEAD：`0ba98b1`

## 1. 版本控制

| 项 | 值 |
|----|----|
| 分支 | `p0-security-fixes`（已推 origin，与远端同步） |
| HEAD | `0ba98b1` docs: 阶段6 ISS债清单 |
| 工作树 | clean（无未提交改动；`defect_fix_evidence/` 等本地残留已被 `.gitignore` 忽略，不入库） |
| `main` | `bc31cd1`（远端已 gone，未合并；勿在此分支工作） |

## 2. 后端运行状态

- **当前：已停止**（大扫除阶段1 为归档分身库曾强杀后端进程，符合预期）。
- 启动器：`backend/run_backend.py`（内部 chdir 到 `backend/` + B5 单实例守卫 + DuckDB 启动 fail-fast）。
- 默认端口：**8000**。B5 守卫会写 `backend/.backend.pid`，重复起会拒绝。
- 鉴权：JWT；dev `SECRET_KEY=local-dev-secret-key`；可用 stdlib `hmac` 本地 mint token 做接口联调。
- LLM：主用 **kimi-k3**（商汤 SenseNova 聚合网关 `https://token.sensenova.cn/v1`，OpenAI 兼容单 key 路由）；网关要求 `business_type=chat`，kimi 系列仅允许 `temperature=1`。

## 3. 数据库（已备份 + 归档）

| 库 | 引擎 | 路径 | 大小 | 状态 |
|----|------|------|------|------|
| 业务主库 | DuckDB | `backend/data/duckdb/aibi.db` | ~134 MB | 真相库，已备份至 `data/backups/`（阶段1.3） |
| 元数据 | SQLite | `backend/data/aibi.db` | ~6.1 MB | 真相库（users/token_quota/chat_session） |
| 分身/QA 库 | 混合 | `backend/data/_archive/`（20 个） | — | 已归档，可恢复，建议定期清旧副本 |

> 双库同名历史冲突已由 `718019d` 根治（绝对路径 + fail-fast），`.env.example` 已指正指 `aibi.db`。

## 4. 前端

- 栈：React + TS + Vite，端口 **5173**。
- 守卫 `App.tsx` `ProtectedRoute` 仅读 `localStorage['user'].roles` 做 UX 门禁，**非安全边界**（真实校验在服务端）。
- 打包：`frontend/node_modules` 已存在；`npm run dev` / `npm run build`。

## 5. 本机工具链

| 工具 | 路径 |
|------|------|
| Python（主用，managed） | `C:/Users/Asus009/.workbuddy/binaries/python/versions/3.13.12/python.exe` |
| Node（主用，managed） | `C:/Users/Asus009/.workbuddy/binaries/node/versions/22.22.2-3/node.exe` |
| Git | `git.exe -C "<绝对路径>"`（见陷阱 1） |
| 出口代理 | 7897（Clash），后端访问 LLM 网关需走代理 |

## 6. 阶段进度（10 阶段）

| 阶段 | 状态 | 产出 |
|------|------|------|
| 0 全项目扫描 | ✅ | `docs/PROJECT_HEALTH_CHECK.md` |
| 1 遗留问题 | ✅ | `693d90c` 假告警修复 + 停服备份归档 20 分身库 |
| 2 定规范 | ✅ | `RULES.md` + `docs/CONVENTIONS.md` + `CHANGELOG.md` |
| 3 清理 | ✅ | 7 个根级 .md 归位 `docs/` + `.gitignore` 防护 + `.env.example` 修正 |
| 4 代码规范化 | ⏳ | 见 `03_PENDING.md`（命名 0 违规，仅安全档待做） |
| 5 全测试 | ✅(分阶) | 每类改动后已跑 tsc/py_compile/health |
| 6 ISS 债清单 | ✅ | `docs/issues/ISSUES.md`（`0ba98b1`） |
| 7 全量回归 | ⏳ | 移交明早（见 `06_MORNING_CHECKLIST.md`） |
| 8 夜跑交接包 | 🔧 | 本目录（进行中） |
| 9 AI 对话 Top3 | ⏳ | 时间够才做（ISS-015） |
| 10 明早交付 | ⏳ | `night4/NIGHT_SUMMARY.md` |
