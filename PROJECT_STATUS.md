# PROJECT_STATUS.md — AI-Report 断点文件

> 每开新会话先读此文件。已完成的不要重做；按【总清单】顺序一项一项来。
> 维护规则：每完成一项 → 划掉移入"已完成" → 落盘证据到 `defect_fix_evidence/final_fixes/` → 更新本文件。

---

## 当前阶段
**Layer 0（环境/路由）收尾 + Layer 1（路演 P0）推进中。**
已冻结基线：`p0-security-fixes` 分支，HEAD `73b0f36`，基线 tag `baseline-final-fixes`。
**本会话目标**：依纪律逐项推进 0.1→0.2→0.3→1.1→1.2→...，每项落盘证据 + 更新本文件。

---

## 总清单（状态图例：✅已完成 / 🔧进行中 / ⬜未开始 / 🛑待拍板）

### 第 0 层：环境与路由
- [x] 0.1 路由修复（DUCKDB_PATH=qa_aibi.db 启动后端）— 实测 5 图出数，证据 `item1_routefix.md`
- [x] 0.2 多实例防护（run_backend.py B5：pidfile + 端口检测，已提交代码）
- [⚠️] 0.3 环境隔离（部分完成：做了告警机制 + 启动横幅打印绑定库，未做物理隔离）— 本会话实测通过，证据 `ev_03_env_isolation.md`；**补充**：当前仍是"一个后端可静默指向任意库"（仅告警未强制），物理隔离（如启动脚本拒绝默认库/双库分离启动入口）未做，待后续 6.x 收口

### 第 1 层：路演 P0
- [✅] 1.1 附录 A/B 去 scroll.x（AppendixPanel.tsx A/B/C 三表仅 `scroll.y:360`，无 `scroll.x`）— 代码完；**视觉需本机确认（沙箱无浏览器不能截图）**，证据 `ev_11_visual_confirm.md`
- [✅] 1.2 多 key 重试 fail-fast（llm_gateway.py:80 MAX_RETRIES 2→1，退避封顶 0.5s）— 改完，计时模拟降为 1/5，证据 `ev_12_retry_fastfail.md`
- [✅] 1.3 Event loop is closed（防御性修复：httpx client 按 loop 分键 + 信号量 per-loop + db 导入独立 loop；路演前本机验证）— 证据 `ev_13_eventloop.md`
- [✅] 1.4 对话多字段截断（intent_classifier.py `_extract_add_charts` 改规则优先；原句"5 字段"全识别为 5 图，证据 `ev_14_15_out.out`）
- [✅] 1.5 对话产生垃圾图（action_executor.py 去掉 `first_dim_metric()` 臆造兜底，字段解析不到真实字段即跳过；混合 4真实+1垃圾→建4跳1，证据 `ev_14_15_out.out`）
- [✅] 1.6 AI 失败弹窗（生成看板路径：LoadingPage Modal + brain_run_sse `ai_awaiting` 已实现；本会话端到端实测：死 LLM→第14s `ai_awaiting=YES`→点"用规则生成"(resume)→看板完成(4图,rule_engine)；证据 `ev_16_ai_popup.md`+`ev_16b_popup_proof.md`；残留 S4b 见 Q2）
- [✅] 1.7 暗色模式（C 范围：图表+KPI+页面背景/导航，ECharts 主题切换已接）— **代码完成，本机视觉待确认**；新建 `chartThemeApply.ts` 集中注入；`DashboardPage.tsx`(主图+详情弹窗图) + `ChartRenderer.tsx`(line/bar/pie/scatter 四图) 接入 `useChartTheme`+`themeChartOption`；`DashboardPage.css` 加 KPI 暗色对比度；tsc EXIT=0。视觉证据用同色预览 `darkmode_preview.html` + matplotlib 栅格化 PNG（沙箱无浏览器）。证据 `ev_17_darkmode.md`
- [✅] 1.8 版本回退语义（路演前一行级提示："已回退到 X：图表结构已还原（数值来自数据源故不变）"，DashboardOps.tsx；数据快照语义留路演后）
- [✅] 1.9 导出 PDF 真现实（reportlab+matplotlib 纯 Python 真实生成 + /downloads 静态下载；Excel/PNG 留路演后，诚实 not_implemented）— 证据 `ev_19_pdf_proof.md`
- [✅] 1.10 附录 B 影响行数（apply winsorize 现填充真实 affected_rows；行级明细留路演后）— 证据 `ev_110_affected_rows_proof.md`

### 第 2 层：AI 含量
- [x] 2.1 AI 能力鉴定（已完成，证据 `ai_capability_appraisal.md`）
- [x] 2.2 Prompt 中心可编辑性（已完成）
- [✅] 2.3 能补的 AI 能力补齐（2.3-A 翻 `BRAIN_S2_USE_LLM` 默认 True + 2.3-B s2 加 `generated_by`/`ai_participated` 标记对齐 S3；hash `ed72f47`；mock 验证 `verify_23.py` 三用例全过）— 证据 `plan_23_ai_upgrade.md`
- [ ] 2.4 路演 AI 展示脚本（方案已出 `plan_24_roadshow_script.md`，待落地：前端绿/灰标渲染 + 演示数据 + 翻车保险话术）

### 第 3 层：UI 体验
- [ ] 3.1 上传页布局（上传后收缩，不占第一屏）
- [ ] 3.2 加载页方案 C（先出规则图，AI 后台增强）
- [ ] 3.3 KPI 卡片单卡留白（复查 + 修）
- [ ] 3.4 看板"无可绘制数据"（路由修复后验证）
- [ ] 3.5 AI 只会说"刷新试试"（修：让它能实查）
- [ ] 3.6 管理后台设置页占位项（隐藏或标注）
- [ ] 3.7 版本"预览/对比"空壳（隐藏或接真实）— 上一轮已禁用+标注"即将上线"部分

### 第 4 层：路演准备
- [ ] 4.1 演示脚本（5 分钟 + 10 分钟版）
- [ ] 4.2 演示前健康检查清单
- [ ] 4.3 翻车保险方案
- [ ] 4.4 隐藏空壳按钮
- [ ] 4.5 演示数据准备（独立库 + 预置看板）

### 第 5 层：数据清理（先给方案，拍板后动）
- [ ] 5.1 清测试残留（46 用户 / 24 看板 / 30 数据集 / 7 分享）— 方案 `item6_cleanup_plan.md`
- [ ] 5.2 管理后台数字自愈

### 第 6 层：项目规范（路演后）
- [ ] 6.1 根目录整理
- [ ] 6.2 建 RULES.md（架构铁律）
- [ ] 6.3 docs/ 完整结构
- [ ] 6.4 Git 规范
- [ ] 6.5 架构统一（3 套鉴权收口）
- [ ] 6.6 命名规范

---

## 已完成的项（做完划掉移过来）
1. **0.1 路由修复** — `DUCKDB_PATH=./data/duckdb/qa_aibi.db` 启动，`risk_demo_v2_05_合规月度表看板` 5 图出数（6列×12行）。证据：`defect_fix_evidence/final_fixes/item1_routefix.md` + `routefix_proof.html`。
2. **0.2 多实例防护** — `run_backend.py` 已实现 B5：pidfile 检测 + 端口占用检测，双进程抢 DuckDB 锁已杜绝。已提交。
3. **2.1 AI 能力鉴定** — 12 板块全接线非空壳；`s2_goal_generator` 半空壳（默认规则）。证据：`ai_capability_appraisal.md`。
4. **2.2 Prompt 中心可编辑性** — 用户确认已完成。
5. **0.3 环境隔离（⚠️ 部分完成）** — 启动横幅显式打印绑定库；`DUCKDB_PATH` 未设即告警（杜绝 0.1 类静默错库）；`.env.example` 补全业务库/元数据分离。证据 `ev_03_env_isolation.md`。**未做物理隔离**（仍靠告警，未强制拒绝默认库/双库分离入口），待 6.x 收口。
6. **1.1 附录 A/B 去 scroll.x（⚠️ 待视觉确认）** — 去掉 `scroll.x='max-content'` 锁宽，表格撑满容器，保留 `y:360` 纵向滚动。tsc 通过。证据 `ev_11_appendix_scroll.md`；**三 tab 截图需本机出**。
7. **1.2 多 key 重试 fail-fast（✅ 完成）** — `MAX_RETRIES=2→1` + 退避封顶 0.5s；切换可用 key 耗时从 3.25s→0.69s（≈1/5）。证据 `ev_12_retry_fastfail.md`。
8. **1.3 Event loop is closed（✅ 防御性修复）** — httpx client 按 `(loop_id,name)` 分键 + 信号量 per-loop + `database.py:26` 导入期独立 loop。py_compile 通过；本沙箱 lib 已 loop-lazy 无法复现原错，路演前需本机验证。证据 `ev_13_eventloop.md`。
9. **1.4 对话多字段截断（✅ 完成）** — `intent_classifier._extract_add_charts` 改规则优先（≥2 张直接采用，LLM 仅单图兜底）；原截图句"5 字段"实测全识别为 5 图。p2 回归 3 passed + `ev_14_15_out.out` ALL PASS。
10. **1.5 对话产生垃圾图（✅ 完成）** — `action_executor._execute_add_chart` 去 `first_dim_metric()` 臆造兜底；字段解析不到真实字段即跳过（不建垃圾「新增bar」）。实测：全垃圾→0 图；混合 4真实+1垃圾→建4跳1。`ev_14_15_out.out` ALL PASS。
11. **1.6 AI 失败弹窗（生成看板路径，✅ 已完成+实测）** — 非新增：`LoadingPage.tsx:425-455` Modal + `brain_run_sse.py:188/1323` `ai_awaiting` 已在前序提交实现；本会话端到端实测 `POST /brain/run`（死 LLM）→第15s `/status` 返回 `ai_awaiting=YES`（stage=probe, options=[rule_fallback,wait_retry]）→ 前端弹窗必触发。证据 `ev_16_ai_popup.md`。残留：S4b 分析文本失败仅静默回退不弹窗（记 Q2）。

12. **1.8 版本回退提示（✅ 完成）** — `DashboardOps.tsx` 回退成功 toast 改为"已回退到 X：图表结构已还原（数值来自数据源故不变）"。证据：`ev_16b_popup_proof.md` 同批；代码 diff 见 DashboardOps.tsx。
13. **1.9 导出 PDF 真现实（✅ 完成）** — `export_service._export_pdf_real`（reportlab+matplotlib 纯 Python 真实生成，无需 headless 浏览器）+ `main.py` 挂载 `/downloads` 静态下载。实测 `POST /exports/sync` 返回 `mode=sync` + `download_url`，文件 91KB 合法 PDF，`GET /downloads/...pdf`=200。Excel/PNG 仍诚实 `not_implemented`（留路演后）。证据 `ev_19_pdf_proof.md`。
14. **1.10 附录 B 影响行数（✅ 完成）** — `appendix_service._clean_log` 的 `rows_map` 覆盖 `done/ignored/todo` 三态并取最大 `affect_rows`，apply 阶段 winsorize 现显示真实"影响行数=2"（修复前全 None）。证据 `ev_110_affected_rows_proof.md`。
15. **1.6 端到端实测补全（✅ 完成）** — 死 LLM 后端实测：t=14s `ai_awaiting=YES`(probe,HTTP 502) → `POST /resume rule_fallback`(200) → 看板 `dash_e8c94106_87b068` 完成，`chart_count=4`，`generated_by=rule_engine`，`ai_participated=false`。证据 `ev_16b_e2e.py` + `ev_16b_popup_proof.md`。
16. **1.7 暗色模式（C 范围，✅ 代码完成，本机视觉待确认）** — 仅做「图表+KPI+页面背景/导航」，不扩全量。新建 `chartThemeApply.ts` 集中注入 ECharts 明/暗主题（取自 `CHART_THEMES`，无散落硬编码）；`DashboardPage.tsx` 主图(1157)+详情弹窗图(1336) 与 `ChartRenderer.tsx` 四图(line/bar/pie/scatter) 接入 `useChartTheme`+`themeChartOption`；`DashboardPage.css` 加 KPI 暗色对比度。tsc EXIT=0。视觉证据：`darkmode_preview.html`(本机可交互真截图) + `darkmode_light.png`/`darkmode_dark.png`(matplotlib 保真，沙箱无浏览器)。证据 `ev_17_darkmode.md`。
17. **2.3 AI 能力补齐（✅ 完成）** — 2.3-A：`config.py:40 BRAIN_S2_USE_LLM False→True`（默认走 LLM，守卫 `not llm_offline` 已安全）；2.3-B：`AnalysisGoal` 加 `generated_by` 字段、`generate_goals_llm_enhanced` 成功置 `llm`、`to_dict` 含 `generated_by`；`brain_run_sse.py` S2 段算 `s2_generated_by` 存 `ctx.shared`，dashboard_config 与 progress.detail 的 `ai_participated` 合并 S2+S3、新增 `s2_generated_by` 字段（路演可秀"目标生成也由 AI 参与"）。mock 验证 `verify_23.py` 三用例全过（默认LLM→6目标llm/ai=True；规则兜底→rule/False；LLM失败回退→rule/False）。hash `ed72f47`。方案 `plan_23_ai_upgrade.md`。

## 关键事实（怕忘）
- **跑后端用系统 Python 3.12**：`C:/Users/Asus009/AppData/Local/Programs/Python/Python312/python.exe`（非 workbuddy venv）。
- **启动命令**：`cd backend && DUCKDB_PATH="./data/duckdb/qa_aibi.db" <py312> run_backend.py`（端口 8000，HOST 127.0.0.1）。
- **git-bash shim 缺** `ls/cat/head/tail/grep/dirname/cd` → 用 python -c / Read / Glob / Write / Bash(python -c)。
- **所有 API 挂在 `/api/v1` 前缀**（`/health`=404，正确是 `/api/v1/health`）。
- **沙箱无浏览器**：UI 视觉验证需用户本机开 `http://127.0.0.1:8000/dashboard/dash_3716856d_35d769`；我以 tsc(EXIT=0) + 代码 diff + 真实 API 数据页 `routefix_proof.html` 作证据。
- **后端当前运行于 8000**（qa_aibi.db，正常实例，`llm_reachable:true`，含本会话 1.8/1.9/1.10 最新改动 + 之前 1.1–1.6 改动；1.6 死-LLM 实测实例已停）。
- **未提交改动（本会话新增）**：`export_service.py`+`main.py`（1.9 PDF 真实生成+/downloads 下载路由）、`appendix_service.py`（1.10 影响行数）、`DashboardOps.tsx`（1.8 回退提示 + 导出诚实化）、`AppendixPanel.tsx`（1.1 去 scroll.x）。
  此前未提交：`llm_gateway.py`/`database.py`（1.2/1.3）、`intent_classifier.py`/`action_executor.py`（1.4/1.5）、`exports.py`/`DashboardPage.tsx`、`run_backend.py`（0.3）。工作树可看 diff，要冻结提交请说一声。
- **提交 aa716cd** 仅删了 C 表（指标）的 `scroll.x`；A/B 表仍带 `scroll.x` → 1.1 根因。
- **版本回退接线已接**（rollback→onConfigReload→reloadConfig→GET /dashboards/{id}→setConfig），但"不感知"是语义问题：回退只还原 `dashboard.config`（图表结构），图表数值来自 DuckDB 不还原；相邻自动存档快照可能相同。

## 已知未查清（不要重复查）
- 0.1 路由已实测通过，勿重测。
- 2.1/2.2 已确认，勿重复鉴定。
- 1.8/1.10 根因已在 `LOCAL_TEST_FAILURES.md` 查清，勿重复查根因；直接进修复。
- 1.3 "Event loop is closed"：本沙箱（Py3.12+httpx0.28.1）lib 已 loop-lazy，无法在此复现错误串；
  已做防御性 per-loop hardening。路演前需本机真实跑一次确认消失（勿在本沙箱空耗复现）。
- `action_executor.py:653` / `intent_classifier.py:240,656` 的 `ex.submit(asyncio.run(...))` 线程池反模式是潜在根因，待拍板是否深度重构（见 OPEN_QUESTIONS.md）。

## 相关文档索引
- `defect_fix_evidence/final_fixes/item1_routefix.md` — 0.1 证据
- `defect_fix_evidence/final_fixes/LOCAL_TEST_FAILURES.md` — 本机 3 生效/3 未生效 根因（1.1/1.2/1.8/1.10 根因）
- `defect_fix_evidence/final_fixes/ai_capability_appraisal.md` — 2.1 证据
- `defect_fix_evidence/final_fixes/item6_cleanup_plan.md` — 5.1 清理方案
- `defect_fix_evidence/final_fixes/routefix_proof.html` — 真实数据快照证明页
- `defect_fix_evidence/fixes/aa716cd_AppendixPanel.diff` — aa716cd 仅改 C 表证据
- `OPEN_QUESTIONS.md` — 待拍板事项（删数据/改语义/引依赖）

## 待拍板（OPEN_QUESTIONS，见 OPEN_QUESTIONS.md）
- 1.8 版本回退语义：是否把 DuckDB 数据也纳入版本（工作量大）？还是仅让"结构回退"可见即可？
- 1.9 导出真实现：引入 reportlab(✅纯Py)/openpyxl(✅纯Py)/matplotlib(✅纯Py) 生成 PDF/Excel/PNG？
- 1.10 附录 B 行级明细：后端补采集 + 新表 `clean_rule_rows`？
- 5.1 清测试残留：A 全删测试用户？B 全删测试看板/数据集？C demo 种子保留 or 删？
