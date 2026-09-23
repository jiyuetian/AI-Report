# OPEN_QUESTIONS.md — 待拍板事项

> 凡涉及"删数据 / 改语义 / 引新依赖 / 架构改动"，停下记录于此，等你拍板后再动。
> 更新规则：拍板后把该项移到 PROJECT_STATUS.md 的对应项，并划掉。

---

## Q1. 1.3 Event loop is closed — 真凶假设 + 路演前必须本机验证
- **现象**：`_start.log` 报 `[LLM] LLM未知错误: Event loop is closed`。
- **已做（防御性 hardening，非根治）**：httpx client 按 `(loop_id,name)` 分键、信号量 per-loop、db 导入独立 loop。
  本沙箱（Py3.12 + httpx0.28.1）这些库本身已 loop-lazy，**无法在此复现原错误串**，故无法 100% 确认已消除。
- **⚠️ 真凶假设（架构反模式）**：`action_executor.py:653` / `intent_classifier.py:240,656` 用
  `ex.submit(lambda: asyncio.run(llm_chat(...)))` 在**线程池**跑整套异步 LLM 调用。
  线程池内 `asyncio.run` 创建的是工作线程局部 loop，而 httpx.AsyncClient 等若在主线程旧 loop 上绑定过，
  跨 loop 复用即抛 "Event loop is closed"。这是最可能的真凶。
- **待拍板**：是否做深度重构（改为在主 loop `run_coroutine_threadsafe` 或调用方直接 `await`，需确认 async 上下文）？属架构改动，工作量中。
- **🔴 路演前必做**：在你本机真实跑一次 LLM 对话/生成，确认 `[LLM] LLM未知错误: Event loop is closed` 不再出现；
  若仍出现，再启动深度重构（不要带这个 bug 上路演）。沙箱无法替你验证。

## Q2. 1.8 版本回退语义
- 现状：回退只还原 `dashboard.config`（图表结构），图表数值来自 DuckDB 不还原 → 用户觉得"没生效"。
- 待拍板：A) 仅让"结构回退"可见即可（低成本，改前端提示+刷新）；B) 把 DuckDB 数据也纳入版本（高工作量，需版本化数据集快照）。
- ✅ **已拍板（2026-09-21）**：路演前只做 A（一行级提示，已落地 DashboardOps.tsx："已回退到 X：图表结构已还原（数值来自数据源故不变）"）；B 数据快照语义放路演后。见 PROJECT_STATUS 1.8。

## Q3. 1.9 导出 PDF/Excel/PNG 真实现
- 现状：上一轮仅做"诚实 not_implemented"占位（未生成文件）。
- 待拍板：引入纯 Py 依赖 reportlab(PDF) / openpyxl(Excel) / matplotlib(PNG) 真生成并落 ExportTask？
  三项均纯 Py、无外部服务，风险低，但属"引新依赖"需你确认。
- ✅ **已拍板（2026-09-21）**：路演前只做 PDF。采用 reportlab+matplotlib **纯 Python 真实生成（无需 headless 浏览器）**，已落地 export_service._export_pdf_real + main.py /downloads 静态路由（实测产出 91KB 合法 PDF 可下载）；Excel/PNG 放路演后（当前仍诚实 not_implemented）。见 PROJECT_STATUS 1.9 + ev_19_pdf_proof.md。

## Q4. 1.10 附录 B 行级明细
- 现状：CleanRule 模型无 old/new/row 列，后端不采集行级前后值。
- 待拍板：后端清洗前 SELECT 受影响行、UPDATE 后 SELECT 新值、diff 落新表 `clean_rule_rows`；前端加"行/原值/新值"三列。属后端增强 + 新表，需你确认。
- ✅ **已拍板（2026-09-21）**：路演前不做行级明细，仅加"影响行数"统计（比"策略 winsorize"更具体）。已落地 appendix_service._clean_log（apply winsorize 现显示真实 affected_rows=2）；行级明细 + 新表 `clean_rule_rows` 放路演后。见 PROJECT_STATUS 1.10 + ev_110_affected_rows_proof.md。

## Q5. 5.1 清测试残留（46 用户 / 24 看板 / 30 数据集 / 7 分享）
- 待拍板（三选范围）：A) 全删测试用户？B) 全删测试看板/数据集？C) demo 种子（`risk_demo_v2_*`）保留 or 删？
- 纪律：先给清单+备份+顺序，你拍板后我才生成 ID 级删除脚本，执行前再确认一次。方案见 `item6_cleanup_plan.md`。

## Q6. 1.6 残留：S4b 分析说明文本失败不弹窗
- 现状：生成看板时，S1/S2/S3 的 AI 失败都会经 `_request_user_choice` 暂停并弹窗（已实测）。
  但 **S4b 分析说明文本**（brain_run_sse.py:1011）的 LLM 调用失败仅 `try/except` 静默回退为规则文案，**不暂停、不弹窗**。
- 影响：S4b 非核心（仅看板顶部"AI 分析摘要"），看板仍正常生成；但若要求"任何 AI 失败都弹窗"，可把 S4b 也接入 `_request_user_choice`。
- 待拍板：是否覆盖 S4b？属小改动（低风险），确认后我接 `_request_user_choice` 并复用现有 Modal。

## Q7. 1.7 暗色模式范围（待确认，未改代码）
- 现状：前端无统一明暗主题（无 ConfigProvider darkAlgorithm；组件大量硬编码色如 `rgba(0,0,0,.03)`/`#1677ff`）。
- 方案已出：`defect_fix_evidence/final_fixes/plan_17_darkmode.md`（含现状/组件清单/配色原则/改动量风险工时/路演是否必演示）。
- 待拍板（三选一）：A) 路演前不做（建议降 P2）；B) 路演前做全量；C) 路演前只做图表+仪表盘核心。
- 未改代码，等你确认范围后再动。

## Q8. 1.6 残留：规则兜底下 S3 图表生成仍较慢
- 实测（ev_16b_e2e）：死 LLM → 弹窗 → 点"用规则生成"(resume rule_fallback) → 看板最终完成（chart_count=4, generated_by=rule_engine），但**耗时约 125s**。
- 原因：rule_fallback 仅绕过 probe 暂停，S3 图表生成阶段可能仍尝试 LLM 调用（超时重试）未完全跳过 LLM。
- 影响：路演若现场 AI 真挂、用户选规则生成，需等 ~2 分钟才出看板（可接受但不顺畅）。
- 待拍板：是否让 S3 也完全跳过 LLM（接 rule_fallback 标志跳过 LLM 分支）？属小改动，确认后做（与 Q6/S4b 同类）。
