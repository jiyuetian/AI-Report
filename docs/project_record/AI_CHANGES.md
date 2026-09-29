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
| (ratiofmt) | fix(frontend) | 统一比率格式化：新增 `metricFormat.ts`（率类字段→百分比 v×100 保留 2-4 位小数去尾零；金额→亿/万紧凑、极小数值保留小数），覆盖 KPI 卡/柱标签/坐标轴/直方图分桶标签/明细表/tooltip；`deriveKpi`+`generateChartOption`(bar/map/scatter/histogram) 全接入。真实 fixture 验算：坏账率 KPI `0`→`0.0249%`、直方图 `0~0`→`0.0038%~0.0482%`、比率裸奔 17 位→`0.0249%` | ISS-046/047/048 |
| (scatterfix) | fix(backend) | ISS-049 散点轴一致性护栏：`S3LLMEnhancer._fix_scatter_axis`（AI 成功路径在 `_apply_derived_metrics` 后调用）。仅当散点标题点名某比率字段时，把该比率的底层金额分量轴反绑回比率字段（分量即分子，语义恒正确）；标题仅含泛化比率词未点名具体比率时同样反绑到所属比率；纯金额/非比率意图散点不改动，避免误绑。补齐规则引擎 night8 已修、AI 路径缺位的 materialize 护栏。确定性单测 6 场景全 PASS（`_verify_scatter.py`） | ISS-049 |
| (detail+clean) | fix(frontend+backend) | ISS-050/051：①明细表（`renderDetailTable` + 图表详情弹窗）去掉 `columns.slice(0,6)` 截断，改为**全列 + 横向滚动**，数据全量分页（每页 20、可切页、显总行数），单元格仍走 Item3 `formatMetricDisplay`；②后端 `appendix_service._clean_log` 透出 `issue_type`（apply 取 `params.issue_type`、detect 取 `iss.type`，均来自已有管线元数据非新计算）；前端 `AppendixPanel` 把 B 附录 78 条平铺记录重组为**按字段叙事卡片**：`字段名 \| 清洗动作 \| 清洗前(空值x/异常y/重复z行) \| 清洗后(已修复/已忽略/待处理行)`，`issue_type` 归类 `affected_rows`。前端 `tsc --noEmit` 全绿 | ISS-050/051 |
| (ai-vs-rule) | test(baseline) | night11 Item6 AI vs 规则 对照基线：A 夹具 D1/D5/D6a 直调 `S3ChartEngine.recommend_charts`（规则，纯本地）与 `S3LLMEnhancer.generate_with_self_healing`（AI，真模型）。结论——AI 胜标题自然+语义配对，规则胜去重/geo→map/histogram+KPI 覆盖；两者均单次干净完成、无连续弹窗。ISS-045 弹窗回归：重传真实 `risk_demo_v2_03`（48×29）AI 生成日志 `_popup_risk03.log` 显示 `sensenova` 429→`[LLM-JSON-FIX]` 强化 prompt 重试自愈→`生成成功`，无错误风暴。ISS-041/042 复合 add/多轮承接底层 json_mode 可靠性已由 Item2 闭环（`AI_VS_RULE.md` §4/§5）。产出 `night_runs/night11/AI_VS_RULE.md` | ISS-045/041/042 |
> 第 1 件 push：用户已批准，但沙箱杀 git 写操作/GCM（SIGTERM），远端仍在 `8fe2a65`，3 个 night10 commit(3a8ad7b/9c9e1b7/14c5c95) 未上；待用户本机执行 `git push -u origin p0-security-fixes`（详见 `night_runs/night11/ROUND_NOW.md` 第1件）。
> 第 2 件 ISS-044 JSON 防护：确定性集成测试 6 场景 = 5/5 可恢复（含 1 个故意全败降级基线），单元级 `_extract_json` 围栏/平衡括号断言通过；**真模型冒烟 3/3**（kimi 429→zhipu glm-5.3-flash 均 `parsed=True`，`REAL_JSON_SUCCESS_RATE=3/3`）。验证脚本 `_verify_jsonfix.py` / `_verify_jsonfix_real.py`。ISS-044 标 `[DONE]`。
> 用户实测 7 项登记 ISS-045~051（043/044 已占用未撞号）：045 弹窗(根因已修剩UX)、046 KPI坏账率显0、047 直方图X轴0~0、048 比率17位小数、049 散点轴绑金额、050 明细只6列、051 清洗策略平铺。046/047/048 同根因族→第3件统一比率格式化；049→第4件；050/051→第5件；045 回归→第6件。
> 第 3 件 ISS-046/047/048 统一比率格式化：新增 `frontend/src/utils/metricFormat.ts` + DashboardPage.tsx 接入（deriveKpi / bar / map / scatter / histogram / 明细表）；真实 fixture 验算 `_verify_ratio.mjs` 全 PASS，逻辑层 before/after 已出，UI 全量重渲染并入第 6 件同文件重传回归。ISS-046/047/048 标 `[DONE]`。
> 第 4 件 ISS-049 散点轴绑金额：只读定位根因——AI 路径 `S3LLMEnhancer` 让 LLM 自由选 x/y，常把「率 vs 率」散点绑到比率的底层金额分量（期末代偿余额≈180亿/坏账核销金额），与「率」标题矛盾；规则引擎 night8 护栏 AI 路径缺位。新增 `_fix_scatter_axis` 补齐：标题点名比率时分量金额反绑回比率，纯金额散点不动。确定性单测 `_verify_scatter.py` 6 场景全 PASS（`ALL_ISS049_CHECKS_PASS=True`）。真实文件 AI 实时生成受沙箱网络 SIGTERM 限制，前后对比以确定性单测（复用该 fixture 真实分量映射）验证。ISS-049 标 `[DONE]`。
> 第 5 件 ISS-050/051 明细全列 + 清洗叙事卡片：①`DashboardPage.tsx` 明细表两处 `slice(0,6)` 截断改为全列 + `scroll.x:'max-content'` 横向滚动，数据全量分页（每页 20、可切页、显总行数），单元格沿用 `formatMetricDisplay`；②后端 `_clean_log` 透出 `issue_type`（已有元数据、非新计算），前端 `AppendixPanel` B 附录由 78 条平铺 Table 重组为按字段叙事卡片（字段名/清洗动作/清洗前 空值x·异常y·重复z 行/清洗后 已修复·已忽略·待处理 行）。前端 `tsc --noEmit` 零报错。ISS-050/051 标 `[DONE]`。

## 七、night12 关键变更（本地未 push）

| commit | 类型 | 说明 | 关联 |
|--------|------|------|------|
| (iss052) | fix(intent+executor+frontend) | ISS-052 add_chart 语义路由 + 维度护栏（P0 核心）：①单值语义（`累计值/最新值`→KPI 单值卡，标题`字段（最新）`，aggregation max/sum）+ `_extract_add_charts` 早返回避免 LLM 臆造 30+ 柱；②`_is_good_dimension`+`MAX_DIM_CATS=20` 维度质量护栏（高基数数值/疑似 ID 不适格→降级 KPI）；③bar/line 维度>20 写 `top_n=20, sort=desc`，前端按 top_n 切片；④单维度柱图单色 `#1677ff`。确定性真测 `_verify_iss052.py` 3 场景全 PASS（EXIT=0） | ISS-052 |
| (iss048b) | fix(frontend) | ISS-048 补漏：普通柱状图/地图 value label 比率裸奔——night11 格式化字段误用 `value_field`（bar 度量在 `y_field`，value_field 恒空）→ `formatMetricDisplay(undefined,…)` 回退 compact 裸奔 0.0002。bar 分支新增 `const metricField = value_field || y_field` 覆盖 tooltip/yAxis/柱 label；map `geoVal` 补 `|| y_field`。附带修正 ISS-052 bar `_topN` 行 `chart.top_n` 类型错（tsc TS2339→0）。前端 `tsc --noEmit` 退出码 0，逻辑验证 0.0002→0.0249% | ISS-048 |
| (iss051b) | fix(frontend) | ISS-051 改向：清洗质检由 night11 叙事卡片改为 `cleanLogTable` 行级明细表（字段\|阶段\|问题类型\|清洗策略\|影响行数\|清洗后状态），置顶 Alert 明示元数据未记录逐行明细。数据模型核查确认 `_clean_log`（`appendix_service.py:116`）仅按 字段×问题类型 聚合存储、无行号/逐行前后值，故不编造逐行数据；4 指标卡雷同经代码核查为字段聚合正确（无 bug），属数据特征。前端 `tsc --noEmit` 退出码 0 | ISS-051 |
| (iss050b) | fix(frontend) | ISS-050 收尾：数据明细预览——`renderDetailTable` 标题改 `数据明细预览`，置顶 header `预览：前 10 行 × 全部 N 列`（展开变 `完整数据：全部 M 行 × 全部 N 列`）；默认 slice 前 10 行，行数>10 显 `查看完整数据` link 切换全量（分页 20/页）；预览态比率字段走 `formatPercent(num,2)`（2 位小数），完整态沿用 `formatMetricDisplay`。前端 `tsc --noEmit` 退出码 0，逻辑验证 `0.000249`→`0.02%` | ISS-050 |

> 第 1 件 ISS-052：只读定位四洞根因 → 后端 `intent_classifier.py`（5 处）+ `action_executor.py`（2 处）+ 前端 `DashboardPage.tsx`（1 处）落码 → 确定性真测 3 场景全 PASS（`ALL_ISS052_CHECKS_PASS=True`）。原句「顶部新增担保余额最新的累计值」修后→KPI 单值卡 `chart_type=kpi, y_field=担保余额, config.aggregation=max, title=担保余额（最新）`；高基数数值维度→降级 KPI；低基数文本维度（月份）仍允许作 bar。真 LLM 端到端截图受沙箱网络 SIGTERM 限制，逻辑层前后对比已由确定性测试覆盖（同 night11 ISS-049 处置），UI 截图待第 5 件重传 risk_demo_v2_03 全链路回归一并给出。ISS-052 标 `[DONE]`。
> 第 2 件 ISS-048：只读定位真根因——night11 只在「数据取值」用 `value_field || y_field`，但「格式化字段」误用 `value_field`（bar 度量写 y_field，value_field 恒空）→ 柱值标签/轴/tooltip 比率裸奔 0.0002。bar 新增 `metricField = value_field || y_field` 覆盖三处格式化 + map `geoVal` 补 `|| y_field`；同次 tsc 冒烟顺带修正 ISS-052 bar `_topN` 行 `chart.top_n` 类型错（TS2339）。逻辑验证 PASS（0.0002→0.0249%），前端 `tsc --noEmit` 退出码 0。ISS-048 标 `[DONE]`（night12 补漏）。
> 第 3 件 ISS-051：用户要求清洗质检由 night11 叙事卡片改为「行级明细表」（行号/字段/问题类型/清洗策略/清洗前/清洗后）。只读核查后端 `appendix_service._clean_log`（`appendix_service.py:116`）——仅按 (dataset_id, target_field, issue_type) 聚合存储 issue_type/strategy/stage/affected_rows/status，无逐行明细（无原始行号、无清洗前/后单元格值）；`data_cleaner.py` 全文 grep row_number|original|before|after|change|diff|old_value|new_value 零命中，确认管线未落 change_log。据此诚实处置：前端 `AppendixPanel` B 附录由 `cleanLogCards`（叙事卡片）改为 `cleanLogTable`（行级明细表，列=字段|阶段|问题类型|清洗策略|影响行数|清洗后状态），置顶 `Alert type="info"` 明示「元数据未记录逐行明细，不编造」，并给单行需求建议（在 `data_cleaner` 落 change_log）。用户质疑「4 指标卡数字雷同」——代码核查 night11 按字段聚合逻辑正确（非 aggregation bug），雷同属该 fixture 数据特征（各字段空值率近似），故不改。前端 `tsc --noEmit` 退出码 0。ISS-051 标 `[DONE]`（改向）。
> 第 4 件 ISS-050：用户要求明细区升级为「数据明细预览」——默认前 10 行 × 全部列快速预览，带 `查看完整数据` 入口，比率字段预览态固定 2 位小数。改造 `renderDetailTable`（`DashboardPage.tsx`）：标题 `数据明细`→`数据明细预览`；置顶 header `预览：前 10 行 × 全部 N 列`（N=列数，展开变 `完整数据：全部 M 行 × 全部 N 列`）；默认 `data.slice(0,10)` 预览，行数>10 显 `查看完整数据` link 切换全量（分页 20/页），再点 `收起为预览（前 10 行）`；预览态比率走 `formatPercent(num,2)`（2 位小数去尾零）、完整态沿用 `formatMetricDisplay`。前端 `tsc --noEmit` 退出码 0，逻辑验证 `0.000249`→`0.02%`（默认 4 位 `0.0249%`）。ISS-050 标 `[DONE]`（night12 收尾）。

## 八、night13 关键变更（本地未 push）

| commit | 类型 | 说明 | 关联 |
|--------|------|------|------|
| (item1) | feat(chat+executor+intent+planner) | **对话动作骨架补全（P0）**：①新增 `UNDO` 意图/动作与撤销句式；②会话级 **AI 动作栈** `ai_action_stack`（持久化到 `ChatSession.context`），每个成功写动作压入 `reverse` 反向描述符，`undo` 弹栈执行、栈空诚实说明；③`delete_last_ai` 指代删除（K-4「去掉你新增的图表」→从动作栈定位最近 AI 新增图）；④ISS-056 布局上下文：`context.layout_summary`（KPI 卡区/图表区结构摘要）+ classifier 抽 `position=top`/`near_title` + executor 按位置/邻近落位（匹配不到落默认）；⑤executor 各写动作返回 `reverse`（add↔delete 原位置重加、change 还原字段、edit_title 还原标题），`delete_chart` 新增按 `chart_id` 定位；⑥K-8 字段不存在禁出图（列候选字段的诚实澄清） | ISS-056/K-4/K-5/K-8 |
| (item1-fix) | fix(executor+intent) | 真跑暴露的 3 个缺陷：①`delete_chart` 的 `chart_id` 命中后被尾部 `else` 澄清分支丢弃（elif 链落空）→ reverse/undo 全失效，改为 `elif target_chart is None and …`；②参数名不一致——规则路径产 `metric`/`target_type`，executor 只认 `metric_field`/`chart_type`，致「顶部新增销售额最新的累计值」误判字段未匹配、且 KPI 单值卡被建成 **bar**（K-1 不符）→ 补 `metric`/`dimension`/`target_type`；③K-4 被 ADD 抢走（「去掉你新增的图表」命中 ADD 的「新增」）→ classifier 新增指代删除优先规则（置信 90，`rule_deictic_delete`） | K-1/K-4 |

> 第 1 件 对话动作骨架补全：只读定位 4 项缺失根因 → 落码 `intent_classifier.py`(UNDO 意图/指代删除优先/near_title+position 抽取) + `action_planner.py`(UNDO 映射/K-8 metric_name 校验) + `action_executor.py`(UNDO 动作/reverse 描述符/chart_id 定位/落位/字段澄清) + `chat.py`(动作栈载入·入栈·持久化/undo 分支/delete_last_ai 解析/layout_summary) → 克隆看板 `dash_p0verify_0001` 真跑 `_verify_item1.py` **PASS=17 / FAIL=0**（A 空栈撤销诚实 / B 顶部落位 / C 邻近落位 / D 精确删最近 AI 新增图且保留更早新增 / E 撤销回基线 / F 字段不存在不出图）。真跑中修掉 3 个真实缺陷（见上表）。测试数据说明：模块 K 指定的 risk_demo_v2_03 物理表已归档到 `data/_archive/duckdb/`（活跃库仅剩 QA 样例表），本轮用同结构 QA 克隆看板真跑；K 模块 12 条全量基线需先恢复该 fixture。产出 `night_runs/night13/ROUND_NOW.md`。
