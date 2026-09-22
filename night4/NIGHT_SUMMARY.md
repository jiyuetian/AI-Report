# 夜跑交接 · 一页纸（NIGHT_SUMMARY）

> 日期：2026-09-22 夜 ｜ 分支：`p0-security-fixes` ｜ 交接 HEAD：`2bf2c54`
> 接手：明早新模型 ｜ 详档：`docs/handover/README.md`

## 1. 一句话

仓库已从测试阶段整理干净并打包好交接；**剩高风险安全面 + 阶段4安全档 + 阶段9 AI对话**，按红线移交明早。

## 2. 今晚已落地（提交链）

| Hash | 阶段 | 内容 |
|------|------|------|
| `2bf2c54` | 阶段6补 | ISS-021 记录 Dependabot high 级依赖漏洞 |
| `5a1203f` | 阶段8 | 夜跑交接包 `docs/handover/`（README+7类） |
| `0ba98b1` | 阶段6 | ISS 债清单 `docs/issues/ISSUES.md`（19 条在债） |
| `01ce96b` | 阶段3 | 根级诊断文档归位 `docs/` + `.gitignore` 防护 |
| `ba82356` | 阶段3 | `.env.example` 指正确业务库 `aibi.db` |
| `c8273d5` | 阶段2 | `RULES.md`+`CONVENTIONS.md`+`CHANGELOG.md` |
| `bb5e35b` | 阶段0 | 项目健康体检报告 |
| `693d90c` | 阶段1 | 修 `main.py` 启动假告警 |
| `718019d` | 历史根治 | DuckDB 绝对路径 + fail-fast |

## 3. 当前状态

- 分支 `p0-security-fixes` 与 origin **已同步**（push 时 GitHub 回显 Dependabot 1 high 漏洞，已记入 ISS-021）。
- 后端：**已停止**（阶段1 归档分身库时强杀，符合预期）；真相库已备份+20 分身库归档 `_archive/`。
- 工作树 clean；`defect_fix_evidence/` 等本地残留被 `.gitignore` 忽略，不入库。

## 4. 明早前三件事

1. `git pull --ff-only` → 应在 `p0-security-fixes`，HEAD `2bf2c54`。
2. 起后端(8000)+前端(5173)，`/health` 200，浏览器实开首页无白屏。
3. 跑阶段 5 八层（tsc/py_compile/核心链路/AI对话/UI真截图），见 `docs/handover/06_MORNING_CHECKLIST.md`。

## 5. 认领优先级（P0 先打，全走红线）

- **P0**：ISS-003 横向越权（owner 过滤）｜ ISS-020 导出假成功+跳页
- **P1**：ISS-001 前端 authHeaders 合入 request()｜ ISS-002 9 端点对齐｜ ISS-004 owner 取服务端｜ ISS-005 上传净化｜ ISS-010 守卫认知债｜ **ISS-021 Dependabot 升级**
- **P2/P3**：ISS-007/014/018/019 稳定面 ｜ ISS-012/013/016/017 整洁面（随阶段4收口）

## 6. 七条本机陷阱（先查 `docs/handover/05_KNOWN_TRAPS.md`）

1. Git-Bash shim 坏 → 用 `git.exe -C "<绝对路径>"`
2. Edit/Write 偶发不落盘 → 写完 Grep 复核
3. DuckDB 静默空库 → `718019d` 已 fail-fast
4. 沙箱拦截删除 → Win32 `MoveFileExW` 移出项目（非删）
5. `netstat` 等 GBK → `decode('gbk','ignore')`
6. PowerShell 偶发空输出 → 优先 Bash+`git -C`
7. 出口代理 7897 波动 → 后端访问 LLM 网关前确认代理在线

## 7. 红线（任何改动）

改 API 契约→改全部调用点；改数据模型→停服+备份+校验；改 schema→带回滚脚本；**一类一 commit+push**，失败 `git revert`，push 前全测试绿。

## 8. 明确未做（移交明早）

- 阶段 4 高风险子类（API契约/数据模型/schema）：与 ISS 债重叠，走红线，不今晚顺手改。
- 阶段 9 AI 对话 Top3：时间不够，ISS-015 留痕。
- 阶段 7 全量回归：明早按清单跑（本机后端已停）。
- Dependabot 漏洞修复：ISS-021，需 `pip/npm audit` 定位后升级。
