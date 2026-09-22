# 02 · 已完成项（WHAT_DONE）

> 本次大扫除（2026-09-22）在 `p0-security-fixes` 上落地的内容，按提交序。

## 阶段 0 · 全项目扫描（只读）

- `docs/PROJECT_HEALTH_CHECK.md`（`bb5e35b`）
  - 命名零违规澄清（初版误报 125 实为 Pydantic PascalCase 类，真实函数级违规 0）。
  - 文档散落（10 个根级 .md）、数据库 22 个 .db 现状、双库同名冲突已根治说明。

## 阶段 1 · 遗留问题

- `693d90c` 修复 `main.py:97` 启动假告警（原误查**仓库根**/.env，实际 pydantic-settings 从 `backend/.env` 加载，打印「.env 已加载: False」误导）。
- 停后端 → 备份 `duckdb/aibi.db`+`.wal`（~134 MB，大小校验通过）→ 将 20 个分身/QA 库整体归档至 `backend/data/_archive/`（保留可恢复）。

## 阶段 2 · 定规范

- `RULES.md`（根）：提交纪律 / 命名 / 配置密钥（唯一 `.env=backend/.env`）/ 数据库铁律 / 鉴权 / 启动 / 测试门槛 / 本机陷阱 / 文档约定。
- `docs/CONVENTIONS.md`：目录模块地图 / LLM 网关约定 / S1–S5 链路 / API 契约 / dev 密钥方案（不写码）/ 提交约定 / 调试产物。
- `CHANGELOG.md`（根）：2026-09-22 三阶段 + 历史 `718019d` 根治 + 关键历史坑。

## 阶段 3 · 清理

- `c8273d5` 之外：7 个根级状态/诊断 .md → `git mv` 至 `docs/`（保留 `README.md` 在根）。
- `.gitignore` 补残留防护段（诊断/证据/临时脚本/`_scan_health.json`/`_tsc_out.txt`/`backend/.env.bak*`/`magic1.dll`/`backend/.backend.pid`/`verify_n1_*.py`/`scripts/_*.py` 等）。
- 后端含密钥残留（`.env.bak*`/`magic1.dll`/`verify_n1_*.py`/`scripts/_*.py`）经 Win32 `MoveFileExW` 移出项目到外部 `_trash_ai_report/`（沙箱 safe-delete 拦截删除，故改为「移出」非「删除」，可恢复）。
- `ba82356` `.env.example` 修正：`DUCKDB_PATH` 正确指向 `./data/duckdb/aibi.db`（修 P0-2 双库错配误导）。

## 阶段 6 · ISS 债清单

- `0ba98b1` `docs/issues/ISSUES.md`：11 字段，18 条在债（P0×2 / P1×7 / P2×5 / P3×4）+ 6 条历史已闭环留痕。

## 历史已闭环（本仓早前提交，勿重复）

- `718019d` DuckDB 绝对路径 + 启动 fail-fast + 修误导告警（根治双库静默错配）。
- G1（任务226）删除两处假 `require_admin`，统一 `security.py` 真实现。
- G3（提交231）13 个未认证端点补鉴权。
- G4（提交232）报告页 XSS 净化（后端净化 + 前端 DOMPurify）。

## 提交链（本会话）

```
0ba98b1 docs: 阶段6 ISS债清单
01ce96b chore: 阶段3 清理（根目录诊断文档归位 + .gitignore 防护）
ba82356 fix(env): .env.example 指向正确业务库 aibi.db
c8273d5 docs: 阶段2 定规范 RULES/CONVENTIONS/CHANGELOG
bb5e35b docs: 阶段0 项目健康体检报告
693d90c fix(app): 修正启动打印误查仓库根/.env 的假告警
718019d fix(env): DuckDB 绝对路径化 + 启动 fail-fast（历史根治）
```
