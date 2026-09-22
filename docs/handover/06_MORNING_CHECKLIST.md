# 06 · 明早清单（MORNING_CHECKLIST）

> 可勾选。开工第一件事按顺序走，异常先查 `05_KNOWN_TRAPS.md`。

## A. 拉取与核对（5 分钟）

- [ ] `git pull --ff-only` → 应在 `p0-security-fixes`，HEAD `0ba98b1`
- [ ] `git status -sb` → 工作树 clean（本地 `defect_fix_evidence/` 等被忽略，不显）
- [ ] 读 `docs/handover/README.md` + `01_CURRENT_STATE.md` 一遍

## B. 起服务（10 分钟）

- [ ] 起后端：`python backend/run_backend.py`（managed python，绝对路径）→ 看启动日志无 `[DUCKDB-FAIL]`、打印 `ds_*` 表数
- [ ] `GET /health` → 200
- [ ] 起前端：`vite` → `http://localhost:5173` 200
- [ ] 浏览器实开首页，确认无白屏/报错（暗色模式顶栏应为深色）

## C. 阶段 5 八层自测（按改动范围选跑）

- [ ] `npx tsc --noEmit`（前端类型）
- [ ] `python -m py_compile backend/app/**/*.py`（后端编译）
- [ ] `pytest backend/tests -q`（单测，若有）
- [ ] 核心链路：上传样例 → 质检 → 清洗 → 生成看板 → 附录 → 血缘 → 列表统计（参考 `ai-report-acceptance-report/`）
- [ ] AI 对话真跑：发一条自然语言修改，确认绿标（`generation_mode=ai`）+ 图表实际变化
- [ ] UI 真截图：看板/血缘/质检/管理后台各一屏

## D. 认领任务（对齐 `03_PENDING.md`）

- [ ] P0：ISS-003 横向越权 → 走红线（停服→备份→列引用→回滚）
- [ ] P0：ISS-020 导出假成功 → 先实测复现
- [ ] P1：ISS-001/002/004/005/010 按序推进，一类一 commit+push
- [ ] P3：ISS-013/016/017 随阶段 4 收口

## E. 收尾

- [ ] 每类改动跑完 B/C 对应层，全绿再 `push`
- [ ] 若中途失败：`git revert <commit>` 回退，不要 `reset --hard`
- [ ] 阶段 7 全量回归通过后，更新 `night4/NIGHT_SUMMARY.md`（阶段 10）
- [ ] 若做阶段 9 AI 对话 Top3：改完补 UI 真截图证据
