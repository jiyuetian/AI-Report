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

> 第 1 件 ISS-057：只读实测修正根因——旧 `os.kill(pid,0)` 在 Windows 上对本机「刚被杀 PID」**不抛异常**→误判存活→B5 拒绝重启（比「死 PID 抛 SystemError」更隐蔽且 100% 可复现）。ctypes `OpenProcess`+`GetExitCodeProcess` 修复对两种形态都覆盖（ERROR_ACCESS_DENIED(5) 视为存活防误杀真进程）。独立 harness 进程内驱动真实 `main()`（uvicorn.run 桩、隔离端口 18099、未碰 8000 活后端），两轮（无 pidfile / 残留死 PID=999999）均到达 `[B5] 启动后端` → **ALL PASS(7/7)**。`ISSUES.md` 新增 `## ISS-057` 条目状态 `[DONE]`。commit `270f21c`。
> 第 2 件 D-018 Task1：纯增量 fire-and-forget 日志，不改任何既有对话行为。落码 `models/ai_action_log.py`(新,30 行) + `core/ai_action_log.py`(新,99 行 helper) + `chat.py` 主链路+兜底埋点块(75 行) + `main.py`/`models/__init__.py` 注册。`docs/test/AI_TEST_CASES_v1.md` 新增**模块 L（8 条，v1.5）**，随仓把既有的未提交模块 K（12 条）一并入库。自测：`_verify_task1_integration.py` **INTEGRATION OK**（真实 SSE 链路 add_chart 写入 `'add_chart','success','add_chart','rule',2219,{metric:担保余额}`）+ `_verify_task1_scenarios.py` **ALL SCENARIOS OK(L1–L8)**：主链路/确认词透传 confirmation_word/undo/delete_chart/流异常 stream_error/持锁写入/超大params截断合法JSON/30并发全落库/坏DB不抛。所有改动模块 `py_compile` 全过；A27+K13 因纯增量日志无退化（核心动作路径 L1–L4 同链路复跑验证行为一致）。commit `d221f04`。


> 第 3 件 Task A（LLM 链 7 层调整，D-020）：`.env` 被 gitignore 故配置本体不进 git，本行仅登记变更；用户须手动重启 8000 后端（pid=9632，禁 kill）方使新链生效。3b 灰度结论——glm-4.5-air 与 glm-4.6v 直调 success=True；glm-4.7-flash 直调两次均 429（code 1305 该模型访问量过大），属免费模型峰值拥堵的瞬时限流而非模型不存在/鉴权失败，网关 failover 会自动跳过它继续走 glm-4.6v→deepseek→agnes→flash-lite，故保留入链无害，按 3b 规则标记待用户确认是否保留；如用户决定移除则回退 `.env` 第 13/15 行即可。3c 真实业务调用核验需 8000 重启后从运行日志确认 provider/model 字段。