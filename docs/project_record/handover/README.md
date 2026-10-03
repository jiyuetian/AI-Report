# 夜跑交接包（Night Handover）· v2

> 分支：`p0-security-fixes` ｜ 交接 HEAD：`af4fd5b`（本地=远端，2026-10-03 已 push 完成）
> 生成：2026-10-03 夜 ｜ 更新人：教练（SenseNova）
> 版本：v2（取代 v1 的 `0ba98b1`，v1 内容已被 v2 覆盖）
> 目的：让接手 agent 在 **不重读会话** 的前提下，5 分钟内知道「现在在哪、改了什么、还剩什么、怎么起、坑在哪、下一轮该做什么」。

---

## 一、接手三步（必做）

1. 拉取核对：`git.exe -C "<绝对路径>" pull --ff-only` → 应在 `p0-security-fixes`，HEAD `af4fd5b`。
2. 起服务：按 `04_RUNBOOK.md` 起后端(8000)+前端(5173)；起不来先查 `05_KNOWN_TRAPS.md`。
3. 跑 night18 基线：`_verify_iss058.py`（35/35）+ `_verify_taskg.py`（14/14）+ `_verify_taski.py`（32/32）+ `_verify_taskjk.py`（17/17）+ `py_compile` → 全绿即环境 OK。

---

## 二、7 类文档导航

| 文件 | 内容 | 何时看 |
|------|------|--------|
| `01_CURRENT_STATE.md` | 分支/HEAD/阶段进度/运行态快照 | 第一眼 |
| `02_WHAT_DONE.md` | night1-18 全量提交链 | 想知道「动了什么」 |
| `03_PENDING.md` | OPEN ISS + 阶段 4/7/9 待办 | 认领任务前 |
| `04_RUNBOOK.md` | 起服务/测试/备份/回滚/push 命令 | 要动手时 |
| `05_KNOWN_TRAPS.md` | 本机 12 大陷阱（含 night17/18 新坑）| 任何异常先查这 |
| `06_MORNING_CHECKLIST.md` | 明早开工清单（night19 视角）| 开工时 |
| `07_ENV_SECRETS.md` | 密钥/网关/代理 注意事项 | 配环境时 |

---

## 三、红线（铁律，违反即回滚）

- 改 API 契约 → 同步改**全部**调用点。
- 改数据模型/schema → 停服 → 备份 `aibi.db`+`.wal` → 列引用 → 带回滚脚本。
- 一次只改一类；一类一 `git commit` + 一类一 `git push`；失败立即 `git revert`。
- push 前必过阶段 5 全绿（`py_compile` + `tsc --noEmit` + `_verify_*.py` 全 PASS + `/health 200`）。
- **代理 7897 已永久配置**：`netsh winhttp set proxy 127.0.0.1:7897` + `reg add HKLM\...\4073` 双写；不再需要每次手动 `set https_proxy`。

---

## 四、一句话现状

> **night5→night18 全部闭环**：AI 对话链路 6 层 failover 稳定、CRUD 走规则引擎 fail-fast、派生指标 14 项 + 下游重算一致性事件驱动、使用统计 + 全链路联调集成、ISS-058 阈值调整 undo 闭环；TEST-2 全量回归 98 检查点全 PASS；2 个真实生产 bug（`analytics.py import time` / `test_runner.py 契约不匹配`）修复。
>
> **剩余债**：`ISS-059`（compute_stats 未 `.get` 防御，<5 分钟改动）、`ISS-030`（glm-5.3-flash 资源包 10-24 到期，需拍板）、阶段 9 AI 对话 Top3（多轮历史注入 + 主链路 LLM 决策 + 澄清退避）待开。
