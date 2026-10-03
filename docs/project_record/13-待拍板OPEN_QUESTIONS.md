# OPEN_QUESTIONS.md — 待拍板事项

> 凡涉及"删数据 / 改语义 / 引新依赖 / 架构改动"，停下记录于此，等你拍板后再动。
> 更新规则：拍板后把该项移到 PROJECT_STATUS.md 的对应项，并划掉。
> **本版：v2，2026-10-03（追加 Q13–Q16，对齐 night18）。**

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

## Q9. 澄清类意图（clarify）到底该不该算一个 IntentType？（2026-09-24 临机决策，请复核）
- 现状：`IntentType` 枚举里没有 clarify，`chat.py` 原本 `IntentType(intent_result["intent_type"])`
  遇到 "clarify" 直接抛 ValueError 打断整条 SSE 流（表现为追问无回复、pending 不落库）。
- 我的处理：追问时 primary_intent 保留用户原意图（如 change_chart），并对非枚举值做 try/except 兜底。
- 待复核：更干净的做法是在 IntentType 里加 `CLARIFY = "clarify"` 成员并让前端据此渲染澄清卡片。
  属语义改动，未擅自做。

## Q10. 「真归因」需要数据源，但风控数据集的 DuckDB 物理表已不在
- 实测：`data/duckdb/aibi.db` 只有 QA 样例表 `ds_04d68399_*`；`risk_demo_v2_*`（贷款明细/客户风险画像）
  的 `ds_4bece390_*` 等物理表在所有 DuckDB 文件里都不存在（业务表已归档到 `data/_archive/duckdb/`）。
- 后果：「为什么逾期上升」只能做到"字段层面实查 + 定位到正确图表"，做不到"取数计算趋势/同比"。
- 待拍板：A) 把归档的 duckdb 表拷回活跃库再实现真取数归因；B) 明确告知路演只到"定位+字段核查"层；
  C) 改从 SQLite/文件源取数。选哪个我再来改。

## Q11. 可行性检查把泛指词当字段要求（「分析一下担保代偿风险」被硬拦）
- 位置：`backend/app/core/feasibility_checker.py:189 _check_field_existence`
  关键词表含「风险」，句中出现即判定"数据里没有该字段"→ severity=blocking，请求在到达分析前被拒。
- 我的判断：这个拦截本身是诚实的（数据集确实没有"担保代偿"字段），所以**没有动它**。
- 待拍板：A) 保持现状（宁可拒，不臆造）；B) 对 attribution/semantic 意图降级为 warning 放行；
  C) 增加"语义代理字段"映射（担保代偿风险 → 历史逾期次数/收入负债比）再分析。选哪个我再来改。

## Q12. ISS-025 剩余 74 个无鉴权端点，是否继续按批推
- 本批（6 个）选的是"写操作 + 落匿名账 + 前端已带 token"的高风险项，已真跑验证并过门禁。
- 剩余 74 个多为 brain/s1-s5 链路与 `_internal` 测试桩。
- 待拍板：A) 继续按"是否读写用户数据"分批（建议下一批：quality/fix、lineage/rebuild-all、
  exceptions/schema-heal 等会改数据的）；B) 只收口对外端点、`_internal` 测试桩靠部署层隔离；
  C) 暂停。另：本次只做了"必须登录"（认证），**未做归属校验（认证用户能否改他人资源）**，
  这是更大的攻击面，需单独立项。

## Q13. ISS-059 `compute_stats` 健壮性缺口 —— 顺手修还是单独轮？（night18 登记）
- 现状：`analytics.compute_stats` / `compare_two_periods` 直接 `e["data"]` 索引；事件缺 `data` 字段时 `KeyError` → 对比接口 500。night18 TEST-2 暴露。
- 修复：全部改 `e.get("data", {})`；给 `UsageStats.record_event` 加 `data: Dict[str, Any] = {}` 类型注解。零 DB、纯静态、<5 分钟。
- 待拍板：A) 下轮（night19）顺手修（建议）；B) 单独立项。

## Q14. Dependabot 1 high 依赖漏洞（default branch）
- 现状：GitHub Dependabot 在 **default branch（main/master）** 报 1 个 high；**不在** `p0-security-fixes`，**不阻断功能与推送**，属"有空再处理"。
- 取数难点：告警页需登录鉴权，匿名 WebFetch 拿不到；本机 **`gh` CLI 未安装**（`gh: 命令未识别`）。
- 两条路径：A) 浏览器登录 GitHub 直接看（哪个依赖 / 漏洞版本范围 / fixed 版本 / CVE/GHSA）；B) 装 `gh` 后 `gh api repos/jiyuetian/AI-Report/dependabot/alerts --jq '...'` 取结构化 JSON。
- 待拍板：拿到依赖名与版本后，评估影响面（default branch 代码路径是否真用到漏洞面）→ 给最小升级方案（改 `package.json` / `requirements.txt` 锁版本 + 重装）。**低优先，不阻断交付。**

## Q15. ISS-030 glm 资源包到期（10-25）—— 续包 or 切档？
- 现状：`glm-4.5-air` 免费 1200 万专属包 10-25 到期；到期后该层失效。
- 待拍板（建议 10-20 前）：A) 切 `glm-4.5-air`（已到期则换其他免费层）；B) 智谱控制台续包；C) 调整七层链顺序。
- 影响：仅影响 failover 备层可用性，主用 `kimi-k3` 不受影响。

## Q16. 阶段 9 AI 对话 Top3 先做哪个？
- 三项：① 多轮历史稳定注入（最多上 5 轮，超出截断）② 主链路 LLM 结构化提取 ③ 澄清循环退避。
- 待拍板：建议先做 **① 多轮历史稳定注入**（收益最直接、与 ISS-038 上下文串号同源）。
