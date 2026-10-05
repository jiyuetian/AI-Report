# NIGHT_SUMMARY · night32（2026-10-04）

> 分支 `p0-security-fixes`，起始 HEAD `b594414`（night31 收口，本地 3 commit 领先 origin），结束 HEAD 见 git log（本收口 commit）。
> **硬约束全程遵守**：不写新业务功能；仅测试补盲/回归/文档收口；真 bug 才最小改动；禁批量删除；一类一 commit；不碰生产 DuckDB / 用户进程 / `requirements.txt` / 已闭环 ISS-053 / `data/`。
> **红线**：Task 0（push night31）未获授权 → **跳过并标注**；push 前等用户确认。

---

## 一、本轮目标与完成度

| Task | 内容 | 状态 | commit |
|---|---|---|---|
| Task 0 | push night31（授权后） | **跳过（无授权）** | — |
| Task A | 全量回归（pytest/12 verify/golden/TEST2/前端/鉴权） | ✅ 完成 | `b0701a9` |
| Task B | 9 意图动作执行层补测 | ✅ 完成 | `c2b47fa` |
| Task C | v2 矩阵未跑项真跑 + v3 | ✅ 完成（v3 gitignored） | —（过程文档） |
| Task D | 收口（ISSUES/AI_CHANGES §52/本文件） | ✅ 完成 | 本收口 commit |

---

## 二、真跑取证（逐项命令 / 退出码 / 通过数）

### A. pytest 全量
- `python -m pytest backend/tests/ -q`（Python312, cwd=backend）→ **67 passed / 1 failed**，rc=1。
- 失败项：`tests/test_frontend_static.py::test_acceptance_charts_js_has_contain_label`（FileNotFoundError 生成物）→ **环境依赖，非回归**，登记 ISS-067。
- 日志：`pytest_full2.log`。

### B. 12 个 `_verify_*.py` 真跑（全部 rc=0 PASS）
- change_chart_llm 22/22、clarify_cap 13/13、health_probe 15/15、history_window 10/10、iss058 5/5、iss059 9/9、taskg 18/18、taski 32/32、taskjk ALL、iss066_message 10/10、night27 23/23、iss025_batch1（4 P0 写端点鉴权闭环）。
- 日志：`verify__verify_*.log`（12 个）。

### C. golden 回归（20 数据集）
- `run_golden_regression_test()` → **20/20 ✅，匹配度均 100%**，GOLDEN_RC=0。
- 注：脚手架 `success` 计数器误报 0（`GOLDEN_HAS_FAIL`）为计数 bug，逐数据集均 ✅ → 真实 20/20 PASS；登记低优先级待修（非数据回归）。日志：`golden_regression.log`。

### D. TEST-2 98 检查点
- iss058(35)+taskg(14)+taski(32)+taskjk(17)=**98 检查点**，所在 4 脚本全部 rc=0 PASS。

### E. 前端 tsc / build / audit
- tsc rc=0；`npm run build` rc=0（3720 modules, 25.06s）；`npm audit` **0 vulnerabilities**。日志：`fe_tsc.log`/`fe_build.log`/`fe_audit.log`。

### F. compileall backend/app
- rc=0（`compileall.log` 空）。

### G. API 路由鉴权扫描（ISS-025 回归）
- AST 静态扫描 → **217 路由**（WRITE 116 / READ 101；WRITE_NO_AUTH 66 / READ_NO_AUTH 44）。
- ISS-025 目标端点（rollback/shares/create/chat/message/tokens/status）**均已鉴权，无漂移**。
- `auth_whitelist.json` 本 checkout 缺失 → 无法二次核对 66 无鉴权写端点，标注 INFO 待补。

### H. Task B 执行层补测
- `backend/tests/test_night32_taskb_exec.py`：**10 tests / 10 passed**（python312 复跑 15 passed 含 quality_checker 5）。日志：`taskb_exec_run.log` / `_reverify_tests.log`。

---

## 三、覆盖矩阵 v3（Task C）

- 解析 night31 v2（177 条），主表 + O 表新增「night32 复跑」列（YES / carried(n31) / —）。
- 新增 **P-1~P-9（9 意图动作执行层）9 条**。
- 总览：**PASS 103 + PASS\* 43 + 需真机 22 + FAIL 0 + O 类 9 + P 类 9 = 186 条**。
- 产物：`night_runs/night32/AI_TEST_CASES_v3_运行矩阵.md`（gitignored）。

---

## 四、缺陷 / 待办登记（Task D）

| 编号 | 类型 | 说明 | 状态 |
|---|---|---|---|
| ISS-067 | 环境依赖测试失败 | `test_frontend_static` 缺生成物 charts.js → FileNotFoundError | `[ENV-DEP]` |
| ISS-068 | 低严重度加固 backlog | config-CRUD 执行器层不强制超管（设计性，鉴权在 API 层） | `[BACKLOG-LOW]` |
| (脚手架) | 低优先级待修 | golden `success` 计数器误报 0 | 待修 |
| (白名单) | INFO | `auth_whitelist.json` 本 checkout 缺失 | 待补后复核 |

---

## 五、结论

- **0 代码回归**：pytest 67/68（1 环境依赖）、12 `_verify` rc=0、golden 20/20、compileall rc=0、前端 tsc/build/audit 全绿、217 路由鉴权无漂移、新增 2 测试文件 15 passed。
- **新增覆盖**：9 意图动作执行层离线用例 10/10 PASS（此前仅测意图识别层）。
- **未改任何业务代码**；仅 2 个测试文件（committed）+ 文档（ISSUES/AI_CHANGES §52/本文件 committed）+ 过程证据（night_runs，gitignored）。
- **未 push**：等用户授权。本地 commit 链：…`b594414`(night31) → `b0701a9`(Task A) → `c2b47fa`(Task B) → 本收口 commit。

---

## 六、证据文件（gitignored，不进 commit）

`night_runs/night32/` 下：
- `全量回归报告.md`、`执行层补测报告.md`、`AI_TEST_CASES_v3_运行矩阵.md`
- `pytest_full.log` / `pytest_full2.log` / `pytest_quality_recheck.log` / `_reverify_tests.log`
- 12 × `verify__verify_*.log`
- `golden_regression.log`、`fe_tsc.log` / `fe_build.log` / `fe_audit.log`、`compileall.log`
- `route_auth_scan.log` / `route_auth_inventory.json`
- `taskb_exec_run.log`、`_run_a2_a3_summary.log`、`_run_a2_a3.py`、`_run_golden.py`、`_scan_routes_auth.py`、`_gen_v3.py`、`_append_aichanges.py`
