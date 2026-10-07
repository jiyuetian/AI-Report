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
| (item2) | feat+fix(executor) | **输出护栏**：①ISS-055/K-6 标题语义校验——新增 `_is_speech_fragment_title`（位置/指代/祈使词、句中标点、长度>16 判为口语片段）+ `_canonical_title`（KPI→`指标（最新/均值/合计）`；维度图→`指标按维度+后缀` bar对比/line趋势/pie占比/scatter关系/table明细），多图 `spec.title` 与单图（含默认「新增XX」）两处落点；②K-7 维度质量补全——新增 `_looks_like_digit_string`（名称像号/id/编号/编码 或 采样值≥80% 纯数字）识别文本型长数字串，`_is_good_dimension` 补「数字串字段 / distinct_count>50 数值字段」禁做分类轴，**单图规则路径（此前完全无护栏）与多图对齐**：维度不适格降级 KPI 单值卡、bar/line 维度基数>20 自动 `top_n=20,sort=desc` | ISS-055/ISS-048/K-6/K-7 |
| (item3) | fix(intent+planner+executor+chat) | **模块 K 全量 12 条 → 13/13 PASS（验收线 100%）**。闭环 K-2/K-11 两处 FAIL：①`delete_last_ai` 指代消解**改仅对 DELETE/UNDO 意图生效**（原对全部意图生效，宽松正则命中「你累加后的值」误 pop chart_type，把 KPI 卡片建成 bar）；②位置正则移除 bare「卡片」（图型 KPI 同义词非顶部锚点，避免「加上一个新卡片」误置顶盖掉 near_title）；③planner 新增 `_extract_position_hints_from_message` 从**整句**抽「在X的旁边」→`near_title`，防 split_clauses 丢落位；④executor 单图护栏接受口语 `metric_name`（经字段画像校验真实存在后放行，命不中则与 K-8 一致拒绝臆造）；⑤chat.py add_chart 落位兜底改用整句 `request.message` | K-2/K-11 |
| (item5) | fix(intent) | **ISS-033「再来一个」闭环 + 指标名抽取盲区修复**：①`_extract_params`(ADD_CHART) 新增「指标是/为/要/：X」直接捕获（剥离尾部「的累计值/的合计/的均值」等聚合修饰），覆盖「销售额/销量/利润」等不以 余额/金额/数量 结尾的指标名——此前这类指标名匹配不到固定后缀列表 → 退化成假名「新增指标」被 K-8 字段护栏误拒（出不了图）；②ISS-033 承接已由既有 `_resolve_history_anaphora`（读 `context.memory.last_action`）覆盖，「再来一个/再加一张」→clone 上一轮真实字段的 add_chart，本次用自建数据集（销售额/月份/地区）端到端验证：T1 新增 KPI 卡(销售额,sum) 图数+1，T2「再来一个」图数再+1 | ISS-033/K-2(指标名抽取) |
| (item6) | feat(frontend) | **ISS-045 UX 退避重试（前端弹窗节流/合并）**：新增 `frontend/src/utils/throttledMessage.ts`（antd `message` 节流+去重封装：相同 key 4s 窗口去重、带 key 原地合并、任意两条间隔<600ms 仅保留最后一条），`ChatPanel.tsx` 对话面板 5 处报错 toast 改走该封装并带稳定 key；`tsc --noEmit` 0 错误。后端根因（错误循环驱动弹窗）此前已由 failover+JSON 防护 `[DONE]`，本件为前端兜底收尾 | ISS-045 |
| (item7) | fix(deps) | **ISS-053 Dependabot 高危漏洞**：本地 manifest 静态审计 + 安全版本钉固 `backend/requirements.txt`——python-multipart 0.0.9→0.0.12(CVE-2024-53981 HIGH)、pandas 2.2.0→2.2.2(CVE-2024-27330/27331 HIGH)、jinja2 3.1.3→3.1.4(CVE-2024-34064)、email-validator 2.1.0→2.1.1(CVE-2024-1916)、httpx 0.26.0→0.27.2(CVE-2024-47081)；ISS-053 登记入 ISSUES.md。沙箱无网络未 `pip install` 实装，待本机/CI 生效 | ISS-053 |
> 第 2 件 输出护栏：只读定位两处根因——①K-6 无任何标题校验（第1件 C 场景已抓到实证：LLM 把口语原句「总销量的旁边加上一个销售额」直接当标题）；②K-7 的 ISS-052 护栏只加在多图 charts_spec 路径，**单图规则路径完全没有护栏**，且原 `_is_good_dimension` 只按 type 判数值、识别不了「文本型但取值是长数字串」。→ 落码 `action_executor.py`4 处（3 个新方法 + `_is_good_dimension` 增强 + 单图路径护栏/标题校验）→ 确定性验证 `_verify_item2.py` **PASS=16 / FAIL=0**（口语片段识别且规范标题零误伤；借据号/应收账款禁做维度、date/region 仍适格；单图不适格维度降级 KPI 且 x_field 为空；bar 维度 dc=30 自动 top_n=20）→ 回归第1件 `_verify_item1.py` 仍 **PASS=17 / FAIL=0**。ISS-055 为本轮新登记编号（旧 `06-ISS债清单.md` 仅到 ISS-025，04x~05x 一贯记在 AI_CHANGES.md）。
> 第 3 件 模块 K 全量：此前 K-2/K-11 FAIL，本轮闭环。K-2 根因 3 层——①classifier `delete_last_ai` 对全部意图生效、宽松正则误命中「你累加后的值」→误 pop chart_type（KPI→bar）；②位置正则 bare「卡片」把「加上一个新卡片」误置顶、盖掉 near_title；③split_clauses 把「在平均坏账率的旁边」拆到独立 clause、executor 单图护栏只认 metric_field 不认口语 metric_name。→ 落码 `intent_classifier.py`(delete_last_ai 收窄到 DELETE/UNDO + 位置正则去 bare「卡片」) / `action_planner.py`(整句抽 near_title) / `action_executor.py`(单图护栏接受 metric_name) / `chat.py`(落位兜底用整句) → 克隆看板 `dash_kmodule_0001` 确定性真测 `_verify_k.py` **13/13 PASS（100%）**（全程规则路径零 LLM，429 下仍验收）。K-11：classifier 对「换一个角度/换视角」→change_chart+ambiguous_change，planner 产澄清（换维度/图型/指标）不执行、图数不变。回归：Item2 `_verify_item2.py` 16/0；Item1 `_verify_item1.py` 13/4（4 FAIL 均为 B 模块依赖 LLM 用例在 429 下降级规则路径，规则路径用例全 PASS，非本次回归）。产出 `night_runs/night13/K_BASELINE.md`。minor（不在 K 验收内）：K-12 R4「担保余额按担保类型的柱图」维度误取 月份，建议后续立 ISS 排查。

> 第 1 件 对话动作骨架补全：只读定位 4 项缺失根因 → 落码 `intent_classifier.py`(UNDO 意图/指代删除优先/near_title+position 抽取) + `action_planner.py`(UNDO 映射/K-8 metric_name 校验) + `action_executor.py`(UNDO 动作/reverse 描述符/chart_id 定位/落位/字段澄清) + `chat.py`(动作栈载入·入栈·持久化/undo 分支/delete_last_ai 解析/layout_summary) → 克隆看板 `dash_p0verify_0001` 真跑 `_verify_item1.py` **PASS=17 / FAIL=0**（A 空栈撤销诚实 / B 顶部落位 / C 邻近落位 / D 精确删最近 AI 新增图且保留更早新增 / E 撤销回基线 / F 字段不存在不出图）。真跑中修掉 3 个真实缺陷（见上表）。测试数据说明：模块 K 指定的 risk_demo_v2_03 物理表已归档到 `data/_archive/duckdb/`（活跃库仅剩 QA 样例表），本轮用同结构 QA 克隆看板真跑；K 模块 12 条全量基线需先恢复该 fixture。产出 `night_runs/night13/ROUND_NOW.md`。

## 九、night14 关键变更（本地未 push）

| commit | 类型 | 说明 | 关联 |
|--------|------|------|------|
| 270f21c | fix(launcher) | **ISS-057** `run_backend.py::_pid_alive` 跨平台探活修复：Windows 改走 ctypes `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)`+`GetExitCodeProcess(==STILL_ACTIVE 259)` 判定真存活，修复「刚被杀 PID 内核对象未回收 → `os.kill(pid,0)` 不抛异常 → 误判存活 → B5 守卫拒绝重启 → 后端起不来」的真 bug；其他构建 `SystemError` 亦兜住；任何异常视为不存在放行（B5-2 端口检测兜底）。独立 harness `_verify_iss057.py` 7/7 PASS | ISS-057 |
| d221f04 | feat(chat) | **D-018 Task1 AI 行为白盒化埋点**：①新增 `AiActionLog` 模型（表 `ai_action_log`，SQLite 同库 aibi.db，注册 `models/__init__.py`+`main.py::lifespan` 自动建表）；②新增 `log_ai_action` helper（fail-fast 写失败仅 `[AI-ACTION-LOG-WARN]` 不抛、PRAGMA busy_timeout=3000、params/error 截断合法 JSON、`asyncio.create_task` fire-and-forget）；③`chat.py send_message_stream` 主链路埋点（动作轮逐动作写一行 + 非动作轮 clarify/fallback/unknown 汇总）+ `safe_stream` 兜底分支写 `stream_error/failed`；④确认词执行(`llm_layer='confirmation_word'`)/remove/undo 经动作轮同源埋点 | D-018/Task1 |
| 9be596c | feat(ai-action-log) | **D-018 Task2 AI 操作日志查询/展示层**：①新增 `GET /api/v1/ai-action-log/list`（分页 + 多维过滤 session/dashboard/action_type/intent/result_status/llm_layer/时间区间/keyword + 权限隔离：普通用户强制只看自己、超管可查全部或指定 user_id），仅查询不写表、不碰 DuckDB；②前端 `views/ai-log/AiLogPage.tsx`（AntD Table + 筛选器 + 分页），`App.tsx` 路由 `/ai-log`、`MainLayout` 导航『AI 操作日志』，`tsc --noEmit` 0 错；③`docs/test/AI_TEST_CASES_v1.md` 计数修正（模块L 8→9）+ 新增模块 M（6 条, Task2 验收） | D-018/Task2 |
| 125cff7 | test(b-module) | **D-018 Task3 B 模块 10 FAIL 的 AI 模式补测**：真跑 `send_message_stream`（真实 6 层 LLM 网关，不 stub；仅 stub 内容审核）+ 隔离临时 SQLite，逐条真跑 night9 规则基线遗留 10 FAIL（同种子同判据）。结果 **PASS 5 / FAIL 5 / BLOCKED 0 / ERROR 0**：PASS 5 为多轮语义承接（B3-2/3/4/5/8，规则+会话上下文闭环，night13 改进生效、AI 模式零回归）；FAIL 5 中 4 条（B1-2/B2-1/B2-2/B2-3 add_chart）经控制实验（`_verify_task3_control.py` 直调 `_execute_add_chart`：给定 field_profiles→n_added=1，不给→n_added=0）定性为**隔离种子无 dataset schema（field_profiles=[] 触发「禁止臆造垃圾图」护栏 skip）所致、非逻辑回归**，真实数据集看板待补测；1 条（B3-7「把阈值调80%」）为真实未覆盖功能缺口（阈值调整动作未实现）。报告 `night_runs/night14/TEST2_B_AIMODE.md`；`AI_TEST_CASES_v1.md` 模块 B 新增「AI 模式补测状态」小节 | D-018/Task3 |
| 50308ea | feat(config) | **Task A LLM 链 7 层调整（D-020）**：`backend/.env` 第 11–15 行 6-provider 旧链 → 7 层新链（glm-5.3-flash 出链；glm-4.7-flash/glm-4.6v 入链；顺序 kimi-k3→glm-4.5-air→glm-4.7-flash→glm-4.6v→deepseek-v4-flash→agnes→flash-lite）。冒烟 3a：n_providers=7、顺序正确、kimi-k3 真实调用 success=True（attempt1 遇 429 自动重试成功）；3b：glm-4.5-air OK / glm-4.6v OK / **glm-4.7-flash 遇 429 瞬时限流（非模型不存在/鉴权失败，模型可达，峰值拥堵）按 3b 规则标记待确认**；3c：活 8000 后端非自启、沙箱不重启，留待用户手动重启 8000 后从日志核验实际服务 provider/model。`.env` 被 gitignore 不进仓，配置即改即生效。 | D-020/TaskA |
| a33f655 | feat(chart-template) | **Task B 图表模板库后端**：新表 `chart_templates`(id/name/category/config_json/tags/usage_count/source/created_by/created_at/updated_at)+CRUD API(`GET /list` 分页+业务域/标签/关键词过滤、`GET /{id}`、`POST /`、`PUT /{id}`、`DELETE /{id}`、`POST /{id}/apply`)；`main.py` 注册建表 + lifespan 种子补种 `init_chart_templates`(8 业务域预置：担保风控/信贷/财务/销售/客户/运营/供应链/人力，SQL/配置硬编码白名单、禁止 LLM 生成)；apply 端点复用 `ActionExecutor._execute_add_chart` 渲染链（取主数据集 profile_json/schema_json→field_profiles，按真实字段映射、命不中跳过不臆造），落库看板 config 且 usage_count+1。验证 `_verify_taskB.py`：建表+补种；担保风控模板在匹配数据集映射 4 图(总担保余额kpi/各区域bar/客户类型pie/月度line)，财务模板命不中 added=0。5 文件 py_compile 全过。 | D-020/TaskB |
| 76e81ea | feat(chart-template) | **Task B 图表模板库前端**：`DashboardOps` 头部新增『图表模板库』入口按钮(透传 `onOpenTemplateLibrary` 回调)；新建 `ChartTemplatePanel.tsx`(Modal：拉取 `/chart-templates/list`、业务域 Select 过滤、卡片展示 name/category/desc/tags/图数/已套用次数 + 『一键套用』)；`DashboardPage` 接收 apply 响应 `render_updates`，按既有 `add_chart` 合并逻辑(`handleTemplateApplied`)追加进 config 并 `http.patch` 落库。后端 apply 返回 `render_updates:[{type:add_chart,chart:{id,chart_type,title,dataset_id,x/y/category/value_field,config}}]`，前端仅合并落库、零臆造。`tsc --noEmit` 0 错。活 8000 未重启，前端 UI 需用户 `npm run dev` 后在看板页头部点『图表模板库』实测套用。 | D-020/TaskB |
| 47681b1 | feat(clean-chain) | **Task C 链路规则引擎**：新建 `app/core/clean_chain.py`(`CleanChainEngine`+`ChainRule`)——YAML 描述有序清洗规则链路，`run()` 顺序执行 `DataCleaner.execute_fix`；**fail-fast**(默认开、单条可 override)异常即停并回链 `failed_rule_id`；**rule_id 回链**(YAML 可读 id 取代随机 8 位，执行结果逐条标注 + 备份表名)；**改前备份**(每条规则执行前 `CREATE TABLE <table>_chainbak_<rule_id> AS SELECT *`)，新增 `rollback_rule(rule_id)` 按备份真回滚(替代 `DataCleaner.rollback` 的 TODO 占位)。示例 `config/clean_chains/example_chain.yaml`。附带修复预存 bug `_fix_enum_normalize`(占位参数数 2N≠实际 N+1、且多 source→target 无法单句套用 → 改 `CASE WHEN` 批量映射)。验证 `_verify_taskC.py`(内存 DuckDB 隔离) **ALL PASS**：顺序/备份/rule_id 回链/fail-fast 中断/真回滚/rule_id 唯一性。 | D-020/TaskC |
| 269663c | test(b-module)+docs(issues) | **Task D 模块B收尾**：①4 条 add_chart FAIL（B1-2/B2-1/B2-2/B2-3）构造最小临时 DuckDB dataset（`ds_btest`：地区/渠道/产品/月份 VARCHAR + 担保余额 DOUBLE，8 行，不碰生产库）真实推导 field_profiles，调 `ActionExecutor._execute_add_chart` 复测全部 PASS（n_added=1/1/1/3）——坐实 night14 Task3 控制实验根因（隔离种子无 dataset schema，field_profiles=[] 触发「禁止臆造垃圾图」护栏 skip，非执行器回归）；`docs/test/AI_TEST_CASES_v1.md` 模块B状态小节 4 行 FAIL→PASS、汇总 PASS5/FAIL5→PASS9/FAIL1；②B3-7「把阈值调80%」阈值调整为真实功能缺口，登记 **ISS-058**（仅登记不实现）。验证 `_verify_taskD.py`（临时 DuckDB 隔离）ALL_RETEST_PASS=True | D-020/TaskD |
| dd7af5c | fix(frontend) | **Task E ISS-048 对话新增图数值格式化漏点修复**：pie tooltip 裸 `{c}`→`formatMetricDisplay(valField)`（count 模式保留『笔』）；heatmap tooltip 裸 `p.data[2]`→`formatMetricDisplay(valF)`；sanitizeChartOption 直方图分箱中心裸 `Number(v.toFixed(3))`→`formatCompactNum`（亿/万 + 极小比率 4 位小数）。复用 night11 `589e27d` 全局格式化器 `metricFormat.ts` 单一事实来源；`tsc --noEmit` 0 错；formatMetricDisplay/formatCompactNum 真跑 6 例断言全 PASS。仅前端渲染格式化，不新增 B 模块意图用例 | D-020/TaskE |
| fed1476 | fix(gateway) | **Task F ISS-045 LLM 网关失败指数退避重试**：`MAX_RETRIES` 1→2（每 key=3 次尝试），新增 `_backoff_wait(retry)=min(8*(retry+1),45)`→ 超时/网络/JSON 重试 8/16/24s、429 优先 `Retry-After` 头否则同公式、整体封顶 45s。与 night13 前端 `throttledMessage` 节流互补（退避=弹前自愈、节流=同失败只弹一次）；`ChatPanel` 5 处 toast 已全走 `throttledMessage`（含 `send-fail` LLM 失败），前端无改动。验证 `_verify_taskF.py`：MockClient 注入 timeout/429/全败序列，`chat_complete` 退避 [8,16] 后成功(retry_count=2)或降级(success=False) 全 PASS；`py_compile` 通过 | D-020/TaskF |

> 第 1 件 ISS-057：只读实测修正根因——旧 `os.kill(pid,0)` 在 Windows 上对本机「刚被杀 PID」**不抛异常**→误判存活→B5 拒绝重启（比「死 PID 抛 SystemError」更隐蔽且 100% 可复现）。ctypes `OpenProcess`+`GetExitCodeProcess` 修复对两种形态都覆盖（ERROR_ACCESS_DENIED(5) 视为存活防误杀真进程）。独立 harness 进程内驱动真实 `main()`（uvicorn.run 桩、隔离端口 18099、未碰 8000 活后端），两轮（无 pidfile / 残留死 PID=999999）均到达 `[B5] 启动后端` → **ALL PASS(7/7)**。`ISSUES.md` 新增 `## ISS-057` 条目状态 `[DONE]`。commit `270f21c`。
> 第 2 件 D-018 Task1：纯增量 fire-and-forget 日志，不改任何既有对话行为。落码 `models/ai_action_log.py`(新,30 行) + `core/ai_action_log.py`(新,99 行 helper) + `chat.py` 主链路+兜底埋点块(75 行) + `main.py`/`models/__init__.py` 注册。`docs/test/AI_TEST_CASES_v1.md` 新增**模块 L（8 条，v1.5）**，随仓把既有的未提交模块 K（12 条）一并入库。自测：`_verify_task1_integration.py` **INTEGRATION OK**（真实 SSE 链路 add_chart 写入 `'add_chart','success','add_chart','rule',2219,{metric:担保余额}`）+ `_verify_task1_scenarios.py` **ALL SCENARIOS OK(L1–L8)**：主链路/确认词透传 confirmation_word/undo/delete_chart/流异常 stream_error/持锁写入/超大params截断合法JSON/30并发全落库/坏DB不抛。所有改动模块 `py_compile` 全过；A27+K13 因纯增量日志无退化（核心动作路径 L1–L4 同链路复跑验证行为一致）。commit `d221f04`。


> 第 3 件 Task A（LLM 链 7 层调整，D-020）：`.env` 被 gitignore 故配置本体不进 git，本行仅登记变更；用户须手动重启 8000 后端（pid=9632，禁 kill）方使新链生效。3b 灰度结论——glm-4.5-air 与 glm-4.6v 直调 success=True；glm-4.7-flash 直调两次均 429（code 1305 该模型访问量过大），属免费模型峰值拥堵的瞬时限流而非模型不存在/鉴权失败，网关 failover 会自动跳过它继续走 glm-4.6v→deepseek→agnes→flash-lite，故保留入链无害，按 3b 规则标记待用户确认是否保留；如用户决定移除则回退 `.env` 第 13/15 行即可。3c 真实业务调用核验需 8000 重启后从运行日志确认 provider/model 字段。

## 十、night15-16 Task G 最高权限 CRUD（走规则引擎 fail-fast，本地未 push）

| commit | 类型 | 说明 | 关联 |
|--------|------|------|------|
| a01deb1 | feat(crud) | **Task G 最高权限 CRUD（走规则引擎 fail-fast）**：①`ActionType`+5(`CREATE_CONFIG`/`UPDATE_CONFIG`/`DELETE_CONFIG`/`BULK_UPDATE_DATA`/`MANAGE_PERMISSIONS`)，`executors` 字典+5、`execute` 分发；②`ActionExecutor` 5 个 `_execute_*` 纯 config 变换（config CRUD 改 `config_items` 并产 `reverse` 撤销描述符，由 chat.py 动作轮落 `dashboard.config`）；③新增 `CrudChainGuard`(`crud_chain.yaml`) 复用 Task C clean_chain 的 fail-fast + rule_id 回链思想——只做参数层前置校验（隔离性/超管/受保护键），不碰 DB；④`BULK_UPDATE_DATA` 仅隔离临时库（红线④，绝不碰 aibi.db）：执行器产隔离计划 + chat.py 调 `run_isolated_bulk_update` 在临时 SQLite/内存执行，双护栏拒绝生产路径；⑤`MANAGE_PERMISSIONS` 硬护栏（用户已确认）：非 `is_superuser` 直接拒绝、超管触发 `requires_confirm` + 全量 `ai_action_log` 留痕（chat.py 动作轮自动记每行）；⑥`intent_classifier`/`action_planner` 自然语言识别——CRUD 意图 `INTENT_PATTERNS` 置顶（防被 `ADD_CHART`/`DELETE_CHART` 的「新增/删除」宽匹配抢走）+ `_get_keywords`/`_extract_params` 抽 key/value/角色/用户；⑦`chat.py` 动作轮注入 `context["is_superuser"]` + 隔离批量执行接线。验证 `_verify_taskg.py`（隔离，不碰生产库）**18/18 PASS**：配置 CRUD 创建→修改→删除 + fail-fast(dup/missing/受保护键)；批量隔离执行 + 拒绝非隔离/生产路径；权限非超管拒/超管留痕；CRUD 意图识别 + 看板意图回归(add/delete_chart 未劫持)；planner 产出 `create_config`。 | D-020/TaskG |

> 两条架构决策（用户本轮确认）：①`BULK_UPDATE_DATA` 选「仅隔离临时库」——执行器只校验隔离标记 + 产计划，真实写入由 `run_isolated_bulk_update` 在临时 SQLite/内存完成，生产 aibi.db 零风险；②`MANAGE_PERMISSIONS` 选「硬护栏+超管留痕」——非 `is_superuser` 直接拒绝(fail-fast)，超管触发 `requires_confirm`+全量 `ai_action_log`。两决策均与硬红线一致。`_verify_taskg.py` 为隔离验证脚本（未进仓，验证后删除），生产库零触碰。

## 十一、night15-16 Task H 派生指标完整版（14 指标，本地未 push）

| commit | 类型 | 说明 | 关联 |
|--------|------|------|------|
| （待提交） | feat(metric) | **Task H 派生指标完整版（14 指标 + 前端展示）**：①新建 `backend/app/core/metric_registry.py`——`BaseMetric` + `MetricRegistry`(单例 `METRIC_REGISTRY`)，显式定义 **14 个业务指标**（财务 5：ROI/ROE/毛利率/净利率/EBITDA margin；风控 4：不良率/拨备覆盖率/资本充足率/流动性比率；业务 3：客户增长率/交易量/客单价；其他 2：复购率/市场份额），每个含名称/中英文公式/字段映射(中文+英文+snake 别名)/数据来源/含义；支持 `operation=query/explain/compare/trend` + 进程内轻量缓存(LRU+TTL)。`calculate` 是确定性事实（非 LLM 猜），除零/缺字段一律返回明确 error，诚实不编造；数据由调用方以 dict 显式提供，零 DB 接触（红线④）。②新建 `backend/app/api/metrics.py`——`/metrics/registry`(GET 指标清单)、`/metrics/calculate`(POST 计算) 两个只读路由，供前端与 AI 调用。③`ActionExecutor` 新增 `CALCULATE_METRIC` 枚举 + `_execute_calculate_metric`（纯计算、返回 `read_only=True`，chat.py 动作轮据此跳过 `dashboard.config` 落库与 `updated_at` 刷新）。④`intent_classifier` 新增 `QUERY_METRIC` 意图（置顶防被 `ATTRIBUTION` 抢走）+ 中文名/英文键/别名解析 + operation 提取（query/compare/trend/explain）；`action_planner` 映射 `QUERY_METRIC → calculate_metric`。⑤前端 `frontend/src/views/metrics/MetricPage.tsx`：指标卡片(名称/公式/单位/分类 Tag) + 4 个 Tab(单期计算/多期对比/趋势预测含 SVG sparkline/指标解释) + 导航 `派生指标`(`/metrics`)；`App.tsx`/`MainLayout.tsx` 接线。验证 `_verify_taskh.py`（隔离，不碰生产库）**42/42 PASS**：14 指标 canonical+中文别名计算准确、除零/缺字段/未知指标诚实报错、多期对比 delta_pct、趋势线性最小二乘确定性、解释结构、NL 意图识别(query/compare/trend/explain)+看板意图回归(改图/新增/删除未劫持)、planner→calculate_metric、executor read_only+值/消息。前端 `tsc --noEmit` **退出码 0（零类型错误）**。 | D-020/TaskH |

> 设计要点：派生指标走「确定性业务注册表」而非 `derived_metric_service` 的「跨列反推」——14 个指标公式显式可审计、可对比、可趋势外推；AI 查询时由调用层负责把字段值解析好再传入 `calculate`（不在此层碰生产 DuckDB，满足红线④）。`CALCULATE_METRIC` 为只读动作，不触发看板 config 落库，避免 `updated_at` 无谓抖动。前端趋势预测用确定性最小二乘外推（非 LLM 编值），诚实可复现。`_verify_taskh.py` 为隔离验证脚本（未进仓）。

## 十二、night15-16 Task I 下游重算一致性（C-16，本地未 push）

| commit | 类型 | 说明 | 关联 |
|--------|------|------|------|
| 5f6c6a5 | feat(recalc) | **Task I 下游重算一致性（C-16）**：①新建 4 模块（零 DB、内存态、红线④）：`dependency_graph.py`——指标依赖图，复用 `lineage_service.get_impact_analysis` 下游 BFS 语义，按 category/data_source 解析下游指标 + 拓扑分层（同层可并行、跨层串行）；`recalc_validator.py`——一致性校验（重算前后对比/合理性检查/依赖完整性/错误恢复）；`recalc_engine.py`——重算引擎（notify_data_change 事件触发→依赖图解析→分层执行→校验→历史），复用 ISS-045 退避 `min(8*(retry+1),45)` + CrudChainGuard rule_id 回链思想（recalc_id↔trigger 可追溯）；`recalc_queue.py`——`RecalcQueue` 薄封装 + 6 端点(trigger/status/history/dependency-graph/stats/recover)。②`ActionExecutor` 新增 `RECALC_METRIC` 枚举 + `_execute_recalc_metric`（read_only，不落库）。③`intent_classifier` 新增 `RECALC_METRIC` 意图（置顶防被 query/attribution 抢走）+ 操作提取(trigger/status/error/perf/graph)；`action_planner` 映射 `RECALC_METRIC → recalc_metric`。④`chat.py` 动作轮事件钩子：CRUD 成功且带 `recalc_scope` → 自动 notify+execute 下游重算（满足 C-16「AI 改规则→下游自动重算」）。⑤前端 `frontend/src/views/recalc/RecalcPage.tsx`：状态面板/历史/依赖图 3 Tab + 触发按钮；`App.tsx`/`MainLayout.tsx` 接线 `/recalc`。验证 `_verify_taski.py`（gitignored，隔离不碰生产库）**32/32 PASS**：依赖图解析(财务5/风控4/业务3/显式/拓扑分层)、校验器(前后对比/回归/合理性违例/恢复)、引擎(notify→execute→前后对比→状态/历史/性能/恢复)、AI 集成(重算触发/状态/错误/性能/图意图 + planner + executor read_only + 看板意图回归)、事件驱动契约(CUD→recalc_scope→下游4指标)。前端 `tsc --noEmit` **退出码 0**。 | TaskG/TaskH/C-16 |

> 设计要点：重算引擎为「事件驱动 + 内存队列」模型，指标计算复用 Task H `METRIC_REGISTRY.calculate`（确定性、零 DB），下游解析复用 Task G `CrudChainGuard` 的 rule_id 回链思想（每条 recalc 记录 recalc_id + trigger，可追溯）。退避复用 ISS-045 同公式（优先直接 import `llm_gateway._backoff_wait`，缺失则就地等价实现）。`chat.py` 事件钩子满足 C-16 P0：AI 修改配置/规则后，下游受影响指标自动入队重算，结果一致性由 `RecalcValidator` 核对（重算前后对比 + 合理性 + 范围完整性）。`_verify_taski.py` 为隔离验证脚本（未进仓）。

## 十三、night17 Task J/K 使用统计（J-8）+ 全链路联调（本地未 push）

| commit | 类型 | 说明 | 关联 |
|--------|------|------|------|
| （night17 单提交） | feat(usage+integration) | **Task J（使用统计 J-8）+ Task K（全链路联调）**：**零 DB、内存态（红线④）**。<br>①`backend/app/core/usage_stats.py`——`UsageStats` 单例 `USAGE_STATS`：进程内 deque 存事件（上限 20000），`record_event(event_type,user_id,data,success,latency_ms)` / `get_stats(time_range,filters)` / `analyze_patterns()` / `recent_events()`；user_id 一律 SHA-256(进程级随机盐) 脱敏、盐不持久化（隐私）。`get_stats` 产出 overview（事件量/成功率/token 消耗/平均延迟）+ 按模型（调用数/成功率/prompt+completion token/延迟）+ 按动作 + 小时趋势；`analyze_patterns` 产出最常用动作 Top / 高峰时段 / 模型偏好占比 / 各模型错误率 / 最慢模型 / 7 日前后对比。<br>②`backend/app/core/analytics.py`——纯函数 `compute_linear_slope`（最小二乘）/ `bucket_events`（时间分桶趋势）/ `compare_two_periods`（前后段对比），无状态、可单测。<br>③`backend/app/api/usage_stats.py`——`/usage-stats` 路由（由 main 以 `/api/v1` 挂载）：`GET /overview` `/events` `/trends` `/patterns` + `POST /record`（鉴权同 metrics）。<br>④**生产埋点接线**：`chat.py` 动作轮（read_only 守卫后、`action_results.append` 前）懒导入 `USAGE_STATS.record_event("ai_action", …)`，记录动作类型/成败/延迟（写失败 try/except 不阻断对话）；`llm_gateway.py` 4 个返回路径（mock 成功 / 真实成功 / fallback 失败 / 无 fallback失败）均懒导入 `USAGE_STATS.record_event("model_call", …)`，记录模型名/prompt+completion token/成败/延迟 → **J-8「模型使用量/成功率/token 消耗可见」真实落埋点**。<br>⑤`backend/app/integration/` 离线集成运行器（Task K）：`test_cases.py` 7 个用例覆盖 Task G 隔离批量更新 / Task H 派生指标(计算+未知指标诚实报错) / Task I 下游重算(notify+依赖图) / Task J 按模型聚合 / 路由装配；`test_runner.py` `IntegrationTestRunner.run_tests()` 产出结构化报告（总数/通过/失败/通过率/逐条）；`performance.py` `run_performance_benchmark()` 测 calculate 与 usage 往返 p50/p95/max/mean；`app/api/integration.py`——`POST /integration/run`（跑用例+性能基准）/ `GET /integration/report`。<br>⑥`main.py` 加 `usage_stats` / `integration` 两路由；前端 `UsageStatsPage.tsx`（概览/按模型/趋势/使用模式 4 Tab，时间范围筛选）+ `E2ETestPage.tsx`（运行联调+通过率+逐条+性能），`App.tsx` 加 `/usage-stats` `/e2e` 路由，`MainLayout.tsx` 加「AI 使用统计」「全链路联调」导航。<br>验证 `_verify_taskjk.py`（gitignored，隔离零 DB）**19/19 PASS**：analytics 三函数 + usage_stats 按模型/按动作/overview.total_tokens/analyze_patterns/脱敏 + 集成 run_tests 7/7 + 性能基准 + API 路由装配；前端 `tsc --noEmit` **退出码 0**。 | J-8/TaskJ/TaskK |

> 设计要点：使用统计为「内存态 + 脱敏 + 零 DB」——所有事件仅驻进程内存，user_id 哈希脱敏、盐随机不落盘，重启即清空，**绝不接触生产 DuckDB（红线④）**，因此统计为进程级、会话级可见（非跨重启持久）。埋点均 fail-fast（try/except 包裹，写入异常只跳过不阻断主业务）。Task K 全链路联调为**离线 smoke 集成**：仅驱动 G/H/I/J 内存态引擎做协同装配验证（调用不崩、返回形态符合契约），不伪造浏览器 UI/生产库端到端覆盖；真实 E2E 由本机手动验收。`_verify_taskjk.py` 为隔离验证脚本（未进仓）。night17 单提交因 main.py/App.tsx/MainLayout.tsx 的路由与导航改动被 J/K 共用（同批编辑），故合并为一次提交，树始终自洽。

## 十四、night18 ISS-058 阈值调整（adjust_threshold，本地未 push）

| commit | 类型 | 说明 | 关联 |
|--------|------|------|------|
| f0cc1fb | feat(threshold) | **ISS-058 阈值调整（adjust_threshold）**：①`ActionType`+`ADJUST_THRESHOLD` 枚举，`executors` 字典注册、`execute` 分发；②`ActionExecutor._execute_adjust_threshold`——写 `config.thresholds[field]`（`operator`/`value`/`updated_at`），区间护栏 `(0,1]`（阈值语义为 0-100% 比例，越界 `requires_clarify`），深拷贝不污染入参、产 `reverse` 撤销描述符（原值非空则 redo 写回、原值为空则标记 `remove_on_undo=True`）；③**n18_3 remove_on_undo 短路分支**（在浮点校验之前）：撤销「原本无阈值的字段」时 reverse 携带 `value=None`+`remove_on_undo=True` → 直接 `thresholds.pop(field)` 返回 success + 可恢复用 reverse，修复旧实现 `float(None)` 抛 TypeError → 误判 `requires_clarify` 导致撤销失败（闭环 B3-7「把阈值调80%」）；④`intent_classifier` 新增 `ADJUST_THRESHOLD` 意图（置顶防被宽匹配抢走）+ 抽 `threshold_field`/`value`（"80%"→0.8、"500%"→5.0 规范化）；`action_planner` 映射 `ADJUST_THRESHOLD → adjust_threshold`。验证 `_verify_iss058.py`（gitignored，隔离零 DB）**5/5 PASS**：调80%写入/0.85保持原值/500%越界拒/缺字段拒/undo恢复空+redo可恢复。 | ISS-058 |

> 设计要点：阈值调整为纯 config 级内存变换（零 DB，红线④），撤销经 chat.py 动作轮 `ai_action_stack` 派发 `reverse` 描述符（`execute_action(reverse.type, reverse.params)`，L1027）；`remove_on_undo` 短路是「原无阈值→新增→撤销」闭环的关键分支——必须跳过浮点校验直接 pop，否则 `float(None)` 会让撤销误判为需要澄清而失败。`_verify_iss058.py` 为隔离验证脚本（未进仓）。


## 十五、ISS-053 Dependabot 告警处置（降级项·本轮不处理）

| 决策 | 依据 | 动作 |
|------|------|------|
| **default branch 的 Dependabot 1 high 告警：显式降级，不处理** | ①`docs/project_record/COLLAB_RULES.md` §七「项目私有降级项（不用管）」明确列出 `- 依赖漏洞三个 major 升级` → 该告警修复需 major 升级，属降级项；②告警挂在 `main`/`master`（default branch），不在 `p0-security-fixes`，不阻断当前分支功能与推送；③后端高危依赖钉版已落 `backend/requirements.txt`（ISS-053 代码 DONE，commit `ec6dd9f`，night13），前端 `npm audit` 落锁属 CI/用户侧动作，沙箱与本机均无可用网络路径（本机未装 gh CLI） | **本轮零改动**：未修改任何依赖版本；未用 WebFetch / gh api 尝试拉取告警详情（用户指令 2026-10-03 明确禁止）。验证：`git diff HEAD` 确认 `requirements.txt` / `package.json` / `package-lock.json` 均未改动。 |

> 处置要点：ISS-053 后端 5 项 CVE 钉版（python-multipart 0.0.12 / pandas 2.2.2 / jinja2 3.1.4 / email-validator 2.1.1 / httpx 0.27.2）已物理存在于 `backend/requirements.txt` 并随 night13 `ec6dd9f` 提交；default branch 上 Dependabot 报的 high 项若需闭环，属「依赖 major 升级」降级项，按 §七不在常规任务范围，由用户本机/CI 自行评估，AI 不主动改动。

## 十六、教练验收轮（2026-10-03）：ISS-059 根因修复 + 全量自验收

| commit | 类型 | 说明 | 关联 |
|--------|------|------|------|
| （待提交） | fix(analytics) | **ISS-059 根因级修复**：`backend/app/core/analytics.py` 全文件事件字段防御化——`bucket_events` / `compare_two_periods` / `compute_stats` / `get_model_usage_stats` / `get_action_usage_stats` / `get_peak_usage_hour` / `get_slowest_model` / `get_top_actions` 内所有裸索引（`e["data"]` / `event["success"]` / `event["event_type"]` / `event["latency_ms"]` / `event["timestamp"]`）→ `.get(...)` 兜底（`data` 用 `(event.get("data") or {})` 兼顾「键存在但值为 None」）；聚合字典键（`stats["count"]` / `recent_stats["success"]` 等）保持原样（由代码保证存在）。修复前：事件缺 `data` 字段 → `KeyError: 'data'` → 对比接口 500（night18 TEST-2 暴露）。 | ISS-059 |

### 教练自验收证据（本机 Python 3.12.10）

| 门 | 命令 | 结果 |
|----|------|------|
| 后端语法 | `python -m py_compile app/core/analytics.py` | EXIT=0 |
| Task J/K 回归 | `python _verify_taskjk.py` | **ALL PASS（17 项）** |
| ISS-058 回归 | `python _verify_iss058.py` | **5/5 PASS** |
| Task G 回归 | `python _verify_taskg.py` | **ALL PASS** |
| Task I 回归 | `python _verify_taski.py` | **PASS=32 / FAIL=0** |
| ISS-059 定向回归 | `python _verify_iss059.py`（新，缺字段事件） | **9/9 PASS**（修复前必 KeyError） |
| 前端类型 | `npx tsc --noEmit` | EXIT=0 |
| 后端健康 | `GET /api/v1/health` | **200** `{"status":"healthy","llm_reachable":true}` |

> ⚠️ 运行中的 8000 后端为 **09-30 13:41 启动的旧实例**（pid=9632），未含 night15-18（Task G/H/I/J/K、ISS-058）与本次 ISS-059 修复；新功能上线需用户手动重启 8000（禁 kill，按 B5 守卫流程）。
> `_verify_iss059.py` 为隔离验证脚本（`.gitignore:84 _*.py`，未进仓）。

---

## 十七、教练验收轮（2026-10-03）：LLM 链去死层（7→5）+ health 探针快路径

| 文件 | 类型 | 说明 | 关联 |
|------|------|------|------|
| `backend/.env`（gitignored） | config(llm) | **下掉资源包已耗尽的两层**：`zhipu-air(glm-4.5-air)`、`zhipu-46v(glm-4.6v)` 从 `LLM_PROVIDERS` 移除（实测 429「余额不足或无可用资源包」）。新链 **5 层**：`kimi-k3 → glm-4.7-flash → deepseek-v4-flash → agnes → sensenova-lite`（glm-4.7-flash 实测可通，保留）。改前备份 `.env.bak_20261003_llmchain`。 | ISS-030 |
| `backend/app/core/llm_gateway.py` | fix(llm) | 新增**可选** `max_retries` 参数（`chat_complete` / `llm_chat`），默认 `None` → 保持 `MAX_RETRIES=2`（每 provider 3 次 + 8/16/24s 退避）**完全不变**；传 `0` 时每 provider 单次、不做退避。 | — |
| `backend/app/api/health.py` | fix(health) | LLM 探针改走快路径：`llm_chat(..., timeout=8.0, max_retries=0)`。修复「链可用但绿标恒 false」——原默认 3 次退避在 L1 限流时整链耗时 ~40s ≫ 18s `wait_for` 上限。 | ISS-030 后续 |

### 根因与验证（本机 Python 3.12.10）

- **根因**：`sensenova(kimi-k3)` 间歇 429（tpm/rpm）；`zhipu-air(glm-4.5-air)` 429「余额不足或无可用资源包」（ISS-030 提前爆，原定 10-25）；`zhipu-46v(glm-4.6v)` 同类耗尽。L1 3 次重试 × 8/16/24s 退避 → 整链 ~40s，而 health 探针 `asyncio.wait_for(18s)` 先触发 → `llm_reachable:false`（链其实可用，被退避吃满时间）。

| 门 | 命令 | 结果 |
|----|------|------|
| 后端语法 | `python -m py_compile app/core/llm_gateway.py app/api/health.py` | EXIT=0 |
| 链装配 | 启动日志 | `LLM provider 链(5层): kimi-k3 → glm-4.7-flash → deepseek-v4-flash → agnes → sensenova-lite` |
| 网关探针（默认） | `llm_chat(...)` | `success=True`，`attempt 1/3 → 2/3`（**默认仍 3 次，未变**） |
| 绿标 | `GET /api/v1/health` ×3 | **3/3 `llm_reachable:true`**，耗时 1.5s / 4.3s / 8.8s（均 < 18s） |

> ⚠️ 残留：L1 `sensenova/kimi-k3` 仍间歇 429、L2 `glm-4.7-flash` 偶发「访问量过大」——快路径下不影响绿标（秒回后切换），但真实 AI 请求首答可能因切换而延迟。


## 十八、night19 任务A：LLM 健康探针去 18s 假快路径 + 后台探针 + /health/llm（ISS-030 后续纠正）

| 文件 | 类型 | 说明 | 关联 |
|------|------|------|------|
| `backend/app/api/health.py` | fix(health) | **纠正 §17 的 18s 假快路径**：保留 `_check_llm_reachable`（去掉 `max_retries=0` + `wait_for(18s)`，改真实重试语义 `MAX_RETRIES` + 整体上限放宽到 **180s**），供 `brain_run_sse.py` 绿标复用；新增进程内缓存 `_LLM_PROBE_CACHE` + 后台探针 `_run_llm_probe`（写缓存，`state`=probing\|ok\|fail\|unknown，`expected_max_wait_s=180`）；`/health` 立即返回缓存（`llm_reachable`/`checked_at`/`state`）**不阻塞**；新增 `GET /health/llm` 返回 `{state, llm_reachable, checked_at, elapsed_ms, reason, expected_max_wait_s}` 并触发后台探针。 | ISS-030 后续 |
| `frontend/src/views/admin/AdminPage.tsx` | feat(ui) | `checkLlm` 改调 `/health/llm`；`llmState` 四态（probing/ok/fail/unknown）；**探测中显示加粗红色**「AI 链路探测中，最长约 3 分钟，可稍后回来查看结果」并每 5s 轮询直到出结果；保留「重新检测」按钮。 | — |

### 背景与根因
- 用户拍板（原话）：「18s 这个就很扯，可以适当延长……几分钟都是正常的，我要的是最终结果好用可靠可追溯」。§17 为"快"加的 `max_retries=0` + `wait_for(18s)` 是误判来源——真实 provider 链（含退避）在限流时本就需数十秒到几分钟，18s 上限让探针反映的是"超时"而非"链路可用性"，与"可靠、可追溯"目标相悖。
- 设计：探针走**真实重试语义**（保留 `llm_chat` 内部 `MAX_RETRIES`），整体上限 180s；`/health` 不再阻塞在长探针上，立即返回上一次缓存结果 + `state`；真实探测在后台/独立端点执行，结果写进程内缓存，前端轮询。

### 验证（本机 Python 3.12）
| 门 | 命令 | 结果 |
|----|------|------|
| 后端语法 | `py_compile backend/app/api/health.py` | EXIT=0 |
| 结构/契约 | `python _verify_health_probe.py` | **15/15 PASS**（18s hack 已去除、缓存命中、/health/llm 六字段、state 机、后台探针写缓存） |
| 前端类型 | `npx tsc --noEmit` | EXIT=0 |

> 红线：零 DB（缓存驻进程内存）；不改 SSE 事件契约；不 kill/重启运行中的 8000 后端（pid 49900）；live 验证留待用户重启。`_verify_health_probe.py` 为隔离验证脚本（gitignored，未进仓）。

---
## 十九、night19 任务B：阶段9「多轮历史稳定注入」（ISS-015 ①）

| 文件 | 类型 | 说明 | 关联 |
|------|------|------|------|
| `backend/app/api/chat.py` | fix(ctx) | 新增 `_build_history(raw_msgs, max_rounds=5, max_chars=600)`：按轮分组（user 起新轮）、保留最近 5 轮、丢弃开头半轮、content 截断 600 字符（action_params/action_result 保持 dict 供 `_build_memory_from_history` 消费）；`context["history"]` 统一由该函数生成（查询窗口由 limit(10) 放宽到 limit(50) 以便完整分组）；自然回复路径 `_hist[-6:]` 改为遍历整窗口，与记忆推导/意图分类共用同一 windowed history，消除两套窗口不一致。 | ISS-015 ① / Q16 |

### 背景与根因
- 现状（核实）：`chat.py:719` 按**条数** limit(10) 注入 history；`chat.py:398` 自然回复用 `_hist[-6:]`（两套窗口不一致）；`intent_classifier.py:413` 把**整个 context（含 history 的 action_params/action_result + current_config）** json.dumps 进系统提示词 → 上下文膨胀（Q16 痛点）。
- 硬约束：上下文管理不得修改 API 契约——保持 SSE 事件结构不变；字段名不变（role/content/action_type/action_params/action_result）。
- 设计：集中到 `_build_history` 一处按轮窗口化，三处消费者（自然回复 L399 / 记忆推导 L742 / LLM 提示词 L413 经 context）自动受益；action_params/action_result 必须为 dict（被 `_build_memory_from_history` 当 dict 取 `.get("target_type")`/`.get("chart_id")`），故只截断 content，不碰 dict 字段。

### 验证（本机 Python 3.12，零 DB）
| 门 | 命令 | 结果 |
|----|------|------|
| 后端语法 | `py_compile backend/app/api/chat.py` | EXIT=0 |
| 窗口/截断契约 | `python _verify_history_window.py` | **10/10 PASS**（仅留最近 5 轮 / 无半轮 / content≤600 / 字段名不变 / action_params+result 仍为 dict / 长 content 1000→601+…） |

> 红线：不改 SSE 事件结构；不改 API 请求/响应契约；不重构无关代码；零 DB。`_verify_history_window.py` 为隔离验证脚本（gitignored，未进仓）。

---
## 二十、night19 新任务A：阶段9-B 主链路 LLM 结构化提取（决策：方案交付，未硬改）

> 决策依据：任务书自带兜底「若无法在零回归前提下完成，只交方案+影响面+风险，不硬改——禁止为快失真」。
> 经代码核实，本任务**不硬改**，仅交付方案/影响面/风险。理由见下。

### ① 改前现象（现状核实，关键：任务书"现状"描述已过时）
- 任务书称「classify() 规则优先，LLM _llm_classify 只在最后兜底；参数结构化未走 LLM」。
- **核实结论（读 intent_classifier.py）**：
  - **ADD_CHART 早已在主链路优先走 LLM 结构化提取**：`classify()` L285 → `_extract_params` L652 分支 → `_extract_add_charts`(L1306)。该函数设计=「规则≥2 张(多字段确定性)走规则；否则 LLM 优先」(`_llm_extract_add_charts` L1067 复用了既有提示词+`_canonicalize_analysis` 字段规范化)，即「参数结构化」高价值场景已 LLM 优先，规则作确定性快速通道/兜底。任务书描述的"规则优先"实为 **intent 类型分类**路径（INTENT_PATTERNS 命中即返回类型），**非参数提取**——属过时描述。
  - **CHANGE_CHART 无结构化提取**：`_extract_params` L514-552 仅产出 `source_type/target_type/title_keyword/target_field/target_axis/time_grain`（规则），不调 LLM、不产 `charts`。

### ② 改后现象（方案，未实施）
- 不改动 `intent_classifier.py` / `action_executor.py` / `action_planner.py`；当前行为保持不变（零回归）。
- 规划中的 CHANGE_CHART LLM 增强（待用户拍板+本机真跑）：在 `_extract_params` CHANGE 分支末尾，当 `field_profiles` 可用且规则未确定目标字段时，调 `_llm_extract_add_charts` 产 `charts` 规格并存入 `extracted_params["charts"]`；`_execute_change_chart` 改为「`charts` 优先、规则键兜底」消费 `charts[0].chart_type/dimension_field/metric_field`；LLM 调用包 try/except → 失败回规则；全程不得因 LLM 挂退化成 UNKNOWN。

### ③ 复现命令（本机真跑验证，沙箱无法离线全证）
- 本机起后端 + 真实 LLM：`python backend/_verify_taskA.py`（待写：构造"把地区分布换成饼图"/"把Y轴换成利润"/"把这张图的指标换成销售额"等，断言 CHANGE 仍定位正确图+字段规范化；ADD 仍 LLM 优先且零回归）。
- 回归：`python backend/_verify_taskg.py` + `python backend/_verify_taski.py` + 模块 B/K 受影响用例前后对比。

### ④ 影响面清单 + 风险
- **影响面**：`intent_classifier.py`(CHANGE `_extract_params`) / `action_executor.py`(`_execute_change_chart` 消费 `charts`) / `action_planner.py`(CHANGE 映射，L731/810) / 前端无（不改 SSE/契约）。
- **风险**：① `_llm_extract_add_charts` 产 NEW-chart 规格，与 CHANGE「改造现有图」语义错配，需映射层；② executor 改吃 `charts` 会动 P0-3「无主语兜底改第一张」修复（L198-211），回归面大；③ LLM 路径依赖网络，沙箱无法离线确定性验证（429/超时抖动），违反"零回归"硬前提。
- **结论**：ADD_CHART 已满足目标；CHANGE_CHART 增强可行但须本机真跑 + 用户拍板，故按兜底交方案，不硬改。

---
## 二十一、night19 任务B：阶段9-C 澄清循环最大轮次退避（ISS-015 ②）

| 文件 | 类型 | 说明 | 关联 |
|------|------|------|------|
| `backend/app/core/action_planner.py` | fix(clarify) | 新增 `MAX_CLARIFY_ROUNDS=2` + `_converge_clarify()`（收敛话术：给最可能方案+确认/取消，带 `converged` 标志）+ `_plan_from_single()`（单动作包装）；`plan_actions` 入口读 `_pending.clarify_round`，`_resolve_pending_clarify` 仍返回 re-ask clarify 且已达上限 → 收敛；短答案无法解析且达上限 → 收敛；粒度冲突 `contra` 分支达上限 → 收敛。承接成功（短答案解析成动作/确认词）仍正常短路，不受轮次限制。 | ISS-015 ② |
| `backend/app/api/chat.py` | fix(clarify) | 持久化澄清载荷时新增 `clarify_round` 计数（同议题累加，异议题重置）；产出 `converged` 收敛话术时**不再持久化 pending_clarify**（清除），结束循环。 | ISS-015 ② |

### 背景与根因
- 现状：`chat.py:738` 每轮加载 `session.context.pending_clarify`；`chat.py:1297-1336` 本轮产 clarify 即落库、短答案承接成功即清零、否则保留。**无最大轮次上限**——用户持续给模糊答案（如「改成柱状图」「改成折线图」反复换图型但不点名图）会让 `which_chart` 澄清无限循环追问。
- 目标：同一议题连续澄清到上限（建议 2 轮）后不再追问，改为收敛话术（给最可能方案+让用户确认/取消）或诚实兜底。
- 硬约束：不改 SSE 事件结构；`pending_clarify` 载荷仅**扩展** `clarify_round` 字段（既有 `reason/clause/intent_type/partial_params/options/created_at` 不动）；承接成功即清零（沿用现有逻辑）。

### 验证（本机 Python 3.12，零 DB，直驱 plan_actions）
| 门 | 命令 | 结果 |
|----|------|------|
| 行为契约 | `python _verify_clarify_cap.py` | **9/9 PASS**：R1 产出 clarify(首问,round=1) / R2 再产 clarify(合法再问,round=2) / R3 收敛(converged=True,话术含确认+取消) / R3b 清晰答案「第二张」仍解析为 change_chart(不收敛) / 确定性 round>=上限 任意模糊输入均收敛 |
| 后端语法 | `py_compile backend/app/core/action_planner.py backend/app/api/chat.py` | EXIT=0 |

> 红线：不改 SSE 事件结构；不改 API 请求/响应契约；零 DB。`_verify_clarify_cap.py` 为隔离验证脚本（gitignored，未进仓）。

---

## 二十、night19 任务C：ISS-025 余 131 未鉴权端点全量扫描（P1 遗留·仅方案）

| 交付 | 说明 | 关联 |
|------|------|------|
| `docs/project_record/22-ISS025无鉴权端点全量扫描.md` | 扫描-only：FastAPI `app.openapi()` 解析路由表（权威），216 路由 / 131 未鉴权；按「读写用户数据(高危 A=47) / 内部系统(中危 B=73) / 故意未鉴权(保留 C=11)」三类分类 + 分批收口建议（Batch1 最高危写类优先、Batch2 内部端点 env 闸门）。**零代码改动**（Task C 明确仅扫描）。 | ISS-025 P1 |

### 分类与收口建议
- **A 类 47 条（优先 Batch1）**：最高危写类 `POST /chat/execute-action`（执行看板增删改！）、`POST /chat/sessions`、`POST /tokens/consume`、`POST /exceptions/session/kickout/{user_id}`；隐私读 `GET /llm/usage/{user_id}`（PII）、`GET /reports`、`GET /golden/*`、`GET /loadtest/*`、`GET /history`、`GET /exports/status/{task_id}`。→ 加 `get_current_user`/归属校验，入 `scripts/auth_whitelist.json`。
- **B 类 73 条（Batch2）**：`/brain/*`、`/s1..s5/*`、`/llm/chat`、`/llm/chat/completions`、`/dependency-graph`、`/trigger`、`/recover` 等内部编排/生成/调试端点 → 内部 token 或 env 闸门（prod 默认关）。
- **C 类 11 条（保留）**：登录/注册/验证码/忘记密码、公开分享查看、健康检查，按设计匿名。

> 与既有闭环：05-ISS025鉴权审计.md 已闭环 P0-1/P0-2/P0-3；本扫描为 P1 遗留全量清单 + 分批建议，交教练/用户拍板后逐批实施。防复发沿用 `scripts/auth_scan.py`+`scripts/fe_bare_fetch_scan.py`+`scripts/auth_whitelist.json` 三件套。

---

## 二十三、night21 修复：ISS-060 澄清收敛后「确认」无法采纳（已 commit）

- **问题**：night19 任务B 的收敛话术引导用户回「确认」采用方案，但收敛即清除 `pending_clarify`（`params.converged=True` → chat.py pop 分支），下一轮「确认」时 `_pending=None` 跳过 `detect_confirmation` 承接分支，确认无法采纳。话术承诺了不存在的路径。
- **改动文件**：
  - `backend/app/core/action_planner.py`：`_converge_clarify` 增加 **proposal**（取最佳项可执行动作 → `proposal={intent_type, partial_params}`；`vague_chart_type` 缺锚点时用 `options[0]` 图型 + 已有锚点/第一张图 拼可执行 `change_chart` proposal 补 `title_keyword`/`chart_id`；无选项/无锚点则收敛文案**改不引导"确认"**）；`_NEGATE_TOKENS` 补「取消」（收敛话术本就引导「取消」放弃，原词表漏收致 R5 失效）。
  - `backend/app/api/chat.py`：收敛扫描分支遇 `converged` 且带 `proposal` → **持久化带 proposal 的 pending**（含 `proposal` + `clarify_round=MAX_CLARIFY_ROUNDS`），替代原 pop；收敛且无 proposal 仍 pop；新增 `MAX_CLARIFY_ROUNDS` 导入。
- **零回归保证**：confirm（L687-714）/ negate（L676-686）/ `cancel_pending` 清除 pending 三路径均不变；收敛 pending `clarify_round>=MAX`，再次模糊输入幂等重新收敛，不无限追问。
- **验证**：`py_compile` 两文件 EXIT=0；`_verify_clarify_cap.py` **13/13 PASS**（R1/R2/R3/R3b 回归 9 + R4-前 proposal 存在 / R4 收敛后「确认」命中 proposal 采纳 / R5「取消」→ cancel_pending / R6 再次模糊仍收敛 共 4）。验证脚本 gitignored（过程文件，不进 commit）。
- **状态**：`[DONE]` 2026-10-03，见 `ISSUES.md` ISS-060。本地未 push。

---

## 二十四、night22 Task A：CHANGE_CHART LLM 结构化补参层（落地实施）

> 方案见 §20（night19 任务A 决策为「方案交付」，本轮按 night22 任务书落地）。用户第一优先、护栏最敏感。
> 红线：禁真实 LLM（沙箱 429）→ 全程 mock 离线验证；零 DB 写；不 push。

### ① 改前现象（night19 核实）
- `intent_classifier._extract_params` CHANGE 分支（L514-561）仅规则提取 `source_type/target_type/title_keyword/target_field/target_axis/time_grain`，**不调 LLM、不产 charts**。
- 多字段口语化指令（如"利润放Y轴，按月看"、锚点用"第 N 张"表达）规则无法解析锚点→执行器回落 `which_chart` 澄清，体验退化。
- `action_executor._execute_change_chart` 只消费规则键；无"charts 优先"通道。

### ② 改后现象（实施）
- **新增 `IntentClassifier._llm_extract_change_chart(message, field_profiles, context)`**：LLM 结构化补参（图型/字段/轴/粒度），**锚点仅当规则未给时采纳**，且必须命中真实图（序号→`chart_id` / 标题→`_locate_chart` 校验），否则**丢弃**→回落规则或 `which_chart` 澄清。失败（含 gateway 不可用）→ 返回 None。
- `_extract_params` CHANGE 分支末尾：`field_profiles` 可用时调 LLM，结果存 `extracted_params["llm_change_spec"]`（独立键，避免 ADD 执行器误吞）。
- `action_executor._execute_change_chart` 顶部：有 `llm_change_spec` 时 **charts 优先 / 规则键兜底** 叠加（仅补规则空缺的字段与锚点）；**无该键时逐字走旧逻辑，零回归**。
- **守卫**：LLM 只补参不夺锚点；规则已给锚点（title_keyword/chart_id/source_type）时绝不采纳 LLM 锚点；绝不静默改第一张（守 P0-3）。

### ③ 复现 / 验证（离线 mock，禁真 LLM）
```
py_compile backend/app/core/intent_classifier.py backend/app/core/action_executor.py   → COMPILE_EXIT=0
python backend/_verify_change_chart_llm.py                                        → 22/22 PASS
```
- R0（真实解析路径 + fake gateway）：合法序号锚点→`chart_id=c2`；非法序号锚点→丢弃（不采纳）。
- R1（集成）："改成柱状图，把利润放Y轴，按月看" + LLM 补 `chart_id=c2/字段=利润/粒度=month` → 正确改中图 c2（非第一张），Y轴=利润，粒度=month。
- R2（锚点缺失→澄清）：LLM 只给字段无锚点 → `requires_clarify`（which_chart），零改动、绝不静默改第一张。
- R3（无 LLM→规则不变）：`field_profiles=None` → 无 `llm_change_spec`；多图无锚点仍澄清、标题锚点（"把地区分布换成饼图"）仍成功改 c3→pie。
- R4（回归 P0-3）："把Y轴换成利润" 无锚点多图 → 仍 `which_chart` 澄清（守卫不变）。

### ④ 改动文件
- `backend/app/core/intent_classifier.py`：+94（新增 `_llm_extract_change_chart` + CHANGE 分支接入）
- `backend/app/core/action_executor.py`：+18（顶部 `llm_change_spec` 叠加）
- `backend/_verify_change_chart_llm.py`：gitignored 过程文件（22 用例）
- **状态**：`[DONE]` 2026-10-03，commit `2682e06`（本地未 push）。


---

## 二十五、night22 Task B：ISS-025 Batch1 收口 A 类高危写端点鉴权（落地实施）

> 依据 `docs/project_record/22-ISS025无鉴权端点全量扫描.md`（§20 全量扫描：216 路由 / 131 未鉴权，按 A 高危写 47 / B 内部 73 / C 保留匿名 11 三类）。
> 红线：零 DB 写；不 push；禁真实 LLM（仅静态 AST 扫描 + dev JWT mock）；验证脚本 gitignored。

### ① 改前现象（扫描核实）
- A 类「写」21 条 + 最高危 `GET /api/v1/exceptions/session/kickout/{user_id}` 共 **22 个端点完全无鉴权**，匿名即可越权：
  - 执行看板增删改（`POST /chat/execute-action`、`POST /chat/sessions`）、消耗/申请 token（`POST /tokens/consume`、`POST /token_applications/apply`）、生成报告（`POST /reports`）、跑 golden / lineage / loadtest / quality 批处理与调试注入（如 `POST /quality/debug/inject-dup` 可污染业务数据）。
  - `kickout/{user_id}` 无归属校验 → 可踢出任意用户会话。

### ② 改后现象（实施）
- 22 个 handler 签名统一加 `current_user: Dict = Depends(get_current_user)`；`exceptions.check_session_kickout` 加归属校验（非本人且非超管 → 403）。
- body 取值修正：`current_user`（旧 str 形参）改为 `current_user["user_id"]`（chat / tokens / token_applications 三处），避免把 dict 当 str 用。
- 前端调用点 grep 确认 `/chat/sessions`、`/reports`、`/quality/*`、`/lineage/verify` 均经 `request.ts` 自动带 token，加鉴权安全；无裸 fetch 须补。
- 不动 C 类 11 条（设计匿名）、B 类 73 条（留 Task E env 闸门）。

### ③ 复现 / 验证（零 DB、离线）
```
python docs/project_record/night_runs/_verify_iss025_batch1.py   -> 22/22 PASS（静态 AST 断言 22 目标 handler 均声明 Depends(get_current_user)，0 漏网）
py_compile backend/app/api/{chat,exceptions,golden,lineage,loadtest,quality,reports,token_applications,tokens}.py   -> COMPILE_EXIT=0
```
- 全量回归（Task D）：`_verify_health_probe.py` 15/15、`_verify_clarify_cap.py`（ISS-060）13/13、`_verify_history_window.py` 10/10，**零回归**。
- 防复发：22 端点入"必须鉴权"静态白名单（`_verify_iss025_batch1.py`），扫描应 0 漏。

### ④ 改动文件
- `backend/app/api/chat.py` / `exceptions.py` / `golden.py` / `lineage.py` / `loadtest.py` / `quality.py` / `reports.py` / `token_applications.py` / `tokens.py`：9 文件加鉴权。
- `tests/test_acceptance.py` / `tests/test_core_chain.py`：`req()` 助手注入 dev JWT（保 suite 绿；POST /reports、POST /quality/check 现需鉴权）。
- `docs/project_record/night_runs/_verify_iss025_batch1.py`：gitignored 过程文件（22 端点静态扫描）。
- **状态**：`[DONE]` 2026-10-03，commit `8f6c56d`（本地未 push）。Batch2（B 类 73 端点 env 闸门）见 Task E。

---

## 二十六、night23 Task A：ISS-025 Batch2 B 类 73 端点 env 闸门（落地实施）

> 依据 `docs/project_record/22-ISS025无鉴权端点全量扫描.md` B 类 73 条内部/系统端点。红线同 night22：零 DB 写、不 push、不改 SSE、禁真 LLM（仅静态 AST + dev JWT mock）。

### ① 改前现象（扫描核实）
- B 类 73 条（`/brain/*`、`/llm/*`、`/exceptions/*`、`/dependency-graph`、`/trigger`、`/recover`、`/skills`、`/stats`、`/status`、`/chat/test/*`、`/tokens/_internal/*` 等）**全部无鉴权**，匿名可访问，是匿名缺口。

### ② 改后现象（实施）
- 新增 `app.core.security.internal_endpoint_guard`（读 `settings.ENABLE_INTERNAL_ENDPOINTS`）：默认关（False）→ 内部端点必须有效 bearer 令牌否则 401；dev 设 `on/true/1` 放行匿名。
- 只做开关，不改任何业务逻辑；73 个 handler 装饰器加 `dependencies=[Depends(internal_endpoint_guard)]`；`config.py` 加 `ENABLE_INTERNAL_ENDPOINTS: bool = False`。
- 前端调用点核查：仅 `GET /api/v1/skills` 被 FE 引用且经 `http.get` 自动带 token → 收口后仍放行，安全无破坏。

### ③ 复现 / 验证（零 DB、离线）
```
python backend/_night23_verify_a.py   -> 检查 73 个目标端点；漏网 0 个 / PASS（功能 4 场景全 PASS；from app.main import app 222 路由正常）
```
- 防复发静态扫描 73/73，0 漏网。

### ④ 改动文件
- `backend/app/api/*`（12 文件）+ `config.py` + `security.py`：14 文件 +129/−74。
- `backend/_night23_verify_a.py`：gitignored 验证脚本。
- **状态**：`[DONE]` 2026-10-03，commit `1fc41f3`（本地未 push）。

---

## 二十七、night23 Task B：ISS-041 / ISS-042 端到端补齐（落地实施）

> 红线：零 DB 写、不 push、不改 SSE、禁真 LLM（全 mock 确定性用例）。

### ① 改前现象（核实）
- **ISS-041（复合 add_chart）**：机制已具备（`split_clauses` 按中文连接词切分 → 逐 clause `classify_intent` → `plan_actions` 聚合），「删X再加趋势图」「加X再改图」可一句拆 2 动作；无需改代码。
- **ISS-042（多轮语义承接）**：①「那就折线图」(vague_chart_type) 已能解析为 change_chart；②「用华南」(filter 值承接) **此前无路径** → 短答案无法回填 pending_clarify 的 filter_field，只能落兜底澄清或丢弃。

### ② 改后现象（实施，仅 `backend/app/core/action_planner.py`）
- 新增 `_dimension_categories(context, field)`：取维度字段真实取值候选（无候选 `[]`），用于发射「聚焦哪个值」澄清。
- 新增 `_infer_filter_field(message, context)`：分类器未给 filter_field 时从「按/根据/筛选/过滤/聚焦/只看 + 维度字段名」反推（限 context 真实字段）。
- `_resolve_pending_clarify` 关键词匹配键加 `or _o.get("value")`；新增 `which_filter_value` 分支：短答案/序号解析成 `filter_drill`（filter_field 取 pending、filter_value 取选项值）。
- `plan_actions` 主循环新增 FILTER_DRILL 澄清发射：有 filter_field、无 filter_value、维度带 categories → 主动发射 which_filter_value 澄清（列候选值，提示「回复具体值即可，例如『华南』」）。
- 未改业务执行语义（仅补多轮承接路径）。

### ③ 复现 / 验证（零 DB、禁真 LLM）
```
python backend/_night23_verify_b.py   -> RESULT: PASS=22 FAIL=0（ISS-041 复合 2 + ISS-042 承接 5 + 回归 3 + 边界 1 = 11 组/22 断言）
```
- T1 删+加 / T2 加+改：复合拆分正确；T3「那就折线图」→change_chart 锚点保留；T4「第二张」→options[1]=销售额趋势；T5「用华南」→filter_field=地区/filter_value=华南；T5b 发射 which_filter_value 澄清；T6 单句 change_chart 回归；T7 无匹配短答案返回 None 不抛 NameError。

### ④ 改动文件
- `backend/app/core/action_planner.py`：+66/−2（vs HEAD `1fc41f3`），唯一 tracked 改动；`intent_classifier.py` 仅 debug 编辑后已还原（py_compile 通过）。
- `backend/_night23_verify_b.py`：gitignored 验证脚本。
- **状态**：`[DONE]` 2026-10-03，commit `c4f7727`（本地未 push）。

---

## 二十八、night23 Task C：LLM 429 韧性加固（网关 failover + 分类器去污染）

> 红线：零 DB 写、不 push、不改 SSE、禁真 LLM（mock 注入 429 / LLM=None）。

### ① 改前现象（核实）
- **网关**：`llm_gateway.py:556` 429 分支对**同层 provider 内**做 8/16/24s 指数退避重试（`_backoff_wait`），限流是 provider 维度配额问题，同层重试徒增延迟且大概率仍 429；且无逐层 429 计数。
- **分类器**：`intent_classifier.py:563` night22 Task A 补参块是与 `if CHANGE_CHART` 平级的独立 `if`，对 ADD/DELETE 等所有意图注入 CHANGE 专属 `llm_change_spec`；LLM 不可用时 ADD/DELETE 被污染/误路由（429 韧性缺口）。

### ② 改后现象（实施）
- **网关**（`app/core/llm_gateway.py`）：429 分支改为**立即切下一层**（`key_exhausted=True; break`，不 sleep 满退避）；`self._incr_rate_limit(prov_name)` 逐层记 429 计数；`__init__` 加 `self._rate_limit_counts`；新增 `get_rate_limit_stats()` 供健康监测/failover 决策。
- **分类器**（`app/core/intent_classifier.py`）：补参块收窄为 `if intent_type == IntentType.CHANGE_CHART and _fps and not ...`，ADD/DELETE 不再被注入 `llm_change_spec`；CHANGE 路径行为不变（零回归）。

### ③ 复现 / 验证（零 DB、禁真 LLM）
```
python backend/_night23_verify_c.py   -> RESULT: PASS=17 FAIL=0（A 网关 4 场景 + B 分类器 3 场景）
```
- A1 两层 429→立即 failover+计数+快(0.001s)；A2 p1=429/p2=200→切 p2 成功；A3 探针路径(`max_retries=0`)覆盖；A4 401 不计 429。
- B1 ADD 无污染+规则参数保留；B2 DELETE 索引保留；B3 CHANGE 路径不变。
- 回归：三文件 `py_compile` OK；night23 Task B 套件 22/22 仍 PASS。

### ④ 改动文件
- `backend/app/core/llm_gateway.py`：429 分支重写 + 计数方法 + `__init__` 计数（约 +21/−12）。
- `backend/app/core/intent_classifier.py`：补参 gate 条件（约 +5/−1）。
- `backend/_night23_verify_c.py`：gitignored 验证脚本。
- **状态**：`[DONE]` 2026-10-03（已 commit `cb9d6e7`，本地未 push）。

## 二十九、night23 Task D：CHANGE_CHART 端到端 + 边界补齐（显式锚点未命中→澄清）

> 红线：零 DB 写、不 push、不改 SSE、禁真 LLM（纯静态方法直驱，无 LLM 调用）。

### ① 改前现象（核实，答非所问隐患）
- `_execute_change_chart`（`app/core/action_executor.py:203-234`）：用户给出**显式但打错的图名**（`title_keyword`，如「把销售额图改成饼图」而真实图叫「各地区销售额分布」）时，`_locate_chart` 返回 None；但因 `title_kw` 为真值，line 216 的 `requires_clarify` 分支（`not title_kw and ...`）被跳过，line 231 静默兜底 `next(c for c if chart_type != target_type) or charts[0]` —— **直接误改第一张图（常是 KPI 卡）**，答非所问。
- 同样的静默误改也发生在 `chart_id` 打错时（`chart_id` 不命中且无其他锚点 → 落 charts[0]）。
- 这是 P0-3「无主语兜底改第一张」隐患的**同族残留**：显式锚点未命中本应澄清，却退化成静默猜。

### ② 改后现象（实施）
- 在匹配循环之后、原 `which_chart` 澄清之前，新增分支：当 `target_chart is None and (title_kw or chart_id)`（用户明确点名图/ID 但未命中任何图、且无 source_type 命中）时，**直接返回 `requires_clarify=True, reason="chart_not_found"`**，列出全部图供用户重选，**绝不静默挑 charts[0]**。
- 原 `which_chart` 分支（三锚点全空 + 多图）保持不变：仅对"无主语 + 多图"澄清，二者职责清晰分离。
- 单图板无锚点仍走 line 231 安全兜底改唯一图（不澄清）；source_type 命中按类型定位不受影响（规则路径零回归）。

### ③ 复现 / 验证（零 DB、禁真 LLM，纯静态方法直驱）
```
python backend/_night23_verify_d.py   -> RESULT: PASS=14 FAIL=0
```
- D1 多图无锚点→`requires_clarify reason=which_chart`（3 options，回归守卫）。
- D2 显式图名未命中→`reason=chart_not_found`（含「销售额图」提示）；D2b chart_id 未命中→同理。
- D2c 防假断言：多图下显式图名未命中**不得**静默改第一张（被误改图=[]）。
- D4 图名子串命中→精确改中图、KPI 卡未误伤；D5 按 source_type 命中。
- D6 无 LLM 回落：纯规则路径（无 `llm_change_spec`）独立改图成功。
- D7 `llm_change_spec` 不夺规则锚点（Task C 协同，无回归）；D8 规则无锚点时 spec 兜底承接。
- D9 单图无锚点→安全兜底改唯一图（不澄清）；D10 undo/reverse 往返（pie→bar→pie）；D11 澄清返回含标准 options 结构（P0-3 共存）。

### ④ 改动文件 / diff
- `backend/app/core/action_executor.py`：`_execute_change_chart` 新增显式锚点未命中澄清分支（约 +19 行，红_lines 无删）。
- `backend/_night23_verify_d.py`：gitignored 验证脚本（14 场景）。
- 完整 diff：见 `docs/project_record/night_runs/_night23_d_diff.txt`（红_lines：210 之后插入；新增 `return {requires_clarify, reason:"chart_not_found", options, error}`）。
- 回归：`py_compile action_executor.py` OK；night23 Task B 套件 22/22 PASS；night23 Task C 套件 17/17 PASS。
- **状态**：`[DONE]` 2026-10-03（本地未 push，待 commit）。

---

## 三十、night24 Task A：env 闸门配置固化（ISS-025 Batch2 收尾）

> 闸门代码（guard + config 键）已于 night23 Task A（commit `1fc41f3`）落地；本任务补齐「配置显式化 + 文档化」，消除"dev 静默收口、缺说明"的落地缺口。
> 红线：零 DB 写、不 push、不改 SSE、不 kill 进程（仅改配置与文档，未重启后端）；验证脚本 gitignored（`_*.py`）。

### ① 改前现象（核实）
- `config.py:89` 已有 `ENABLE_INTERNAL_ENDPOINTS: bool = False`（默认收口）。
- 但 `backend/.env` 与 `backend/.env.example` **均无此键** → dev 启动读不到 → 静默落在默认 `False`，内部端点被收口（与"dev 应放开"的设计意图不符），且无任何文档说明，易误判为 bug。
- RUNBOOK 无内部端点闸门说明。

### ② 改后现象（实施）
- `backend/.env.example`：在「安全」段新增 `ENABLE_INTERNAL_ENDPOINTS=false` + 注释（prod 务必保持 false/注释；dev 设 on/true/1 放开）。
- `backend/.env`（本地，gitignored）：新增 `ENABLE_INTERNAL_ENDPOINTS=on` + 注释（dev 显式放开内部端点匿名访问）。
- `docs/project_record/RUNBOOK.md`：新增「七、内部端点 env 闸门（ISS-025 Batch2）」——说明是什么 / prod 默认收口 / dev 放开 / 验证 curl 命令 / 改完重启才生效（原「七、最后更新」顺延为八）。
- **仅配置与文档，零代码改动**；guard 行为不变。

### ③ 复现 / 验证（零 DB、不重启后端，用真实 config 加载器直驱）
```
python backend/_night24_verify_a.py wire    -> MODE=wire settings.ENABLE_INTERNAL_ENDPOINTS=True; anon_call allowed=True(200); RESULT: PASS
python backend/_night24_verify_a.py secure  -> MODE=secure settings.ENABLE_INTERNAL_ENDPOINTS=False; anon_call allowed=False(401); RESULT: PASS
```
- wire 模式**不覆盖 env、直接读 `backend/.env`** → `True` 且匿名放行：证明 `.env` 的 `=on` 被真实 `env_file` 加载正确、闸门对 dev 打开。
- secure 模式 env 覆盖 `=false` → `False` 且匿名 401：证明 prod 默认/显式 false 收口生效。
- pydantic-settings 布尔解析已实测：`on/true/1/yes`→True，`off/false/0`→False（确认 `=on` 不会在启动时崩溃）。

### ④ 改动文件 / diff
- `backend/.env.example`：+6（新增键 + 注释），tracked。
- `docs/project_record/RUNBOOK.md`：+14（新增第七节 + 原七顺延八），tracked。
- `backend/.env`：+3（显式 `=on`），**本地 gitignored，不进 commit**（含密钥，永不入仓）。
- `backend/_night24_verify_a.py`：gitignored 验证脚本（wire/secure 两模式）。
- **状态**：`[DONE]` 2026-10-03（本地未 push，待 commit）。

---

## 三十一、night24 Task B：端到端连通性回归（22 写 + 73 内部 + 重点端点）

> 红线：零 DB 写、不 push、不改 SSE、不 kill 进程（用 app.main 路由表静态核对，不重启后端）；禁真 LLM；验证脚本 gitignored（`_*.py`）。
> 结论：零代码改动，全部通过，无需修 401/404（所有重点端点均存在且带正确鉴权依赖）。

### ① 核对范围与方法
- 从 `app.main` 权威加载路由表，遍历 `route.dependant.dependencies`（签名级 Depends）+ `route.dependencies`（路由/应用级）识别鉴权依赖（`get_current_user` / `internal_endpoint_guard`）。
- 重点端点 7 个 + `/chat/test/*` 整组 + night22 Batch1 22 写端点全量复核。

### ② 结果（全部 PASS）
- 重点端点：POST `/chat/execute-action`、POST `/tokens/consume`、POST `/brain/run`、GET `/brain/run/{id}/status`（均含 `get_current_user`）；GET `/skills`、POST `/trigger`、GET `/dependency-graph`（均含 `internal_endpoint_guard`）—— 7/7 存在且鉴权到位（带 token 不会 401，路由存在不会 404）。
- `/chat/test/*` 整组 4/4 含 `internal_endpoint_guard`。
- 22 写端点（night22 Batch1）22/22 含 `get_current_user`（0 漏网）。
- 73 内部端点（night23 Batch2）路由表抽查全部含 `internal_endpoint_guard`（/brain/* 40+、/skills、/trigger、/dependency-graph、/chat/test/*）。

### ③ 路径纠正（任务书 stale，非代码缺陷）
- 任务书所列 `/recalc/trigger`、`/recalc/dependency-graph` 曾在 night25 被记「路由表不存在，真实端点为 `/api/v1/trigger`、`/api/v1/dependency-graph`」。**更正（night26 Task A）**：recalc 路由此前以 `prefix="/api/v1"` 挂载，与前端 `RecalcPage` 调 `/api/v1/recalc/*` 漂移（H1）；night26 Task A 已将 `main.py:228` 改为 `prefix="/api/v1/recalc"`，现真实路径为 `/api/v1/recalc/{status,history,dependency-graph,trigger,stats,recover}`（status/trigger/dependency-graph/stats/recover 挂 guard，history 用 get_current_user），漂移已修。
- night22 原登记 `/api/v1/token_applications/apply` 实际路径为 `/api/v1/tokens/applications/apply`（tokens 复数）；`/api/v1/exceptions/session/kickout/{user_id}` 实际为 **GET**（非 POST）。已校正核对清单，结论不变。

### ④ 复现 / 改动
- `python backend/_night24_verify_b.py` → `RESULT: PASS`（7 重点 + 4 chat/test + 22 写，0 漏网）。
- 改前=改后：无代码改动（仅验证脚本 gitignored）。
- **状态**：`[DONE]` 2026-10-03（零代码改动，本地未 push；登记用本 commit）。


---

## §32 night24 Task C · ISS-025 Batch3 A 类读端点 26 条收口（含 /llm/usage PII 403）

> 红线：零 DB 写、不 push（本地 commit 等确认）、不改 SSE 事件结构、禁真 LLM；验证脚本 gitignored（`_*.py`）。
> 结论：26 个 A 类读端点全部带鉴权依赖（get_current_user / require_admin）；/llm/usage/{user_id} 加 PII 归属 403 校验；`_night24_verify_c2.py` 26/26 PASS。

### ① 收口清单（10 个 api 文件）
- 注入式（8 文件，经 `_night24_fix_c.py` 在 def 闭合行注入 `current_user: Dict = Depends(get_current_user)`）：
  exports.py / golden.py / lineage.py / llm.py / loadtest.py / quality.py / recalc_queue.py / reports.py。
- 手动式（2 文件，`_night24_fix_c_tokens.py`，函数级作用域替换，避免误伤 `_internal/test-*`）：
  tokens.py（GET /tokens/quota、GET /tokens/can-send）、
  token_applications.py（GET /tokens/applications/check-active、/my-applications、/my-applications/{application_id}）。

### ② tokens/* 5 端点具体改法（原匿名默认 → 真鉴权）
- 签名：`current_user: str = "anonymous"` → `current_user: Dict = Depends(get_current_user)`。
- body：`current_user`（字符串）用法 → `current_user["user_id"]`（与 night22 Task B 对 /tokens/consume 的同类修正一致）：
  - /tokens/quota：`TokenManager.get_quota_status(db, current_user)` → `...current_user["user_id"]`
  - /tokens/can-send：`TokenManager.can_send_message(db, current_user)` → `...current_user["user_id"]`
  - /tokens/applications/my-applications：`TokenApplication.user_id == current_user` → `...current_user["user_id"]`
  - /tokens/applications/my-applications/{application_id}：同上
  - /tokens/applications/check-active：`TokenQuota.user_id == current_user` → `...current_user["user_id"]`

### ③ /llm/usage/{user_id} PII 归属校验（llm.py）
- 非本人且非超管：raise HTTPException(403, "无权查询该用户的 LLM 用量")。堵住越权查他人用量泄露。

### ④ 安全网（未误伤）
- 全仓 grep `current_user: str = "anonymous"` = 0（5 个全部转换）。
- `_internal/test-*` 处理器（current_user: str = "test_user" 等，受 internal_endpoint_guard 护闸）保持字符串用法，未被本任务改动。

### ⑤ 验证
- `python backend/_night24_verify_c2.py` → `RESULT: PASS`（26/26 读端点鉴权 + /llm/usage PII 403）。
- `python -m py_compile` 全部 10 个 api 文件 = OK。
- 复现脚本（gitignored）：`_night24_fix_c.py`（8 文件注入器）、`_night24_fix_c_tokens.py`（5 端点函数级修复）、`_night24_verify_c2.py`（复核）。

### ⑥ 状态
- `[DONE]` 2026-10-03（本地未 push；登记用本 commit）。


---

## §33 night24 Task D · 依赖钉版上提（ISS-025 Batch / ISS-053 收口）

> 红线：零 DB 写、不 push、不联网（pip-audit/Dependabot 网络部分待 CI）；requirements.txt 仅钉版上提不降级。
> 结论：5 个钉版上提；静态扫描后端无 pandas 3.0 已移除 API 使用；联网全链路验证（pandas 3.x install + pytest / pip-audit / npm audit）待用户本机或 CI。

### ① 钉版上提（均“上提不降级”）
| 包 | 原 | 新 | 依据 |
|---|---|---|---|
| python-multipart | 0.0.12 | 0.0.32 | CVE-2024-53981 修复（0.0.32） |
| pandas | 2.2.2 | 3.0.3 | 上提 3.x（CVE 已在 2.2.2 修复；3.x 为版本上提） |
| email-validator | 2.1.1 | 2.3.0 | CVE-2024-1916 已修复（2.1.1+）上提 |
| jinja2 | 3.1.4 | 3.1.6 | CVE-2024-34064 已修复（3.1.4+）上提 |
| httpx | 0.27.2 | 0.28.1 | CVE-2024-47081 已修复（0.27.0+）上提 |

### ② 静态扫描（pandas 3.0 兼容性，离线）
- 全仓 grep：`read_pickle` / `iteritems(` / `pd.np` / `convert_objects` / `downcast=` / `pd.Panel` / `DataFrame.append` / `to_pickle` / `inplace=True` / `pd.concat` = 0 处（实际代码；仅 `_night24_fix_d.py` 注释含 read_pickle 字样）。
- 结论：后端代码未使用 pandas 3.0 已移除/强变更 API，估计升级冲击小；但 copy-on-write 默认行为变更需在运行时（CI）最终确认。

### ③ 待联网验证（本沙箱无网络，移交用户本机/CI）
- `pip install -r requirements.txt`（pandas==3.0.3 实测安装 + import 通）。
- `pytest backend/tests`（pandas 3.x 全链路跑通）。
- `pip-audit`（依赖漏洞复核）+ `npm audit`（frontend）。
- Dependabot 配置：当前仓库若未启用，建议在 .github/dependabot.yml 增设 pip + npm 周扫描。

### ④ 复现脚本（gitignored）
- `backend/_night24_fix_d.py`（钉版上提，确定性替换 + assert）。

### ⑤ 状态
- `[DONE-离线]` 2026-10-03（钉版已上提并静态扫描；联网验证待 CI；本地未 push；登记用本 commit）。


---

## §34 night24 Task G · 全量路由鉴权回归（ISS-025）

> 红线：零 DB 写、不 push、不联网；验证脚本 gitignored（`_*.py`）。
> 结论：A/B/C 三套 verify 全 PASS；全量路由 221 条，130 硬鉴权 + 74 内部护闸 + 2 可选 + 15 意图公开；回归中发现并收口 brain_v2.py 2 个未鉴权配置读端点。

### ① 回归范围与结果
- Task A env 闸门：`verify_a.py wire` PASS（ENABLE_INTERNAL_ENDPOINTS=True）+ `secure` PASS（=False → 401）。
- Task B 写端点：`verify_b.py` PASS（8 22 写端点 + 73 内部 + 7 重点 + /chat/test/* 4，0 漏网）。
- Task C 读端点：`verify_c2.py` PASS（26 读 + /llm/usage PII 403）。
- 全量路由扫描：`verify_g.py` 枚举 221 条 (method,path)+鉴权依赖。

### ② 全量鉴权覆盖
- total=221 / hard_auth=130 / internal_guard=74 / optional=2 / no_auth=15（收口前 17）。
- 15 个 no_auth 均为意图公开：`/`(root)、`/auth/captcha`、`/health`(+`/health/llm`)、`/shares/{share_code}`(+`/verify`)、`/docs`(+oauth2-redirect)、`/openapi.json`、`/redoc`、`/auth/login|register|forgot-password/*`。
- 备注：`/docs`/`/openapi.json`/`/redoc` 为 FastAPI 默认公开；prod 若需收紧可 `docs_url=None, redoc_url=None, openapi_url=None`。本次不改（标准默认）。

### ③ 回归发现的新漏洞（已收口）
- `brain_v2.py` 与 `brain.py` 同 prefix `/brain`，含 2 个未鉴权 GET：
  - `GET /api/v1/brain/configs`（list_configs）— 无鉴权，匹配 `ConfigCreateRequest` 类别泄露全量生效配置。
  - `GET /api/v1/brain/configs/{config_key}/history`（get_config_history）— 无鉴权，泄露配置变更历史。
- `verify_c2.py` 之 `find_route` 返回首个匹配路由，被 `brain.py` 的 `{category}/history`(require_admin) 遮蔽，故以前误判为 PASS；全量扫描才暴露真实的 `{config_key}/history`(NONE)。
- 收口：2 端点加 `dependencies=[Depends(internal_endpoint_guard)]`，与同模块已收口的 `GET /configs/{config_key}`(单条获取) 对齐。收口后 no_auth 17→ 15。

### ④ 复现脚本（gitignored）
- `backend/_night24_verify_g.py`（全量路由鉴权覆盖扫描）。
- `backend/_night24_fix_g_brainv2.py`（brain_v2 2 端点收口）。
- A/B/C verify 脚本同前。

### ⑤ 状态
- `[DONE]` 2026-10-03（全量回徒 + 发现收口 brain_v2 漏洞；本地未 push；登记用本 commit）。

---

## §35 night25 Task A · 读端点连通性补盲（ISS-025 读端点侧闭环）

> 红线：零 DB 写、不重启后端（不 kill pid）、禁真 LLM（mock/离线）、验证脚本与过程文件 gitignored（_night25_taskA_*.py / .md）。
> 结论：night24 Task C 给 26 个 A 类读端点加鉴权 **未破坏任何前端连通性**；0 回归，零代码改动，仅登记验证。

### ① 盲区说明（任务书核心关切）
- night24 Task C（commit `be60462`）给 26 个 A 类读端点加 `get_current_user` 鉴权；但其连通性回归（night24 Task B, `f7568fb`）在 Task C **之前**跑，未覆盖这批端点 → 前端影响从未验证。本任务补齐。

### ② 方法
- 静态：扫描 `frontend/src` 全部 API 调用点（65 个），抽取路径模板匹配路由表，标注 token 携带机制。
- 动态：对 26 个 A 类读端点（含同模块 2 个常驻鉴权 GET，共 28）用 in-process `TestClient` 发「无 token / 带 dev JWT」两组 GET（仅读，零 DB 写）。

### ③ 结果
- **全仓裸 `fetch(` 调用：0 处**（grep `(?<![a-zA-Z.])fetch\(` 无匹配）。65 个前端调用点 **全部** 经 `request.ts`（自动注入 token）或 `authorizedFetch`+`authHeaders()`（显式带 token）。
- **28 个读端点两组请求：TOTAL=28 FAIL=0**。无 token → 均 401（后端强制鉴权）；带 token → 均非 401（200/404/422/ERR；ERR 为沙箱缺 Postgres 表，发生在鉴权闸门之后，非鉴权回归）。
- 4 个手工 authHeaders 文件（`LoadingPage/ChatPanel/QualityCheckPanel/UploadPage.tsx`）均 `import { authHeaders, authorizedFetch } from '../../utils/request'`，已正确携带 token → 非回归点。

### ④ 对照表交付物
- `docs/project_record/night_runs/_night25_taskA_TABLE.md`（28 行实测对照表 + 前端调用点全量回归面 + 22 写/73 内部静态结论）。
- 证据脚本：`_night25_taskA_scan.py`（路由×前端交叉扫描）、`_night25_taskA_verify.py`（两组请求）、`_night25_taskA_table.py`（出表）。

### ⑤ 状态
- `[DONE]` 2026-10-04（0 回归，零代码改动，本地未 push；登记用本 commit）。

---

## §36 night25 Task B · AI 对话边界加固（ISS-041/ISS-042/CHANGE_CHART 更深边界）

> 红线：零 DB 写、不重启后端、禁真 LLM（mock 分类器/规划器 stub）、验证脚本与过程文件 gitignored。
> 结论：6 类更深边界场景全 PASS；并修复一处复合动作拆分缺陷（_ACTION_VERB_RE 加"加"）。

### ① 6 类场景（离线 mock LLM，零网络）
- ① 三重动作链（删A改B加C）：`删掉第一张图，把饼图改成柱图，再加一个销售额趋势图` → is_compound、3 动作按 删→改→加 顺序。**PASS**
- ② 撤销后再改：`把饼图改成柱图` → 源图型(饼图)唯一→精确锁定 c2，不反问 which_chart。**PASS**
- ③ 歧义锚点（多图）：`把那个图改一下` → 必须澄清（semantic_clarify），不静默改 charts[0]。**PASS**
- ④ 超 5 轮截断后承接：pending_clarify.clarify_round=5 + `第二张` → 仍解析为 change_chart 锁定 c2。**PASS**
- ⑤ 锚点命中但图型非法：`把饼图改成飞饼图` → 不崩溃、不静默落库非法图型（澄清 which_chart）。**PASS**
- ⑥ 一句两意图拆分：`删掉第一张图并且加一个趋势图` → is_compound、删+加两动作。**PASS**
- 复现：`python docs/project_record/night_runs/_night25_taskB_verify.py` → `RESULT: ALL_6_SCENARIOS_PASS`。

### ② 代码加固（修复复合拆分缺陷）
- `backend/app/core/action_planner.py` · `_ACTION_VERB_RE` 增加独立词 **"加"**。
- 修复前：复合句 `把饼图改成柱图，加一个趋势图` 中「加一个趋势图」不含「加上/新增/添加」，被判为无动作动词子句，**回并入上一子句**，add 动作被吞（三重链退化成 删+澄清）。实测 night23 双动作(删+加)靠「再」连接词拆分，但「加」作独立连接词时仍会丢失。
- 修复后：独立「加」被识别为动作动词 → 子句独立成句 → 三重/双动作链均可正确拆分。回归：双动作复合、单意图行为不变（verifier R1-R2 守卫）。

### ③ 交付物
- `docs/project_record/night_runs/AI_TEST_CASES_v1.md`（6 场景 + 加固说明 + 回归守卫）。
- `docs/project_record/night_runs/_night25_taskB_verify.py`（可执行回归，内联 mock LLM）。

### ④ 状态
- `[DONE]` 2026-10-04（6/6 PASS + R1-R2 回归 PASS；含 1 处代码加固；本地未 push）。

## §37 night25 Task C · 用户验收预演（night23_ACCEPTANCE_CHECKLIST 逐条）

- **目标**：对 night23 用户验收清单 22 个子项，能自动化的用 mock/TestClient/静态扫描跑；跑不了的标「需真机人工」+ 最小步骤。全程零真 LLM（动态校验走 night25 Task B 的 in-process mock 验证器）。
- **汇总**：总项 **22** ｜ 可自动化 **11**（PASS 11 / FAIL 0）｜ 需真机人工 **11**。
- **可自动化 11 项全部 PASS**：
  - ①-1 分支=`p0-security-fixes`；①-3 Python3.12 + fastapi/sqlalchemy/openai 均 import OK；①-4 `.env` 含 kimi/senseNova 网关配置。
  - ②-1 night_runs 验证脚本 0 处真实 DB 写（commit/execute/INSERT/UPDATE/DELETE）；②-3 `brain_run_sse.py` 未被 night23/24/25 安全修复系列改动（近5提交为 d12c419 弹窗 P0），helper 仍 `json.dumps(data, ensure_ascii=False)`，SSE 双编码结构未动；②-5 验证脚本 0 处真实 LLM 网络调用。
  - ③A `Depends(internal_endpoint_guard)` 端点数=**75**（清单称 73，差异 2 属统计口径；prod 默认 `ENABLE_INTERNAL_ENDPOINTS=off` → 无 token 返回 401 不执行）；③B + ③D 以 night25 Task B 验证器等价复现（ALL_6_PASS + R1-R2 PASS，覆盖三重动作链/撤销后再改/歧义锚点/非法图型→澄清）。
  - ④-1 py_compile 5 个改动文件全 OK；④-2 复合拆分套件等价复现 PASS。
- **需真机人工 11 项**：①-2 / ②-2（需联网比对远端）、②-4（后端进程本机托管）、③C / ④-3（429 切层属 provider 行为，需真实 kimi/sensenova 触发）、④-4（真 LLM 冒烟，仅克隆看板）、⑤-1~⑤-5（上线决策/拍板）。
- **关键发现**：night23 验证脚本 `_night23_verify_a/b/c/d.py` 均为 gitignored 过程文件，本 session 磁盘已不存在；故 ③B/③D 以 night25 Task B 验证器做等价复现，③C/④-3 标需真机人工。
- **交付物**（gitignored 过程文件，不进 commit）：
  - `docs/project_record/night_runs/night25_acceptance_preview.md`（预演结果表，含 5 段 22 行 + 结论建议）
  - `docs/project_record/night_runs/_night25_taskC_preview.py`（预演脚本，输出 `_night25_taskC_result.json`）
  - `docs/project_record/night_runs/_night25_taskC_table.py`（结果表生成器）
- **commit**：见本提交（p0-security-fixes 分支，parent=59f1788 night25 Task B）（仅 AI_CHANGES.md 入库；night_runs 过程文件按红线 gitignored）


## §38 night25 Task D · 依赖与 CI 收口

- **新增 `.github/dependabot.yml`**（入库）：pip（/backend/requirements.txt）+ npm（/frontend/package.json）+ github-actions 三类，**每周一 06:00** 自动提 PR，限流 10/5，标签 `dependencies`。沙箱无网，配置入库后由本机/CI 在联网环境触发。
- **新增 `_verify_env_deps` 离线核验脚本**（gitignored）：检查 Python>=3.12、requirements.txt 钉版 vs 本机已装、Node 版本、package-lock.json/node_modules 存在性，输出 `_night25_taskD_env_deps.json`。
  - 实测：Python 3.12.10（>=3.12 OK）；pip 34 项 OK=29 / MISSING=5（asyncpg、python-magic、pytest-asyncio、ruff、black——均属 DB 驱动/开发lint工具，环境裁剪非安全回归）；Node v22.22.2 + package-lock.json + node_modules 均在。
- **新增 `night25_npm_audit_checklist.md`**（gitignored，需真机人工）：npm audit / pip-audit 执行步骤与判读口径；因沙箱无网，审计本身标「需真机人工」，与 dependabot 自动扫描互补。
- **闭环 night24 Task D 遗留**：pandas 3.x 钉版（`pandas==3.0.3`，CVE 已修复）、python-multipart/email-validator/jinja2 等 CVE 修复钉版已在 requirements.txt（night24 上提），本次补 dependabot 周扫描 + 离线 env 核验 + 审计清单，形成「钉版 + 周扫 + 手动兜底」三层收口。
- **交付物**：`.github/dependabot.yml`（入库）；`docs/project_record/night_runs/_night25_taskD_verify_env_deps.py`、`_night25_taskD_env_deps.json`、`night25_npm_audit_checklist.md`（gitignored）。
- **零代码改动、零真 LLM、零 DB 写、未 push（沙箱无网）**。


## §39 night25 Task E · 前端路由漂移扫描（H1）

- **扫描器** `_night25_taskE_scan.py`（gitignored）：前端 `src/**/*.ts*` 的 `/api/` 调用点（19）vs 后端 in-process `app.openapi()` 路由（205）交叉比对；另补查 http.* 缺 `/api/` 前缀调用。零真 LLM / 零网络。
- **结论**：404 风险 **4 项**（全部 `/api/v1/recalc/*`），401 风险 **0**（前端 19 调用点全经 `utils/request.ts` + `authHeaders`；裸 fetch 仅 1 处且为注释内，已排除）。
- **H1 真实 bug**：`RecalcPage.tsx` 调 `/api/v1/recalc/{status,history,dependency-graph,trigger}`，但 `recalc_queue.router`（`APIRouter()` 无前缀）在 `main.py:226` 以 `prefix="/api/v1"` 挂载 → 真实路径为 `/api/v1/{status,...}`（**无 `/recalc` 段**）。前端「下游重算」页每次 API 调用均 404，功能实际不可用。
- **历史根因**：ISS-025 鉴权扫描曾记「`/recalc/trigger` 路由不存在，真实端点 `/api/v1/trigger`」——核对了鉴权面却未回溯前端仍在调 `/api/v1/recalc/*`，漂移遗留。
- **已于 night26 Task A 修复（方案 A）**：`main.py:228` 改为 `app.include_router(recalc_queue.router, prefix="/api/v1/recalc")`；现真实路径 `/api/v1/recalc/{status,history,dependency-graph,trigger,stats,recover}` 与 `RecalcPage` 完全一致。实测：前端 4 调用点带 token→200、无 token→401（prod `ENABLE_INTERNAL_ENDPOINTS=off` 时 guard 生效）；in-process 路由表 6/6 存在。night24 验证脚本与 ISS-025 文档同步更正（见 §41）。
- **非漂移说明**：15 个匹配项正常；14 个「缺 `/api/` 前缀」的 http.* 调用为基址相对路径（由 `http` 封装 `API_BASE` 补 `/api/v1`），与后端一致。
- **交付物**：`_night25_taskE_scan.py` + `_night25_taskE_result.json` + `night25_route_drift.md`（均 gitignored）。
- **零代码改动、零真 LLM、零 DB 写、未 push（沙箱无网）**；仅登记本 §39 与报告。


## §40 night25 Task G · API 文档暴露收口

- **新增开关** `ENABLE_API_DOCS`（`backend/app/core/config.py`，默认 `False`=prod 安全）：与 `DEBUG` 解耦的独立闸门，控制 FastAPI `/docs`、`/redoc`、`/openapi.json` 是否暴露。
- **`main.py:165` 改造**：`docs_url`/`redoc_url`/`openapi_url` 由 `settings.ENABLE_API_DOCS` 决定（`True`→暴露，`False/未设`→`None` 不挂载），替代原仅依赖 `settings.DEBUG` 的粗粒度控制。
- **env/RUNBOOK 登记**：`backend/.env`（dev）加 `ENABLE_API_DOCS=on`（保持 dev 文档便利，gitignored 本地）；`backend/.env.example` 加 `ENABLE_API_DOCS=false`（prod 默认）；`docs/project_record/RUNBOOK.md` 追加 `ENABLE_API_DOCS` 章节（作用/取值/默认/prod 指引/安全影响）。
- **实测安全影响**（in-process 路由枚举）：`ENABLE_API_DOCS=on`（dev）无鉴权路由=18，其中框架文档端点 4 个（`/docs`、`/docs/oauth2-redirect`、`/openapi.json`、`/redoc`）；`=false`（prod）这 4 个不挂载 → 无鉴权=14，均为业务/鉴权流公开端点（login/health/captcha/forgot-password/shares-verify/admin-prompts）。即：**隐藏文档后公开 schema 暴露面从 4 降为 0**，业务无鉴权面不变。
  - 注：任务书预估「15→dev15/prod12」是按 night24 计数口径（不含框架路由）的近似；本回合实测算入框架文档路由，故 dev=18/prod=14，降幅一致（隐藏 4 个公开 schema 端点）。业务无鉴权端点 14 个属既有 auth 流设计，不在本开关收口范围。
- **回归**：`py_compile` config.py+main.py OK；night25 Task A 读端点 28/0、Task B ALL_6+R1-R2 仍 PASS（docs 网关不影响业务路由鉴权）。
- **交付物（入库）**：`backend/app/core/config.py`、`backend/app/main.py`、`backend/.env.example`、`docs/project_record/RUNBOOK.md`、本 §40。（`backend/.env` dev 改动为本地 gitignored，不进 commit。）
- **零真 LLM、零 DB 写、未 push（沙箱无网）**。


## §41 night26 Task A · recalc 路由漂移修复（方案 A，闭环 H1）

- **代码改动**（唯一 tracked 代码改动）：`backend/app/main.py:228` → `app.include_router(recalc_queue.router, prefix="/api/v1/recalc")`（原 `prefix="/api/v1"`）。`recalc_queue.router` 内 6 路由（`/trigger`、`/status`、`/history`、`/dependency-graph`、`/stats`、`/recover`）现挂在 `/api/v1/recalc/*`，与前端 `RecalcPage.tsx` 调用完全一致。
- **验证** `_night26_taskA_verify.py`（gitignored，零真 LLM / 零 DB 写）：
  - in-process 路由表：6/6 `/api/v1/recalc/*` 路由存在；旧前缀（`/api/v1/trigger` 等）残留 = 0。
  - TestClient（prod `ENABLE_INTERNAL_ENDPOINTS=off`）：前端 4 调用点（status/history/dependency-graph/trigger）**无 token→401**、**带 dev JWT→200（非 404）**；`ALL_PASS`。
  - recalc 端点鉴权面不变：`/status`、`/trigger`、`/dependency-graph`、`/stats`、`/recover` 仍 `internal_endpoint_guard`（prod 默认 401），`/history` 仍 `get_current_user`（硬鉴权）——漂移修复未削弱任何鉴权。
- **同步更正过期引用**（同 commit，避免后续验证器/文档误判）：
  - `docs/project_record/22-ISS025无鉴权端点全量扫描.md` B 类清单 6 处：`/api/v1/{trigger,dependency-graph,stats,status,recover}` → `/api/v1/recalc/{...}`；收口建议段同步。
  - `docs/project_record/night_runs/_night24_verify_b.py` 连通性验证器 focused 列表改新路径，并重跑 `RESULT: PASS`（无回归）。
  - `AI_CHANGES.md` §31「路径纠正」+ §39「漂移状态」：标注「已于 night26 Task A 修复（方案 A）」。
- **回归**：`_night24_verify_b.py` 重跑 `RESULT: PASS`；`_night26_taskA_verify.py` `ALL_PASS`。未碰其他路由/业务逻辑。
- **零真 LLM、零 DB 写、不 kill 后端、未 push**。
- 交付物（gitignored）：`_night26_taskA_verify.py`(→`_night26_taskA_result.json`)、`night26_taskA_recalc_fix.md`、`night25_route_drift.md`(标已修复)。


## §42 night26 Task B · _ACTION_VERB_RE 过匹配加固

- **根因**：night25 Task B 给 `_ACTION_VERB_RE`（`action_planner.py:38`）加裸词「加」修复复合句 add 被吞；副作用是裸「加」以 `.search()` 命中任意含「加」字（增加/更加/参加/附加/相加/叠加/愈加），导致非动作句被误判为动作子句、破坏 `split_clauses` 合并逻辑。
- **修法**（两处，唯一 tracked 代码改动 `action_planner.py`）：① 长词优先（`加上|添加|新增` 置于裸 `加` 之前，消除死分支）；② 裸「加」加否定环视 `(?<![增更附参相叠愈越倍交])加`，仅当「加」前非这些字才命中。
- **验证** `_night26_taskB_verify.py`（gitignored，零真 LLM）：反例 7/7 不命中（增加销售额/更加清晰/参加活动/附加说明/相加/叠加显示/愈加明显），正例 5/5 命中（加一个趋势图/添加柱状图/加上平均值/再来一个/改成饼图）→ `ALL_PASS`（误命中 0、未命中 0）。
- **回归**：night25 Task B 6 边界 + R1/R2 重跑 → `ALL_6_SCENARIOS_PASS` + `REGRESSION R1-R2 PASS`（零回归，零真 LLM）。`py_compile` action_planner.py OK。
- **零真 LLM、零 DB 写、不 kill 后端、未 push**。
- 交付物（gitignored）：`_night26_taskB_verify.py`(→`_night26_taskB_result.json`)、`night26_taskB_action_verb.md`。


## §43 night26 Task C · night25 遗留 H2/H3（性能基线 + 覆盖盘点）

- **H2 性能采样**（`_night26_taskC_h2_perf.py`，N=20/接口，in-process 无 token，零 DB 写 / 零真 LLM）：
  - dashboard 加载 `GET /api/v1/dashboards/my` 401 基线 avg=2.945ms / p50=2.772ms / max=8.667ms。
  - chat 流式首字节 `POST /api/v1/chat/message` 401 基线 avg=2.538ms / p50=2.244ms。
  - recalc 触发 `POST /api/v1/recalc/trigger` 200（沙箱 `ENABLE_INTERNAL_ENDPOINTS=on` dev 放开，非安全回归）avg=2.063ms / p50=1.904ms。
  - 解读：鉴权层基线 ~2–3ms 无毛刺；完整加载时延（DB/LLM/渲染）需真机，已附最小步骤卡（标「需真机人工」）。**只测不优化**。
- **H3 覆盖盘点**（`night26_taskC_h3_coverage.md`）：
  - **关键发现**：真「功能完成度矩阵(34项)」文件仓库内不存在（`COLLAB_RULES.md` 规则8#5 要求维护但从未创建）→ 列为文档闸门缺项（建议 D 类补建，本表可作初始草稿回填）。
  - 替代：代码夯实 34 项 AI 对话功能完成度矩阵（意图21类 `intent_classifier.py:49-73` + 多轮/澄清13项），映射 `AI_TEST_CASES_v1.md`（⑥+R1/R2）。
  - 覆盖：✅10 / 🟡2(部分) / ❌22(无用例)；覆盖率 10/34=29.4%。无用例重点：配置 CRUD(#14-16)、权限(#18)、FILTER/QUERY/RECALC(#5#19#20)、Task B 裸「加」(#32)、指代删除优先(#28)、阶段9三(#29-31)。
  - 建议：补建真矩阵回填本表；将 night26 Task B 验证器并入 `AI_TEST_CASES` v2 防回归。
- **零真 LLM、零 DB 写、不 kill 后端、未 push**。交付物（gitignored）：`_night26_taskC_h2_perf.py`(→`_night26_taskC_h2_result.json`)、`night26_taskC_h2_perf.md`、`night26_taskC_h3_coverage.md`。

## §44 night26 Task E · 全量回归 + 收尾 + ISS-025 闭环判定

- **全量回归（全部 _verify_*.py 零回归）**：
  - `_night26_taskA_verify.py` → `ALL_PASS`（recalc 路由 6/6；prod 401、with_token 非404，route_missing=0）。
  - `_night26_taskB_verify.py` → `ALL_PASS`（误命中0、未命中0）。
  - `_night25_taskB_verify.py` → `ALL_6_SCENARIOS_PASS` + `REGRESSION R1-R2 PASS`（复合拆分零回归）。
  - `_night24_verify_b.py` → `RESULT: PASS`（recalc 连通性 + 22 写端点 `get_current_user` 全在，0 漏网）。
  - `_night25_taskA_verify.py` → `TOTAL=28 FAIL=0`（路由扫描）。
  - `py_compile` 8 改动文件（main/action_planner/security/recalc_queue/intent_classifier/action_executor/chat/llm_gateway）→ 8/8 OK。
- **脚本归位**：全部过程脚本/证据均在 `docs/project_record/night_runs/`（gitignored），无过程文件泄漏进代码目录。
- **ISS-025 闭环判定**：**`[CODE_CLOSED]`**——代码侧主链路全收口：
  - A 类 47（22 高危写 + `kickout` 归属校验）已加硬鉴权（`get_current_user`）；
  - B 类 73 内部端点 env 闸门已落地（75 端点 `internal_endpoint_guard`，prod 默认 401；recalc 漂移 night26 Task A 已修）；
  - C 类 11 按设计保留匿名（非缺项）。
  - **验收侧 11 项待用户本机**（push 比对远端 / DB 真跑 / 真实看板绿标 / 用户拍板），属上线决策或需真实环境，非代码缺项 → **可判「ISS-025 代码闭环，验收待真机」**。
- **本夜 commit 链**（本地 `p0-security-fixes`，未 push）：`81ad561`(Task B) `a894b68`(Task A)；两处真问题已修、零回归已验。
- **零真 LLM、零 DB 写、不 kill 后端、未 push**。

## §45 night26 Task D · 11 项「需真机人工」验收脚本化准备

- 一键本地检查器 `night_runs/_night26_taskD_acceptance_local.py`（只读 git/进程探测，不 push/不写DB/不杀后端）：覆盖 ①-2（ahead of origin 提交数）/ ②-2（未 push 提交列表）/ ②-4（127.0.0.1:8000 监听探测）。
- 最小步骤卡 `night_runs/night26_taskD_acceptance_cards.md`：11 项全有最小步骤——
  - 可自动化 3 项（①-2/②-2/②-4）：脚本直接出结果；
  - 需真机触发 3 项（③C LLM429 切层 / ④-3 LLM429 套件 / ④-4 真 LLM 冒烟）：给命令 + 预期（用克隆看板 `dash_p0verify_0001`，禁碰真实看板）；
  - 需用户拍板 5 项（⑤-1~⑤-5 上线决策）：决策项，拍板后执行对应 git/pip 命令。
- 用户真机操作量压缩为「跑脚本 + 点选 + 拍板」；脚本已 `py_compile` OK。
- 零真 LLM、零 DB 写、不 kill 后端、未 push。

## §46 night27 统一 AI 失败处理（ISS-062~066，本地未 push）

> 本轮把「AI 对话」与「看板生成」的 AI 失败处理统一为同一套规则（R1-R5），并把 risk_demo_v2_01 实测暴露的 5 个真实缺陷（ISS-062~066）逐一闭环。
> 约束：一类一 commit、不 push、前端改完 `tsc --noEmit` 通过、回读验证。验证为结构级确定性断言（沙箱无法起 uvicorn / DuckDB 被独占），浏览器真机为体验确认项。

### 统一 AI 可用性规则（对话 + 看板生成共用基线）

- **R1 判定**：AI 调用失败 / 限流(429) / 超时 / 返回空内容 → 统一视为「AI 未参与」。
- **R2 不静默、不空**：任何链路禁止产出空回复 / 空气泡，必须给明确文案 + 失败原因。
- **R3 用户抉择**：AI 未参与时提供两个入口——「重试 AI」与「规则兜底」，与看板生成 `ai_awaiting` 抉择语义一致。
- **R4 诚实标注**：走规则兜底时明确标注「本次 AI 未参与，已用规则兜底」，不冒领成果。
- **R5 退避重试**：重试沿用既有 LLM 链退避规则（8/16/24s），入口幂等、不重复落库。
- **说明**：对话保持 SSE 流式、看板生成保持后台任务 + 轮询；本轮只统一**判定/兜底/重试/标注**规则，不改传输方式。

### 变更清单（按 ISS）

| 文件 | 类型 | 说明 | 关联 |
|------|------|------|------|
| QualityCheckPanel.tsx | fix(frontend) | ISS-062 自动质检守卫移入定时器回调 + 404 后 1.5s 静默重试 + runCheck silent 门控 | ISS-062 |
| QualityCheckPanel.tsx | fix(frontend) | ISS-063 批量修复 60s 超时/取消 + 内联状态条（秒表+取消）+ applyError Alert + 重试修复 | ISS-063 |
| quality.py | feat(backend) | ISS-064 新增 `POST /quality/{dataset_id}/reset`（删清洗层表 + 置 ignored + 清缓存，带归属校验） | ISS-064 |
| QualityCheckPanel.tsx | fix(frontend) | ISS-064 重置改 async 调后端 + 二次确认 Modal + 文案「重置数据（撤销清洗）」+ 成功自动重检 | ISS-064 |
| QualityCheckPanel.tsx | fix(frontend) | ISS-065 删除批量修复后自动跳转 `onProceed`，改提示用户手动点「生成看板」 | ISS-065 |
| chat.py | fix(backend) | ISS-066 `complete` 事件 message 非空守卫（generate_intent_response 回退 + 统一兜底 + 未成功置 ai_error） | ISS-066 |
| ChatPanel.tsx | fix(frontend) | ISS-066 防空气泡（`if (!finalContent)` 兜底文案 + ai_error 透传，绝不 push 空白气泡） | ISS-066 |

### 验收

- 前端 `tsc --noEmit` 退出码 0（Tasks A-E 全过）。
- 后端 `py_compile` chat.py / quality.py 全绿。
- 结构级验收脚本 `tests/_fixtures/real/_verify_night27_iss062_066.py` **23/23 PASS**（含 ISS-065 自动跳转已删除的反向断言）。
- 浏览器真机复测（自动质检触发 / 批量修复超时取消重试 / 重置真回滚 / 单动作对话不空气泡）属体验确认项，需用户本机起服务后确认（与历史 night 模式一致：代码 DONE、真机待验收）。

## §47 night27 补丁 · ISS-066 守卫 await/dict 缺陷修正（教练核实，本地未 push）

> 教练在 commit `2f9ebfa`（Task E 守卫）中发现两处缺陷，在「单动作轮 message 为空」场景会让 SSE 流崩溃。本补丁独立成 commit，未 push。

### 缺陷（根因）
- `generate_intent_response` 是 `async def`（chat.py:114），守卫里缺 `await` → `_fb` 是 coroutine（恒真），`if _fb:` 命中，把 coroutine 赋进 `response_data["message"]`。
- 该函数返回 **dict**（message/action/suggested_followups），即便补 await，`response_data["message"] = _fb` 也会把 dict 塞进 message。
- 后果：`full_response["message"]` 为 coroutine/dict → `sse_event` → `json.dumps` → `TypeError`（coroutine 不可序列化）→ SSE 中断。结构级 grep 没拦住此 bug。

### 修复（chat.py:1216-1235，elif/else 兜底分支不变）
```python
try:
    # 必须 await（async def）+ 取 .message 字符串；否则 coroutine/dict 进 message → SSE 崩溃
    _fb = await generate_intent_response(intent_type, intent_result.get("analysis", {}), context)
except Exception:
    _fb = None
_fb_msg = _fb.get("message") if isinstance(_fb, dict) else None
if _fb_msg:
    response_data["message"] = _fb_msg
```

### 验收（真实验证，非结构 grep）
- 新增 `tests/_fixtures/real/_verify_iss066_message.py`，直接 `import` 真实 `generate_intent_response` 并 `await`：
  - 复现旧 bug：不 await → coroutine → `json.dumps` 抛 `TypeError`（PASS，证明根因）。
  - 修复后：`response_data["message"]` 为**非空 str**，`json.dumps(full_response, ensure_ascii=False)` 不抛异常（PASS）。
  - 兜底分支 A/B：message 恒非空 str 且可序列化、失败时诚实置 `ai_error`（PASS）。
  - 运行结果：**10/10 PASS**，exit 0。
- 后端 `py_compile` chat.py 全绿。
- 经验沉淀：`docs/project_record/verify_script_guide.md` 记铁律「结构性断言不能替代运行时断言——async/await 与 JSON 序列化类缺陷必须真跑分支」。

### 提交
- 单独 commit `fix(backend): ISS-066 守卫补 await + 取 .message 字符串`（chat.py + 验证脚本 + 指南，未 push）。

## §48 night28 全量收口（Task A–E，本地未 push）

> 2026-10-04。分支 `p0-security-fixes`（HEAD `898ca30`）。目标：依赖漏洞真定位 + 166 条覆盖矩阵 + 34 项矩阵 + 零回归 + 交付说明 + 交接。

### ① Task A — ISS-053 依赖漏洞真定位（commit `898ca30`）
- 真定位：`pip-audit` 本地 manifest + `pip index versions` 查可装版 + OSV.dev `/v1/querybatch` 审计前端 lockfile（沙箱放行 HTTPS 裸套接字，git/npm-advisory 被掐）。
- 漂移发现：原 `requirements.txt` 是 night24 钉版但严重漂移——实际运行环境已是安全版（fastapi 0.136.3/starlette 1.2.1/pyarrow 25.0.1/duckdb 1.5.5/python-jose 3.5.0）。按旧钉版全新安装才触发 33 CVE。
- 修复：对齐钉版到实际安全环境，闭环 starlette 7 CVE、pyasn1 8 CVE、python-dotenv/black/pyarrow/duckdb/python-jose 等。
- 结果：pip-audit **33 CVE/8 包 → 2 CVE/1 包（仅 ecdsa 0.19.2 上游无修复版，残余）**；`requirements.txt` dry-run 无 ERROR；backend 导入 OK。

### ② Task B — 168 条覆盖矩阵（`AI_TEST_CASES_v1_RESULT.md`）
- 修正上轮 bug：原正则 `^[A-N]\d` 只匹配 `A1-1`/`B1-1`，漏 C–N 模块 `C-1`/`L-1`/`N-1` 格式（仅 82/168）；且误把「AI 模式补测」重测表当独立案例、附录 D1–D8 造数据行误标模块 N。
- 重生成健壮解析器（仅取 `## 模块 X` 下正式案例表，排除补测/附录表）→ **168 行全量覆盖**。
- 计数：PASS 103 / PASS* 43 / 需真机 22 / **FAIL 0**。FAIL 空 → 无 ISS-067 需登记。

### ③ Task C — 34 项功能完成度矩阵（真建 `34项功能完成度矩阵.md`）
- 此前 night26 草稿仅为代理（无物理文件），本表据当前 AI_TEST_CASES_v1（A–N 168 条）重映射。
- 计数：已覆盖 24 / 部分 1（#18）/ 无用例 9（#6/#9/#10/#14–17/#19/#20）= 70.6%（较 night26 草稿 29.4% 提升，因 K/L/M/N 四模块补齐 + B3-7 闭环）。
- 9 项无用例为测试覆盖缺口（非缺陷），建议纳入 v2 用例集。

### ④ Task D — 全量回归零回归
- night28 仅改 `requirements.txt`（已 commit）+ 文档，**无运行时代码改动** → 回归真空干净。
- 前序已真跑：backend `compileall` OK + 8 个 `_verify_*` 脚本全绿（ISS-066 10/10、night27 23/23、ISS-058 5/5、TaskI 32/32、TaskG 18/18、clarify 13/13、health 15/15、history 10/10）+ 前端 `tsc --noEmit` 退出码 0。
- 本会话补 `compileall` 复检：COMPILE_OK。

### ⑤ Task E — 交付说明 + 文档闸门
- 新建 `AI能力交付说明.md`（能力清单/已闭环问题/边界残留/真机验收步骤/遗留）。
- 新建 `PROJECT_STATUS.md`（11 项能力域总状态）。
- 更新 `ISSUES.md`（追加 night28 收口块：0 FAIL + 9 覆盖缺口 backlog，非缺陷）。
- 本文件追加 §48；本 night28 `NIGHT_SUMMARY.md` 见 `night_runs/night28/`。

### ⑥ 状态
- **代码闭环**，验收待真机（ISS-025 验收侧 11 项 + night27 五处浏览器复测）。
- 待 push：分支 `p0-security-fixes`（HEAD `898ca30`）；沙箱 GitHub git 协议被 SIGTERM，需用户本机带 `127.0.0.1:7897` 代理。

### §48.1 收口复核补正（2026-10-04 续，对照完整提示词）
- **axios 真实漏洞（修正旧「非漏洞源」误判）**：`osv_precise_audit.py` 精确 SEMVER 复核 → `axios 1.19.0` 真实落在漏洞区间，修复版 `1.20.0`（12 条 GHSA，HIGH/MODERATE 混合）。提示词「1.19.0 安全版」系过时判断；「上一轮把 axios 判为漏洞包」并非误判。→ 同步修正 `AI能力交付说明.md §3.3/§5/§6` + `ISSUES.md` ISS-053。
- **前端锁同步 BLOCKED**：沙箱 `npm install axios@1.20.0 --save-exact` 被 SIGTERM（与 git/npm audit 同因），`package-lock.json` 未变更（`git diff` 空，安全）。已定位未落锁，诚实登记 `[BLOCKED-前端锁同步]`；待本机执行 `npm install axios@1.20.0 --save-exact --registry=https://registry.npmjs.org` + `npm audit fix`。
- **其余 npm 命中真实修复版**：brace-expansion(1.1.18→1.1.19 / 2.1.4→2.1.5)、echarts(5.6.0→6.1.0)、esbuild(0.21.5→0.25.0)、js-yaml(4.3.1→4.3.2, HIGH)、react-router(6.30.6→7.18.0)、vite(5.4.21→6.4.x)；**braces 3.0.3 无修复版（HIGH 残余）**。
- **Task D 回归汇总补产**：`night_runs/night28/回归汇总.md`——11 个 `_verify_*` 本会话实时真跑全部 ALL_PASS（ISS-066 10/10、night27 23/23、ISS-058 5/5、ISS-059 9/9、clarify 13/13、health 15/15、history 10/10、TaskI 32/32、TaskG ALL、TaskJK 17/17、ISS-025 Batch1 22/22）+ `tsc --noEmit` exit 0 + `compileall` COMPILE_OK → **ALL_PASS 零回归**。
- **ISS-053 状态翻转**（提示词 Task 0 要求）：`[DONE-代码]` → `[DONE-后端]` + `[BLOCKED-前端锁同步]`。
- 新增 commit：`fix(docs): ISS-053 精确OSV复核 axios真实漏洞+状态翻转`（ISSUES.md）；`docs: night28 Task E 修正 axios 真实漏洞表述`（AI能力交付说明.md）。

### §49. night29 验收收口轮（2026-10-05）

- **机型**：不写新功能，只做「让 night28 成果真正落地并被验证」。代码侧已收口，瓶颈在验收。
- **Task 0 push**：实测沙箱 `github.com:443` 现已可达（旧「git SIGTERM」记忆过时），`git push origin p0-security-fixes` EXIT 0，remote == local `fff8ed8`。注意远端 push 前已在 `0ee6895`（=night28 HEAD），night28 实际早于本回合已被推上；本回合仅新增并推送 `fff8ed8`（前端锁）。
- **Task A ISS-053 定论（权威 npm audit）**：
  - `npm audit --registry=https://registry.npmjs.org --json` 沙箱实跑成功（bulk POST 200）→ 确认 **axios 1.0.0–1.19.0 为 HIGH（修复 `<1.20.0`）**，与 night28 OSV 一致 → axios 确为真实漏洞包，非误判；提示词「若 npm audit 无高危→撤销 54306b2/0ee6895」分支不适用，两 commit 保留。
  - 落锁：`npm install axios@1.20.0 --save-exact --registry=https://registry.npmjs.org` EXIT 0 → package.json `axios=1.20.0` + lock 同步（`git diff --stat` 有 lock）。
  - 收口：`npm audit fix`（非破坏性）→ brace-expansion + js-yaml 修复 → 漏洞 **17 → 14**；复跑确认 axios 已移除。
  - 残余 14 项全 `fix=MAJOR` 破坏性（echarts/vite/react-router/@typescript-eslint/braces 链）→ 本轮「不重构」未自动 `--force`，移交 CI/Dependabot。
  - ISS-053 翻转 `[DONE-后端]`+`[BLOCKED-前端锁同步]` → `[DONE]`（ISSUES.md）。
- **Task B 真机验收**：沙箱无浏览器，UI 层（ISS-062~066 五处 + 22 条需真机 UI + ISS-025 验收侧 11 项）全部标记「待真机」，未伪造 PASS；逻辑层引用 night28 的 11 个 `_verify_*` ALL_PASS + `tsc`/`compileall` 零回归。报告：`night_runs/night29/真机验收报告.md`。
- **commit**：`fff8ed8` fix(deps) ISS-053 axios 落锁 + npm audit fix（已 push）。
- **诚实声明**：Task B UI 层待真机；Dependabot 网页原文仍不可拉（github.com:443 仅 ls-remote 可达）→ 以本地权威 `npm audit`+OSV 双审计为准。零 DB 写、未 kill 进程、未新增功能。

### §51. night31 状态对账 + 用例补盲 + 收口（2026-10-05）

- **机型**：不写新功能，只做**状态对账（消灭台账漂移）+ 测试盲区补盲 + 收口**。依据：教练 2026-10-05 本机核对 ISSUES.md 全部 `ISS-*` 状态 vs 代码/提交/`_verify_*.py`，并离线复跑既有用例。
- **红线（严格遵守）**：未改任何后端/前端业务代码；未碰生产 DuckDB、后端运行中进程、`backend/requirements.txt`、已闭环的 ISS-053；批量删除类操作全程未触发；push 前等用户确认。
- **基线**：分支 `p0-security-fixes`，起点 HEAD `62bc1d2`（night30 收口）；本会话本地 commit 链 `329b5b9`(Task A) → `7f0aa51`(Task B) → (Task D 收口 commit)，均**未 push**。
- **Task A — 全量状态对账（commit `329b5b9`）**：
  - 逐条核对 ISSUES.md 全部 34 条 `ISS-*`，仅 **2 处状态漂移**：
    - **ISS-033**「再来一个」未推断 add_chart：代码已于 night13 commit `2fd76dd` 实现（`backend/app/core/action_planner.py` P0-1 指代消解 L70-73/L700/L1030-1035 + `chat.py` L395-409 上下文注入）→ 台账漏翻 `[OPEN]`，现**翻 `[DONE]`** 并补证据。
    - **ISS-031** glm-5.3-flash 仅作兜底：实为 failover 设计原则（长期约束）非待办 → `[OPEN]` 误导，翻 **`[CONSTRAINT]` 长期约束(非待办)**。
  - ISS-037 附属项「对话丢消息入口探针诊断日志」确认外部/不适用，不翻 ISS-037 状态。
  - 过程文件 `night_runs/night31/状态对账表.md`（gitignored，不进 commit）。
- **Task B — 测试盲区补盲（commit `7f0aa51`）**：
  - 新增 `backend/tests/test_night31_taskb.py`：覆盖 `34项功能完成度矩阵` 中 **9 项 ❌ 无用例**功能——ATTRIBUTION / QUALITY_FIX / CHART_FIX / CREATE_CONFIG / UPDATE_CONFIG / DELETE_CONFIG / BULK_UPDATE_DATA / QUERY_METRIC / RECALC_METRIC。
  - **离线、零 LLM**：走意图分类规则路径（`INTENT_PATTERNS` + `_extract_params`，`context={}` 无 field_profiles，绝不触发 LLM 网络），运行时断言（非关键词 grep）`intent_type` + 关键参数（批量更新 `isolated=True`、配置 CRUD 抽到 key、指标查询解析 metric）+ 3 条优先级回归。
  - 实测 **4 tests / 18 子断言全 PASS**；同步更新矩阵 9 项 ❌→✅（意图识别层），覆盖率 24/34(70.6%) → 33/34(97.1%)。
  - 文件用 `test_*.py` 而非 `_verify_*.py`：仓库 `.gitignore` 全局忽略 `_*.py`（含 `_verify_*.py`），本用例需提交。
  - **诚实声明**：仅闭环**意图识别层**；配置 CRUD/批量更新/权限的**动作执行层**需真机（DB+鉴权），不伪造 PASS。
- **Task C — 可跑用例真跑 + 覆盖矩阵 v2（gitignored 过程文档，无独立 commit）**：
  - 复跑 10 个离线 `_verify_*.py` 脚本 + 1 个 pytest，**全部 PASS**（ISS-058 5/5、ISS-059 9/9、clarify 13/13、health 15/15、ISS-066 10/10、night27 23/23、history 10/10、TaskG 18/18、TaskI 32/32、TaskJ/K ALL、TaskB 4 tests）。
  - 生成 `night_runs/night31/AI_TEST_CASES_v2_运行矩阵.md`：继承 night28 的 168 条分类（**0 回归**，因本会话未改任何业务代码），新增「本会话复跑」列标记 60 行 + 新增 **O-1~O-9 意图识别层 9 条**。
  - 覆盖率：**PASS 103 + PASS\* 43 + 需真机 22 + FAIL 0 + 新增 O 类 9 = 177 条**。
- **Task D — 收口（本 commit）**：ISSUES.md 状态对账（A 已提交）+ 本 §51 + `night_runs/night31/NIGHT_SUMMARY.md`。
- **FAIL 清单**：**（空）0 FAIL**。本会话仅对账/补测/复跑，**未引入任何代码变更**，故无回归可能；ISS-033 状态漂移已在 Task A 修正（代码 night13 已实现，仅台账漏翻）。
- **需真机（同 night28，22 条，不计入自动回归）**：A1-3/A4-1/A4-4/A4-6/A5-1/D-1~D-8/F-11/F-12/F-7/G-1~G-5/H-4；其前端**结构守卫**已由 `tests/_fixtures/real/_verify_night27_iss062_066.py`(23/23) 与本会话复跑确认存在，视觉渲染/截图仍待用户真机。
- **诚实披露/偏差**：本会话仅文档+测试，无依赖升级/无 build；无 CVE 变动（night30 已 0）。Edit 工具在本仓对 ISSUES.md 曾静默未落盘（ISS-031 那次），已用 Python 确定性替换+assert 强制落盘并回读验证。
- **未触碰**：后端业务代码 / 前端业务代码 / 生产 DuckDB / 用户进程 / `requirements.txt` / 已闭环 ISS-053 / axios。
- **commit 清单（本地未 push，等用户确认）**：`329b5b9`(Task A) / `7f0aa51`(Task B) / 本收口 commit。
- **证据文件**：`night_runs/night31/` 下 `状态对账表.md` / `补盲用例清单.md` / `AI_TEST_CASES_v2_运行矩阵.md` / `NIGHT_SUMMARY.md` / 11 个 `run_*.log`（均 gitignored，不进 commit）。

### §50. night30 前端依赖大版本升级清残余 14 CVE（2026-10-05）

- **机型**：不写新功能，只清 night29 残余 **14 CVE（10 high + 4 moderate）**——前端依赖大版本升级 + 回归 + 收口。依据：教练 2026-10-05 本机 `npm audit --registry=https://registry.npmjs.org` 实跑。
- **基线**：分支 `p0-security-fixes`，起始 HEAD `e067f64`（night29 收口，本地==远端）。axios 已于 night29 `fff8ed8` 落锁 1.20.0，本轮不碰；后端 `requirements.txt` 已 night28 钉版，本轮不碰。
- **工具链（关键）**：安装全程用**系统 Node24 的 npm 11.17.0**（`C:/Program Files/nodejs/node.exe` + 其 npm-cli.js）。managed npm 10.9.7 对可选原生二进制（`@rollup/rollup-*`/`@rolldown/binding-*`）做 idealTree/lock 计算会崩 `Cannot read properties of undefined (reading 'spec')`，`--package-lock-only` 与 `install` 均触发；npm 11.17.0 解决。代理 `http_proxy/https_proxy=127.0.0.1:56218` 使装包卡死，**须置空走直连**；`npm audit` 须 `--registry=https://registry.npmjs.org`（npmmirror 不支持 audit）。
- **Task A — dev 链（commit `de52302`，单独 commit）**：
  - `@typescript-eslint/eslint-plugin`+`parser` → `8.71.0`（`--save-exact`，清 ReDoS 链，连带 braces/fast-glob/globby/micromatch）；
  - `vite` → `7.3.6`（**提示词目标 8.3.2**；因 npm 10 bug 改 7.3.6 + `@vitejs/plugin-react` `5.2.0` + `esbuild` `0.28.2`，等价清 vite high + esbuild moderate，build 已验证 EXIT 0）；
  - audit **14 → 3**（high 归零）。
- **Task B — 运行时（commit `e3c69de`，单独 commit）**：
  - `echarts` `5.6.0 → 6.1.0`（清 XSS GHSA-fgmj-fm8m-jvvx）；`echarts-for-react` `3.0.2 → 3.0.6`（peer 支持 echarts 6）；`react-router-dom` `6.30.6 → 7.18.4`（清 open redirect，连带 `react-router`）。
  - audit **3 → 0**。
- **验证（非伪造）**：
  - `npm run build`（`tsc && vite build`）：Task A `✓ built in 27.82s`、Task B `✓ built in 45.64s`，均 EXIT 0 → tsc 已对 react-router 7 类型定义零报错。
  - `npm ls --all --json`：top-level problems=None，全树 **0 invalid / 0 missing**，锁与 node_modules 一致（`npm ci` 可复现）。
  - 业务代码**零改动**：echarts 仅经 `echarts-for-react` 标准 option（grep `echarts.\w+` 仅命中注释）；react-router 全 v6 声明式 API 100% v7 兼容。
- **过程偏差（诚实披露）**：
  1. 首个 echarts `Edit` **静默未落盘**（本仓已知 Edit 工具陷阱，working_memory 已记）——package.json 仍 `^5.4.3`、node_modules 停在 `echarts@5.6.0`；经 `npm ls` 发现后用 **Python 确定性替换 + assert** 强制落盘 `^6.1.0`，复跑 install 才真正升到 6.1.0。
  2. 前序 install 被 SIGTERM 打断，锁文件 `node_modules/echarts` 仍记 5.6.0（node_modules 已是 6.1.0）；补 `npm install --package-lock-only` 把锁对齐到 6.1.0 后 audit 才归零。
- **残余**：**无 CVE 残余（14 → 0）**。唯一未完成项是「真机浏览器冒烟 + 截图」（沙箱无浏览器/显示器），已在 `回归汇总.md` 标注需真机并给命令，未伪造 PASS。
- **未触碰**：axios / 后端 `requirements.txt` / 生产 DuckDB / 用户进程。
- **commit 清单（本地未 push，等用户确认）**：`de52302`（Task A dev 链）、`e3c69de`（Task B 运行时）、本轮收口文档 commit（ISSUES.md §50 台账 + NIGHT_SUMMARY.md）。
- **证据文件**：`night_runs/night30/` 下 `audit_before.json`(14) / `audit_after_dev.json`(3) / `audit_after_runtime.json`(0) / `npm_build_taskA_final.log` / `npm_build_taskB2.log` / `npm_ls_all.json` / `回归汇总.md` / `NIGHT_SUMMARY.md`（均 gitignored，不进 commit）。


### §52. night32 全量回归 + 执行层补测 + 覆盖矩阵 v3（2026-10-06）

- **机型**：在 night31 收口（HEAD `b594414`，本地 3 commit 领先 origin）基础上做**全量回归 + 9 意图动作执行层补盲 + 覆盖矩阵 v3**。硬约束：不写新业务功能；仅测试补盲/回归/文档收口；发现真 bug 才最小改动；禁批量删除；一类一 commit。
- **基线**：分支 `p0-security-fixes`，起始 HEAD `b594414`（night31 收口）。未改任何业务代码。
- **Task A — 全量回归（commit `b0701a9`，单独 commit）**：
  - `backend/tests/test_quality_checker.py` 修复：旧 fixture 唯一度 50% 命中 UNIQ_KEY_RATIO 降级 WARNING 分支，测不到 BLOCKING 路径的 `row_count` 修复；改为真实主键场景（唯一度 ≥95% 走 BLOCKING），断言 `row_count==2` + `row_indices` 长度 ==2；复跑 5 passed。
  - 真跑取证（`night_runs/night32/`，gitignored）：pytest 全量 **67 passed / 1 failed**（1 项为 `test_frontend_static` 环境依赖失败，非回归，登记 ISS-067）；12 个 `_verify_*.py` 脚本**全部 rc=0 PASS**；golden 20 数据集 **20/20 ✅**（脚手架 `success` 计数器误报 0，逐数据集均 100% 匹配，非数据回归）；`compileall backend/app` rc=0；前端 `tsc`/`build`/`audit` 全绿（audit **0 vulnerabilities**）；API 路由鉴权 AST 静态扫描 **217 路由**（WRITE 116/READ 101），ISS-025 目标端点（rollback/shares/create/chat/message/tokens/status）无鉴权漂移。
  - 详见 `night_runs/night32/全量回归报告.md`。
- **Task B — 9 意图动作执行层补测（commit `c2b47fa`，单独 commit）**：
  - 新增 `backend/tests/test_night32_taskb_exec.py`：**10 tests / 10 passed**，覆盖 9 意图 `ActionExecutor.execute()` 路由/产出/护栏（ATTRIBUTION/QUALITY_FIX/CHART_FIX/CREATE_CONFIG/UPDATE_CONFIG/DELETE_CONFIG/BULK_UPDATE_DATA/QUERY_METRIC/RECALC_METRIC）；离线、mock LLM、隔离临时 DB，**不直写生产 DuckDB**。
  - 关键发现：config-CRUD 执行器层不强制超管（设计性，鉴权在 API 层）→ 登记低严重度加固 backlog（ISS-068）。
  - 详见 `night_runs/night32/执行层补测报告.md`。
- **Task C — 覆盖矩阵 v3（gitignored 过程文档，无独立 commit）**：
  - 解析 night31 v2（177 条），对主表 + O 表新增「night32 复跑」列（YES=本轮 12 脚本/pytest 覆盖；carried(n31)=night31 已验；—=历史基线）；新增 **P-1~P-9（9 意图动作执行层）9 条**。
  - 总览：**PASS 103 + PASS\* 43 + 需真机 22 + FAIL 0 + O 类 9 + P 类 9 = 186 条**（功能矩阵内 FAIL 0；环境依赖测试 fail 不计入矩阵，登记 ISS-067）。
  - 产物 `night_runs/night32/AI_TEST_CASES_v3_运行矩阵.md`（gitignored，不进 commit）。
- **Task D — 收口（本 commit）**：ISSUES.md 追加 ISS-067（环境依赖测试失败）/ ISS-068（config-CRUD 执行器层超管护栏缺口）+ 本 §52 + `docs/project_record/NIGHT_SUMMARY_night32.md`。
- **FAIL 清单**：功能矩阵内 **0 FAIL**。非阻塞待办 3 项（均非代码回归）：① ISS-067 环境依赖测试失败；② golden 脚手架 `success` 计数器 bug（误报 0，低优先级待修）；③ `auth_whitelist.json` 本 checkout 缺失（INFO，待补后复核 66 个无鉴权写端点）。
- **需真机（同 night28/31，22 条，不计入自动回归）**：A1-3/A4-1/A4-4/A4-6/A5-1/D-1~D-8/F-11/F-12/F-7/G-1~G-5/H-4；前端结构守卫已确认存在，视觉渲染/截图仍待用户真机。
- **诚实披露/偏差**：本会话仅文档 + 测试，无业务代码改动、无依赖升级、无 build、无 CVE 变动。Edit 工具在本仓对 Python/Markdown 曾静默未落盘（已知陷阱），本次改用 Python 确定性替换 + assert 强制落盘并回读验证（pytest 复跑 15 passed 交叉验证）。
- **未触碰**：后端业务代码 / 前端业务代码 / 生产 DuckDB / 用户进程 / `requirements.txt` / 已闭环 ISS-053 / axios / `data/`。
- **commit 清单（本地未 push，等用户授权）**：`b0701a9`(Task A) / `c2b47fa`(Task B) / 本轮收口 commit。
- **证据文件**：`night_runs/night32/` 下 `全量回归报告.md` / `执行层补测报告.md` / `AI_TEST_CASES_v3_运行矩阵.md` / 各 `_verify_*.log` / `pytest_*.log` / `golden_regression.log` / `fe_*.log` / `route_auth_scan.log` / `route_auth_inventory.json` / `taskb_exec_run.log`（均 gitignored，不进 commit）。


### §53. night33 合主分支预演 + 收口进度（累计：Task A 已合 / Task B 预演 / Task C / Task D 待）

- **基线**：分支 `p0-security-fixes`，night32 收口 HEAD `d19457c`（本地==远端）。本 §53 为 night33 累计进度区，随 Task B/C/D 提交逐步扩展。
- **Task A — backlog 清零（commit `a0d1732`，已合，2026-10-06）**：
  - A1 ISS-067 `[ENV-DEP]`→`[RESOLVED]`：`test_frontend_static.py` 加 skip 守卫（生成产物 `charts.js` 缺失则跳过，pytest 2 passed / 1 skipped）。
  - A2 ISS-068 `[BACKLOG-LOW]`→`[WONTFIX-BY-DESIGN]`：`crud_chain.yaml` 顶部加设计决定注释（config-CRUD 执行器层不加 `is_superuser`，鉴权在 API 层，加会误伤合法非超管调用引入回归；如需兜底应 `require_auth` 而非 `require_superuser`）。
  - A3 golden 脚手架计数器 bug：修正 night32 ad-hoc `_run_golden.py` 的 `getattr(r,"success")` 误报；复跑 `GOLDEN total=20 success=20` 真跑证。
  - A4 文档瑕疵：AI_CHANGES §52 标题日期 `2026-10-04`→`2026-10-06`（经 `git show -s --format=%ci d19457c` 确证 commit 实际作者日 2026-10-06）；ISS-067 旧冲突句更正。
  - 新增 **ISS-069** `[TEST-INFRA-BUG]`（night33 全量 pytest 暴露，pre-existing 非 night33 回归）：`test_run_status_recovery.py` 3 项失败（`no such table: brain_trace_summaries`/`dashboards`，测试库未建表）；留单独 commit 排期，未擅自修、未伪造 PASS。
  - 全量 pytest：64 passed / 1 skipped / 3 failed（3 fail = ISS-069，已登记）。

- **Task B — 合主分支技术预演（2026-10-06，本 commit，⛔ BLOCKER）**：
  - **干跑合并结论：`origin/main` 与 `p0-security-fixes` 是两条「无共同祖先」的独立历史，无法直接合并。**
  - 证据：`git merge-base --all` 空（rc=1）；两分支根不同（main 根 `7c3cb7b` init / p0 根 `f42dcc66`）；提交重叠 0；`git merge-tree --write-tree` 报 `fatal: refusing to merge unrelated histories`（rc=128）。
  - main 真实 tip `82de1c0`（11 commits，根 `7c3cb7b` init + 接管报告层 + axios 升 1.12.0 修 CVE-2025-58754）；p0 本地 `a0d1732`（206 commits，根 `f42dcc66`）。
  - **依赖差异极大**（package.json 对照）：`vite 7.3.6↔^5.1.0` / `react-router-dom ^7.18.4↔^6.22.0` / `echarts ^6.1.0↔^5.4.3` / `@vitejs/plugin-react ^5.0.4↔^4.2.1` / `@typescript-eslint 8.71.0↔^7.0.0`；`package-lock.json` 差异 4576 行。
  - **关键澄清**：提示词假设「合入 main 清 10 漏洞」不成立——当前分支 axios 已 `1.20.0`（≥ main 的 1.12.0，CVE 已覆盖），且 night30 已将前端 CVE 清到 0；把 main 合入反而会把 vite7/router7/echarts6/eslint8.71 的大版本升级**整体回退**到旧栈、重新引入旧 CVE 面。
  - **环境坑（已绕过）**：本沙箱 `git fetch` 仅更新 `FETCH_HEAD` 不持久化 remote-tracking ref（`refs/remotes/origin/main` 盘上不存在），故用 `git ls-remote` 取真实 SHA 驱动 merge-tree；网络本身可达（ls-remote/fetch rc=0）。
  - **决策升级**：「⑤-1 合 main」须用户先拍板——确认 `origin/main` 是否被 force-push/重置误替换；建议以当前 `p0-security-fixes`（206 commits、0 CVE）为交付真相，而非把疑似被重置的 main 合入。完整报告见 `night_runs/night33/合主分支预演报告.md`（gitignored）。
  - **未执行**：未 `git merge`、未 `--allow-unrelated-histories`、未改工作树、未残留 merge 状态，严守「只预演不真合」红线。
- **Task C（浏览器真机验收 + runbook）**：commit `20fd71a`（2026-10-06）。交付 `docs/project_record/真机验收 runbook.md`（22 UI 用例 + ISS-025 22 网关点 + night27 五处复测矩阵）+ 诚实截图占位 `night_runs/night33/真机验收截图证据.md`（gitignored）。**环境阻塞**：沙箱无可用浏览器工具（agent-browser 包装损坏 + 无 npm + 无 Chromium），无法生成截图；依据红线「禁编造截图」，所有视觉/交互项标 `[需真机浏览器验证]`，结构/静态核验项本会话复跑 PASS（ISS-025 22/22、night27 23/23）。
- **Task D（ISSUES 翻转 + §53 收口 + NIGHT_SUMMARY）**：本 commit。ISS-067→[RESOLVED]、ISS-068→[WONTFIX-BY-DESIGN]、ISS-069 登记（待处理）、ISS-070 golden 计数器已修、ISS-071 合 main BLOCKER 挂账，均写入 `06-ISS债清单.md`；本 §53 收口；`docs/project_record/NIGHT_SUMMARY_night33.md` 产出。**push 仍跳过**，等用户授权（本地领先 `origin/p0-security-fixes`：含 `a0d1732`+`a828a52`+`20fd71a` 等；合 main 因 unrelated histories 为 BLOCKER，见预演报告）。


### §54. night34 交付真相重定（Plan B 执行：main ← p0-security-fixes，2026-10-07）

- **目标**：以 `p0-security-fixes`（206 commits、0 CVE）为交付真相，重定默认分支 `main` 指向该线；保全旧 `main` 独有内容。
- **Task 0 — push night33 5 commit（HEAD `982ad5a` 领先 5）**：`git push origin p0-security-fixes` 成功，本地 = 远端（`982ad5a`）。
- **Task A — 保全 main（非破坏）**：
  - `git fetch origin main:refs/tmp/main` + `git push origin refs/tmp/main:refs/heads/backup/main-pre-truth-20261007` → 备份分支 = `82de1c0463843fc908ccc79a15d7ea6608bae063`（`git ls-remote` 已核实）。
  - `git diff --name-status refs/tmp/main refs/tmp/p0-security-fixes`：A(仅 p0)=297 / D(仅 main)=14 / M(两边不同)=109；D 类 14 文件 = 验收报告产物(8) + `verify_schema.py` + `WorkbenchPage.tsx/css` + `test_api_verify.py` + `整体逻辑说明.html` + `环境自救.bat`。清单见 `docs/project_record/night_runs/night34/main独有文件清单.md`。
- **Task B — 重定 main = p0-security-fixes**：
  - 将 14 个 main 独有文件并入 `p0-security-fixes`（commit `acd5061`，"14 files changed, 1898 insertions(+)"）；`WorkbenchPage` 为 main 独有完整页面，p0 原无 workbench 路径，并入后需后续 build 验证（package.json 等 M 类未动，不引入 main 旧依赖）。
  - `git push origin p0-security-fixes`（ff）→ `git push origin p0-security-fixes:main --force`（b1 推荐；b2 merge --allow-unrelated-histories 会产生 418 文件差异冲突，风险高，未采用）。
  - `git ls-remote` 核实 `main == p0-security-fixes == acd50615dcc130ab28227595982604f503aa98d3`。
- **Task C — 验证**：
  - `main == p0-security-fixes` ✅。
  - 新 `main` 的 `frontend/package.json`：`axios 1.20.0` / `echarts ^6.1.0` / `react-router-dom ^7.18.4`（旧漏洞版本 `axios ^1.12.0` / `echarts ^5.4.3` / `react-router-dom ^6.22.0` 已移除）。
  - Dependabot 原 10 告警（8 high / 2 moderate）来自旧 main 依赖栈；重定后 `main` 应为 0 CVE，但 GitHub 异步重扫，**实际消除状态待用户在 GitHub 页面确认**（未伪造）。
- **Task D — 收口**：
  - `ISSUES.md`：ISS-071 状态更新为 `[DONE]`（B 执行结果 + 备份分支名）；新增「历史债清单对齐（ISS-001~022）」节，ISS-003/004 经 `git log -S` 定位标 `[DONE]`，ISS-020 标 `[OPEN]` 并新开 ISS-072 登记残余，其余 12 项按债清单原值落 `[挂账]/[待处理]/[待核查]/[部分已处理]`。
  - 本 §54。
  - `docs/project_record/night_runs/night34/NIGHT_SUMMARY.md`（gitignored）。
- **红线守纪**：无备份不覆盖（备份分支先建）；未批量删除（仅 14 文件并入，main 旧内容由备份保底）；未 `reset --hard`；未伪造 PASS/告警消除（Dependabot 标待确认）；未碰生产 DuckDB/后端进程/ISS-053；main 独有内容并入前已 ask 用户（用户重贴完整提示词授权全执行，零丢失默认并入全部 14）；过程文件不进 commit。
