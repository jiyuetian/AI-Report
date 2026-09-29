# AI_CHANGES.md — 本轮（night7→night8）关键变更台账

> 目的：把分散在多个 commit / night 记录里的关键修复聚合成一份可检索台账，便于回看与 code review。
> 范围：night7 全量修复 + night8 Item0/Item2/Item3/Item4 前序。所有 commit 均在分支 `p0-security-fixes`，本地未 push。

## 一、night7 关键修复（已 commit）

| commit | 类型 | 说明 | 关联 |
|--------|------|------|------|
| c18537d | fix(llm) | failover 识别 HTTP 200 内嵌错误体（余额不足/限流）并切备胎 | — |
| 05b7cd7 | fix(chat) | 诚实兜底 D 方案升级 + 跨会话冒领校验 + 入口探针 | ISS-033（commit msg 误引 ISS-034，见 ISS-037） |
| d12c419 | fix(alert) | 弹窗 P0 三件：探针测真实 provider 链 + 用户选择不静默吞 + 前端旁路封堵 | — |
| 4e6a667 | fix(feasibility) | 修复 _GENERIC_CONCEPT_WORDS NameError 致所有动作意图崩溃 | ISS-032 |
| b340e98 | fix(chat) | Q11 可行性检查放宽——泛指词（风险/趋势/异常…）不当字段要求 | — |
| 4e90ee5 | fix(chat) | 修复 _rule_extract_add_charts 中 is_avg 未初始化导致 else 分支 UnboundLocalError | 与 b340e98 同批改 chat |

## 二、night8 关键变更（已 commit）

| commit | 类型 | 说明 | 关联 |
|--------|------|------|------|
| 45fbcfa | chore(backend) | 启动日志打印 6 层 LLM provider 链（Item 0 佐证可从日志核验 failover） | Item 0 |
| 351f89a | fix(chart) | 修复规则引擎 CHART-01/02/03（散点/热力图 config 占位符 + 兜底饼图基数校验 + 直方图 bins 自适应） | ISS-034/035/036 |

## 三、night8 Item3 过程文件剥离（本回合 3 commit，待 push）

| commit | 类型 | 说明 |
|--------|------|------|
| (archive) | chore(archive) | 后端根 14 + 仓库根 scripts/ 26 测试脚本 → _archive/ |
| (repo) | chore(repo) | 移除废弃验收报告 + darkmode 迁移 docs/design + night 目录整理 + 测试资产入库 |
| (governance) | docs(governance) | _coach_input 治理源迁入 + 本台账 + ISS-037 |

> 注：commit hash 在 push 前以本地生成为准；本表以「类型+说明」锚定，避免 hash 漂移误解。

## 四、night9 关键变更（已 commit）

| commit | 类型 | 说明 | 关联 |
|--------|------|------|------|
| (crossdash) | fix(chat) | 跨看板上下文串号：chat.py 取/建会话后按「当前 dashboard_id + 登录用户」重定位会话归属，杜绝旧看板历史注入当前看板 | ISS-038 |
| (crossdash) | fix(frontend) | DashboardPage.tsx 给 `<ChatPanel>` 加 `key={urlId}`，切看板重挂载重新 loadHistory（双保险） | ISS-038 |
| (confirm) | feat(chat) | C 确认词承接（模块 B5 承诺执行）：action_planner 新增 detect_confirmation + 确认/否定词表，plan_actions 在 pending_clarify 存在时短路（好/可以/确认/就这样→执行 proposal 动作；先不/不好→cancel_pending），不依赖 LLM 分类，规避 429 与误判 | B5-1~B5-4 |
| (confirm) | feat(chat) | clarify 动作可携带 proposal（待确认动作）；chat.py 持久化 proposal 到 pending_clarify，确认执行后清除 pending，否定 cancel_pending 后清除 pending | B5 |

> 第 1 件 glm-5.5-flash 入链：直调 400/1211（模型未开放），按红线不入链，无代码改动、无 commit（详情见 night9/ROUND_NOW.md）。
> 第 3 件 C 确认词承接：落码 + 5 组确定性真测（T1 好/T2 可以/T3 确认/T4 就这样 确认执行；T5 先不 否定不执行）全部 PASS，pending 承接头尾清除（验证脚本 `_verify_confirm.py`，隔离 SQLite 零 LLM 调用，RESULT_JSON all_pass=true）。
> 第 4 件 B 模块 35 条摸底基线：真后端规则模式（LLM 网关 stub 因 429）跑完 35 条 → 12 PASS / 15 FAIL / 8 N/A，产出 `night_runs/night9/TEST1_B_BASELINE.md`，登记 ISS-039~042（仅记录不修）。B 模块基线已出，等用户验收信号。

## 五、night10 关键变更（本地未 push）

| commit | 类型 | 说明 | 关联 |
|--------|------|------|------|
| (iss039) | fix(intent) | CHANGE_CHART 加「轴/字段替换」正则 + target_field/axis 抽取；FILTER_DRILL 年份抽取分支；单图看板 edit_title 自动带 chart_id（改图标题而非看板标题） | ISS-039 |
| (iss039) | fix(executor) | change_chart 仅当 target_type 存在才换图型（字段替换不强制 bar）；filter_drill 补 `year` 键；**补 `import re`** 修复 `_execute_filter_drill` NameError 崩溃（B1-10 根因） | ISS-039 |
| (iss039) | fix(planner) | `detect_vague_chart_type` 在 `target_field` 存在时返回 None（不反问图型）；字段缺失澄清 guard `and not params.get("target_field")` | ISS-039 |
| (iss040) | fix(intent) | CHANGE_CHART 加「否定+纠正」正则（不是X是Y，覆盖饼图/柱图/线图/散点图/环形图/表格）→ change_chart(source_type/target_type) | ISS-040 |
| 9c9e1b7 | fix(gateway) | 修复六层 failover 模型透传 bug：`model = request.model or prov.get("model")` 在 request.model 有值时锁死 kimi-k3，备胎永不命中 → 改为首层用显式 model、failover 层用各 provider 自身 model。直调验证 kimi 429→glm-5.3-flash success | ISS-043 |

> 第 1 件 ISS-039/040 规则缺口修复：只读定位根因 → 13 处增量改动（intent_classifier 6 / action_planner 3 / action_executor 4，含补 `import re`）→ 隔离 SQLite + stub LLM 确定性真测 **5/5 PASS**（B1-5/B1-7/B1-10/B4-1/B4-7）→ 35 条 B 模块回归无新增失败（10 FAIL 均为 night9 既有 add_chart/多轮语义缺口，待 Item2 AI 模式补测）→ ISS-039/040 标 `[DONE]`（commit 3a8ad7b）。
> 第 2 件 AI 模式真跑补测（不 stub）：探活发现 **ISS-043 failover 模型透传 bug**（备胎 key 均有效却永不命中）→ 修复(9c9e1b7)后六层链真正生效（kimi 429→glm-5.3-flash success）。真跑证据：B4-2 规则分类+glm-5.3-flash 高质量澄清（自然语言层可用）；B1-9 诚实兜底无崩溃（弹窗链优雅）；但 glm-5.3-flash json_mode 偶发非法 JSON 致结构化动作不稳（ISS-044，待 kimi 限流解除后重跑完整基线）。产出 `night_runs/night10/AI_MODE_BASELINE.md`。kimi-k3 当前限流(429)中，glm-5.5-flash 模型未开放(404/1211)。

## 六、night11 关键变更（本地未 push）

| commit | 类型 | 说明 | 关联 |
|--------|------|------|------|
| a555b99 | fix(gateway) | ISS-044 JSON 防护：①`_extract_json` 先剥 Markdown 围栏（```json … ```）再解析；②json_mode 解析失败自动重试一次并注入强化 prompt（「只返回合法 JSON、不要围栏」）；③仍失败切下一 provider（原 failover 保留）。恢复记 `[LLM-JSON-FIX]` 日志 | ISS-044 |

> 第 1 件 push：用户已批准，但沙箱杀 git 写操作/GCM（SIGTERM），远端仍在 `8fe2a65`，3 个 night10 commit(3a8ad7b/9c9e1b7/14c5c95) 未上；待用户本机执行 `git push -u origin p0-security-fixes`（详见 `night_runs/night11/ROUND_NOW.md` 第1件）。
> 第 2 件 ISS-044 JSON 防护：确定性集成测试 6 场景 = 5/5 可恢复（含 1 个故意全败降级基线），单元级 `_extract_json` 围栏/平衡括号断言通过；**真模型冒烟 3/3**（kimi 429→zhipu glm-5.3-flash 均 `parsed=True`，`REAL_JSON_SUCCESS_RATE=3/3`）。验证脚本 `_verify_jsonfix.py` / `_verify_jsonfix_real.py`。ISS-044 标 `[DONE]`。
> 用户实测 7 项登记 ISS-045~051（043/044 已占用未撞号）：045 弹窗(根因已修剩UX)、046 KPI坏账率显0、047 直方图X轴0~0、048 比率17位小数、049 散点轴绑金额、050 明细只6列、051 清洗策略平铺。046/047/048 同根因族→第3件统一比率格式化；049→第4件；050/051→第5件；045 回归→第6件。
