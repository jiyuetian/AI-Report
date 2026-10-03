# 01 · 当前状态快照（CURRENT_STATE）· v2

> 时间：2026-10-03 夜 ｜ 交接 HEAD：`af4fd5b`（本地=远端）

## 1. 版本控制

| 项 | 值 |
|----|----|
| 分支 | `p0-security-fixes`（已推 origin，与远端同步） |
| HEAD | `af4fd5b` fix(test_runner): 兼容 IntegrationTestCase.run() bool 返回契约 |
| 前一提交 | `849ccba` fix(analytics): import time（night17 遗留） |
| 工作树 | clean（除 handover 7 文件本轮重写外，无其他未提交改动） |

## 2. 阶段进度（10 阶段 + Task A–K + ISS 系列）

| 阶段 / Task | 状态 | 关联 commit |
|------|------|--------|
| 0 全项目扫描 | ✅ | `bb5e35b` |
| 1 遗留问题 | ✅ | `693d90c` |
| 2 定规范 | ✅ | `RULES.md` + `docs/CONVENTIONS.md` + `CHANGELOG.md` |
| 3 清理 | ✅ | `01ce96b` |
| 4 代码规范化 | ⏳ | 见 `03_PENDING.md` |
| 5 全测试 | ✅（分阶）| 每类改动后已跑 |
| 6 ISS 债清单 | ✅ | `ISSUES.md` 27 条 |
| 7 全量回归 | ✅ **night18 全绿** | `_verify_*.py` 98 检查点 |
| 8 夜跑交接包 | ✅ **v2** | 本目录 |
| 9 AI 对话 Top3 | ⏳ | 待开（多轮历史注入 / 主链路 LLM 决策 / 澄清退避） |
| 10 明早交付 | ✅ | 每 night 有 `NIGHT_SUMMARY.md` |
| Task A 图表模板库 | ✅ | `a33f655` / `76e81ea` |
| Task B 链路规则引擎 | ✅ | `47681b1` |
| Task C 图表模板（前端）| ✅ | `76e81ea` |
| Task D 模块 B 收尾 + 登记 ISS-058 | ✅ | `269663c` |
| Task E ISS-048 对话格式漏点 | ✅ | `dd7af5c` |
| Task F ISS-045 LLM 退避重试 | ✅ | `fed1476` |
| Task G 最高权限 CRUD | ✅ | `a01deb1` |
| Task H 派生指标 14 项 | ✅ | `2932834` |
| Task I 下游重算一致性 C-16 | ✅ | `5f6c6a5` |
| Task J 使用统计 J-8 | ✅ | `45a7ad6` |
| Task K 全链路联调 | ✅ | `45a7ad6` / `e338981` |
| ISS-058 阈值调整 | ✅ | `f0cc1fb` |
| ISS-059 compute_stats 健壮性 | 🔧 **OPEN** | 待下轮顺手修 |

## 3. 后端运行状态

- **当前：已停止**（收尾阶段，无运行进程）。
- 启动器：`backend/run_backend.py`（内部 chdir 到 `backend/` + B5 单实例守卫 + DuckDB 启动 fail-fast）。
- 端口：**8000**；B5 守卫写 `backend/.backend.pid`，重复起会拒绝。
- 鉴权：JWT；dev `SECRET_KEY=local-dev-secret-key`；stdlib `hmac` 可本地 mint token。
- LLM：主用 **kimi-k3**（商汤 SenseNova 聚合网关 `https://token.sensenova.cn/v1`）；**七层 failover 链（以 `.env` `LLM_PROVIDERS` 为准）**：kimi-k3 → glm-4.5-air（zhipu）→ glm-4.7-flash（zhipu）→ glm-4.6v（zhipu）→ deepseek-v4-flash（sensenova）→ agnes-2.0-flash（agnes）→ sensenova-6.8-flash-lite（sensenova）。
- 网关要求：`business_type=chat`；kimi 系列仅允许 `temperature=1`；七层 provider 健康（zhipu 资源包到期风险见 ISS-030）。

## 4. 数据库

| 库 | 引擎 | 路径 | 大小 | 状态 |
|----|------|------|------|------|
| 业务主库 | DuckDB | `backend/data/duckdb/aibi.db` | ~134 MB | 真相库 |
| 元数据 | SQLite | `backend/data/aibi.db` | ~6.1 MB | 真相库（users/token_quota/chat_session）|
| 分身/QA | 混合 | `backend/data/_archive/` | — | 已归档 |

> DuckDB 绝对路径 + fail-fast 已根治（`718019d`）。

## 5. 前端

- 栈：React + TS + Vite，端口 **5173**。
- `frontend/node_modules` 已安装；`npm run dev` / `npm run build`。
- `DashboardPage.tsx` 给 `<ChatPanel>` 加 `key={urlId}`（ISS-038 双保险）。

## 6. 本机工具链

| 工具 | 路径 / 端口 |
|------|-------------|
| Python（后端运行时） | `C:/Users/Asus009/AppData/Local/Programs/Python/Python312/python.exe`（实测 `3.12.10`） |
| Python（agent 工具链，非后端） | `C:/Users/Asus009/.workbuddy/binaries/python/versions/3.13.12/python.exe` |
| Node | `C:/Users/Asus009/.workbuddy/binaries/node/versions/22.22.2-3/node.exe` |
| Git | `git.exe -C "<绝对路径>"`（陷阱 1）|
| **出口代理** | **7897（Clash）**——**已永久配置**：`netsh winhttp` + `HKLM\...\4073` 双写；不再需要每次 `set https_proxy` |

## 7. 本轮新资产（night17/18）

| 资产 | 位置 | 用途 |
|------|------|------|
| `_verify_iss058.py` | `backend/` | ISS-058 阈值调整 5 场景回归 |
| `_verify_taskg.py` | `backend/` | Task G CRUD 14 场景回归 |
| `_verify_taski.py` | `backend/` | Task I 派生指标 + 重算 32 场景回归 |
| `_verify_taskjk.py` | `backend/`（gitignored）| Task J/K 使用统计 + 全链路 17 场景回归 |
| `test_runner.py` | `backend/` | 统一 runner（`af4fd5b` 已修契约不匹配）|
| `METRIC_REGISTRY` | `backend/app/core/metric_registry.py` | 14 业务指标元数据 |
| `UsageStats` | `backend/app/core/usage_stats.py` | 内存态脱敏使用统计 |

## 8. 已完成的 night SUMMARY（可直接读）

- `night15/NIGHT_SUMMARY.md` — Task G 最高权限 CRUD
- `night16/NIGHT_SUMMARY.md` — Task H 派生指标 + Task I 下游重算
- `night17/NIGHT_SUMMARY.md` — Task J 使用统计 + Task K 全链路
- `night18/NIGHT_SUMMARY.md` — ISS-058 阈值调整 + TEST-2 全量回归
- `night14/NIGHT_SUMMARY.md` — Task A/B/C/D + ISS-058 登记
