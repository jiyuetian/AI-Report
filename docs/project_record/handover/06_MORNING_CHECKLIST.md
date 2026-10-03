# 06 · 明早清单（MORNING_CHECKLIST）· v2

> 可勾选。开工第一件事按顺序走，异常先查 `05_KNOWN_TRAPS.md`。
> **视角**：night19 开工。

## A. 拉取与核对（5 分钟）

- [ ] `git.exe -C '<路径>' pull --ff-only` → 应在 `p0-security-fixes`，HEAD `af4fd5b`
- [ ] `git.exe -C '<路径>' status -sb` → 工作树 clean
- [ ] 读 `handover/README.md` + `01_CURRENT_STATE.md` 一遍

## B. 起服务（10 分钟）

- [ ] 起后端：`& 'C:/Users/Asus009/.workbuddy/binaries/python/versions/3.13.12/python.exe' 'backend/run_backend.py'`（managed python）→ 无 `[DUCKDB-FAIL]`、打印 `ds_*` 表数
- [ ] `GET /health` → 200
- [ ] 起前端：`& node node_modules/.bin/vite` → `http://localhost:5173` 200
- [ ] 浏览器实开首页，确认无白屏/报错

## C. night18 基线复跑（10 分钟，全绿才动手）

```powershell
$PY = 'C:/Users/Asus009/.workbuddy/binaries/python/versions/3.13.12/python.exe'
& $PY 'backend/_verify_taskg.py'    # 14/14
& $PY 'backend/_verify_taski.py'    # 32/32
& $PY 'backend/_verify_taskjk.py'   # 17/17
& $PY 'backend/_verify_iss058.py'   # 35/35
& $PY -m py_compile 'backend/app/**/*.py'
cd frontend ; npx tsc --noEmit
```

- [ ] 全绿（98 检查点 + py_compile + tsc 三绿）

## D. 认领任务（对齐 `03_PENDING.md`）

**建议主线（P0）**：

- [ ] **主线选一**（三选一，用户拍板）：
  - [ ] 阶段 9-A：多轮对话历史稳定注入（推荐；改动 `chat.py` + 会话上下文管理，中风险）
  - [ ] 阶段 9-B：主链路 LLM 结构化提取（部分决策改走 LLM json_mode）
  - [ ] 阶段 9-C：澄清循环最大轮次退避（避免反复追问）

**建议顺手（<30 分钟）**：

- [ ] ISS-059：`compute_stats` / `compare_two_periods` 内 `e["data"]` → `e.get("data", {})`；`UsageStats.record_event` 加 `data: Dict[str, Any] = {}` 类型注解（<5 分钟）

**拍板项（用户决定才做）**：

- [ ] ISS-030：glm-5.3-flash 资源包 10-24 到期——切 `glm-4.5-air` 还是续包？（建议 10-20 前拍板）
- [ ] Dependabot 1 high：评估升级影响（先读 Dependabot PR 描述）

## E. 每类改动自检（push 前）

- [ ] `py_compile` 全绿
- [ ] `tsc --noEmit` 全绿
- [ ] 对应 `_verify_*.py` 全 PASS
- [ ] `/health 200`
- [ ] 前端页面 200 + 无 console 报错
- [ ] **AI 对话真跑**：一条自然语言修改指令，确认绿标 + 图表变化 + 撤销闭环

## F. 收尾

- [ ] 一类一 commit：`git add <具体文件>` + `git commit -m "feat/fix: 一类一说明"`
- [ ] 一类一 push：`git push origin p0-security-fixes`（**注意陷阱 8**：不要 `<your-branch>` 占位符）
- [ ] push 后验证：`git rev-list --count origin/p0-security-fixes..HEAD` 应为 0
- [ ] 若失败：`git revert <commit>` 回退，**不要 `reset --hard`**
- [ ] 写 `night19/ROUND_NOW.md`（过程）+ `night19/NIGHT_SUMMARY.md`（收尾）
- [ ] 更新 `AI_CHANGES.md` 台账（加 §15）
- [ ] 若开新 ISS：追加 `ISSUES.md`（编号顺延 ISS-060）

## G. 收尾红线（三条硬要求）

1. **闭环定义**：commit + push + 远程 tip 一致 + 台账登记 + NIGHT_SUMMARY 写完 = 一轮结束。
2. **回归资产化**：新脚本 `_verify_*.py` 必须入库（除特殊调试），失败也要保留 FAIL 记录。
3. **ISS 编号不复用**：新问题顺延下一个编号，不复用旧 ISS（ISS-037 已澄清）。
