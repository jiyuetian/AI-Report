# UI & AI 修复交付总结（一页纸）

> 分支：`p0-security-fixes` ｜ 测试看板：`risk_demo_v2_05_合规月度表看板`
> 纪律：一次一项、改动限约定范围、每项落盘、全量回归。

## 提交链
| 序 | 项 | 提交 | 说明 |
|----|----|------|------|
| 基线 | 诊断报告 | `3e0f631` | 冻结，四问题根因 |
| 0 | LLM 多 key 方案 | `294a0cf` | 待确认方案（已确认 B） |
| 0 | **LLM 多 key 容错** | `feb4942` | provider 列表 + 单 key 回退 + 错误分流 |
| 1 | **问题1 限流静默兜底** | `2258ca3` | 消静默弹窗 + 标注落库 + 绿/灰标 |
| 2 | **问题2 多字段截断+匹配** | `f0f5039` | split_clauses 回并 + 规则枚举 + 执行器容错 |
| 3/4 | **问题3 KPI 列宽 + 问题4 附录表格** | `aa716cd` | 自适应 Col + 去 scroll.x |

## 第 0 项 · LLM 多 key 容错（基础设施）
- `config.py`：新增 `LLM_PROVIDERS` 字段 + `get_llm_provider_list()`（未配自动回退单 key，向后兼容）。
- `llm_gateway.py`：网关持 provider 列表 + 惰性 client 池；`chat_complete` 双层循环——外层逐 provider 切换，内层每 key 重试 2 次（退避 1/2/4s）；`429/超时/5xx` 内层重试后切 key，`4xx` 非 429 立即跳，JSON 错重试 1 次后切；脱敏 failover 日志；**全败才 `success=False`**（上层弹窗语义不变）。
- 验证：`tests/test_llm_multikeys.py` 4 passed（MockTransport：切 key 成功 / 全败降级 / 4xx 立跳 / 超时切 key）。

## 问题 1 · 生成看板限流静默兜底（P0）
三层：
1. `brain_run_sse.py` 探针失败 + S3 超时两分支均置 `s3_ai_failed`，弹窗门改为 `if s3_ai_failed`（与对话修改路径一致）→ 不再静默。
2. 同文件 Dashboard.config 落库补 `generation_mode` + `ai_participated`。
3. 前端 `DashboardPage` 扩展 `DashboardConfig` 类型 + 派生 `genMode`；`DashboardOps` 标题渲染绿标「AI 智能生成」/ 灰标「本次为规则生成」。
- 验证：`py_compile` + 前端 `tsc` 通过。E2E（限流→弹窗→灰标）经第 0 项单测间接证明（全 key 失败→`llm_chat` 失败→探针 `llm_offline`→弹窗触发）。

## 问题 2 · 多字段截断 + LLM 路径字段匹配（P0）
三处：
1. `action_planner.split_clauses`：回并无动作动词的裸字段子句（防 5 字段截成 1）。
2. `intent_classifier`：ADD_CHART 新增聚合模式（允许逗号）；`_llm_classify` 后 `_canonicalize_analysis` 用 `_match_field` 规范化字段；`_rule_extract_add_charts` 优先按真实数值字段生成图（LLM 挂时仍可用）。
3. `action_executor._execute_add_chart`：对 `metric_name/title` 回退 `_match_field`，失败给候选。
- 验证：`tests/test_p2_multifield.py` 3 passed（含「删A图并新增B图」复合指令回归，确认未误伤）。

## 问题 3 · KPI 卡片右侧空白（P1）
- `DashboardPage.renderKPILayer`：`<Col>` 按 `kpiCharts.length` 自适应（1→24 / 2→12 / 3→8 / ≥4→6）。
- 验证：`tsc` 通过。⚠️ **视觉截图 = dev 环境手动门禁**（沙箱无浏览器）；附 `visual_repro_p3p4.html` 等价预览。

## 问题 4 · 附录表格右侧留白（P2）
- `AppendixPanel`：A/B/C 三表去 `scroll.x`（A 保留 `y:360` 纵向滚动，B/C 弹性列吸满 100%）。
- 验证：`tsc` 通过。⚠️ **视觉截图 = dev 环境手动门禁**；附 `visual_repro_p3p4.html` 对比预览。

## 全量回归
| 层 | 命令/产物 | 结果 |
|----|-----------|------|
| L1 单测 | `l1_pytest_final.out`（隔离 QA 库） | **53 passed / 1 failed**（1=预存 `test_quality_checker` row_count bug，非本次范围） |
| L5 安全 G3 | `g3_rerun2.out` | **13/13 PASS** |
| L5 安全 G4 | `g4_rerun2.out` | **22/22 PASS**（exit 0） |
| 前端 tsc | `p3p4_frontend_tsc.out` | exit 0 ✅ |
| 复合指令（问题2） | `test_p2_multifield.py` | 3 passed ✅ |
| LLM 多 key | `test_llm_multikeys.py` | 4 passed ✅ |

> 说明：G3/g4_verify 与 L1 pytest 因 `import app.main` 起后台线程，进程在测试完成后于 teardown 挂起（已知现象），结果以输出文件为准，已分别单独运行避免 DuckDB 争锁。

## 交付物
- `UI_FIX_SUMMARY.md`（本文件）
- `LLM_MULTIKEY_PLAN.md`（方案）
- `defect_fix_evidence/ui_fixes/`：各问题 FIX 文档 + 测试 + `.out` 证据 + `visual_repro_p3p4.html`

## 手动门禁（需用户在 dev 环境执行，本沙箱无法自动截图）
1. **问题1**：造 AI 限流（断网/错误 key）→ 生成看板 → 确认弹出选择框；走兜底→打开看板→确认灰标「本次为规则生成」。
2. **问题3**：加载含 KPI 看板 → 单 KPI 占满整行无空白；2/3/≥4 张正常；窄/宽屏各截图。
3. **问题4**：打开附录 Tab → A/C 撑满无右留白、B 保持原样 → 截图对比。
