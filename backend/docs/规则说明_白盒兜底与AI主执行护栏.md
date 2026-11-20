# AI-Report 规则说明（白盒兜底 + AI 主执行护栏）

> 文档定位：**白盒化规则说明**。把 AI-Report 生成链路里所有「兜底 / 护栏 / AI 主执行开关」集中讲清楚——
> 每条规则对应什么意图、可调参落在哪个文件/配置键、默认值是多少、不合理时去哪改。
> 设计依据：PRD `AI快速BI报表工具2.0.md` §三（9 条白盒规则）、§4.7（LIDA 四阶段）、§4.8（规则主链路 + LLM 增强）。
> 单一事实源（代码）：`app/core/brain_modules/rule_config_catalog.py`（R1–R15 全注册在此）。

---

## 0. 设计原则（北极星）

- **AI 是每步主执行者**：S1 主题 / S2 目标 / S4 编排 / S5 裁判 / S6 自主 CRUD，全部 AI 先跑；失败或超时 **退化为规则兜底**，绝不拖死主链路。
- **规则是地基 + 护栏**：规则引擎产出候选池、守住可读性下限（KPI 上限、图表数上限、叙事顺序），AI 在其框架内自由重排/增强。
- **白盒可追溯**：每条规则的可调参数集中在 `rule_config_catalog.py`；阈值在 `threshold_config.py`；提示词外置 `core/prompts/*.md` 且可在**管理后台·提示词中心**在线编辑。
- **红线不可越**：AI 绝不直接碰生产库（批量改数、权限变更默认全关），每次变更前强制快照可回滚。

---

## 1. 规则总表（R1–R15）

| 规则 | 意图 | 可调参数（键） | 默认值 | 落地位置（source） |
|---|---|---|---|---|
| **R1** | 图表-数据匹配矩阵 + 粒度约束 | `s3_chart_rules.yaml::rules[].priority`（字段类型+业务语义→图型，首条命中）；`grain_constraints`（macro/aggregate/detail 各自禁用的图型） | priority 数值大者优先 | yaml |
| **R2** | 图表可读性上限 | `r2_pie_max_slices`=8 / `r2_bar_max_bars`=20 / `r2_bar_horizontal_threshold`=10 / `r2_line_max_series`=5 | 见左 | config |
| **R3** | 目标生成模板 | 提示词 `s2_goal_generator`；模板键 `goal_prompt_v1` | v1 模板 | prompt/config |
| **R4** | 主题识别词典 | `theme_dict`（金融/担保主题词） | 内置词典 | config |
| **R5** | 看板编排与叙事硬排序 | `orchestrate_rules`；`s3_chart_engine_v2._enforce_narrative_order_dicts`（KPI→趋势→对比→分布→其他→风险）；护栏 `r3_max_kpis`=4、`s4_max_charts`=6 | 见左 | yaml/config |
| **R6** | S5 评分分级处置 | `score_weights`（五维权重和=1）；`r6_grade_accept`=70（≥直接出厂）；`r6_grade_regen`=50（50~69 降级重生成）；`r6_grade_minimal`=30（30~49 仅留 KPI+趋势） | 见左 | config |
| **R7** | Self-Repair 自修复 | `r7_self_repair_max_rounds`=2（PRD 要求≤2）；`r7_self_eval_pass`=70（规则校验通过即放行，不随 LLM 低分翻转） | 见左 | config |
| **R8** | CRUD 权限+留痕护栏 | `crud_guard_mode`=legacy（anonymous/current 仅超管可见可删）；非超管不可越权（ISS-025 已闭环） | legacy | config |
| **R9** | 六层血缘采集 | `lineage_enabled`=true | true | config |
| **R10** | 洞察/归因阈值白盒化（G2/G3/G4） | `insight_top_share`=0.30（集中度）/ `insight_delta`=0.20（环比同比显著）/ `insight_outlier_sigma`=3.0（离群）/ `insight_concentration_hhi`=0.25（结构归因）/ `insight_forecast_min_points`=3 / `insight_max_cards`=8 / `insight_ai_enabled`=true / `insight_ai_timeout`=25 / 提示词 `s3_insight_deepen` | 见左 | config/prompt |
| **R11** | S4 AI 主执行编排 | `s4_ai_enabled`=true / `s4_ai_timeout`=30 / 提示词 `s4_ai_orchestrate`（含护栏：不得臆造图表、不得超限） | 见左 | config/prompt |
| **R12** | S5 AI 裁判（规则地基+AI 双票否决） | `s5_ai_enabled`=true / `s5_ai_timeout`=25 / 提示词 `s5_ai_score` | 见左 | config/prompt |
| **R13** | S1 AI 主执行主题识别 | `s1_ai_enabled`=true / `s1_ai_timeout`=25 / `s1_ai_guardrail_threshold`=0.8（词典命中且 AI 偏离→强制纠正）/ 提示词 `s1_ai_theme` | 见左 | config/prompt |
| **R14** | S2 AI 主执行目标生成 | `s2_ai_enabled`=true / `s2_ai_timeout`=30 / `s2_max_goals`=6 / 提示词 `s2_ai_goal`（含规则底座+飞轮经验） | 见左 | config/prompt |
| **R15** | S6 AI 自主 CRUD（增删改查） | `ai_crud_enabled`=true / `ai_crud_max_actions`=5（单次动作上限，防改崩）/ `ai_crud_allow_bulk`=false（红线④绝不让 AI 碰生产库）/ `ai_crud_allow_permission`=false（权限仅超管）/ `ai_crud_require_snapshot`=true（R8-4 改前快照可回滚）/ 提示词 `s6_ai_crud` | 见左 | config/prompt |

---

## 2. 兜底 / 护栏逻辑（你最关心的「不合理能及时调整」）

### 2.1 AI 主执行 → 规则兜底的翻转（A2/G1/债A）
S1/S2/S4/S5/S6 都是「**AI 先跑，失败或超时退规则**」：
- 每个 AI 节点有独立超时（`s1/s2/s4_ai_timeout` 25~30s，`s5_ai_timeout` 25s），超时即规则兜底，**绝不拖死主链路**。
- 规则兜底结果标注 `fallback_used=true` / `generated_by='rule'`，前端可识别（如显示「规则兜底」徽标）。
- 真机实测：当所有 LLM provider 在 180s 内连续 429/403/404，`[Brain] S3 LLM 超时，规则引擎从候选池兜底` 正确触发，生成不中断。

### 2.2 S3 图表规则（14 条，来自 `s3_chart_rules.yaml`）
- 字段类型 + 业务语义 → 图表类型（priority 自上而下首条命中）。
- 粒度约束：macro/aggregate/detail 各自禁止的图型（如宏观层不出明细散点）。
- 叙事硬排序：`KPI → 趋势 → 对比 → 分布 → 其他 → 风险`（保留硬底线 + 业务关键图豁免，见 H5）。
- 聚合口径：duration/rate/age 一律 `avg`（不再被 sum 累计）；代偿金额等零值主导字段推荐 `fill_constant`（填 0），不再一律中位数。

### 2.3 S5 分级处置三档（对齐「AI 参与权 + 否决权」）
- `score ≥ 70` → 直接出厂；
- `50 ≤ score < 70` → 编排层重排/补图后重评；
- `30 ≤ score < 50` → 降级简单图（仅留 KPI + 趋势）；
- `score < 30` → 弹出选择框，交用户决策（不静默出厂）。

### 2.4 S6 AI 自主 CRUD 护栏（R15）
- 单次指令最多执行 `ai_crud_max_actions=5` 个动作，防一次指令改崩看板。
- `bulk_update_data` / `manage_permissions` 默认被 `_apply_guardrails` 拦截（`_blocked=true`），AI 不可碰生产库、不可改权限。
- 每次变更前 `ai_crud_require_snapshot=true` 对看板打回退点，可一键回滚；每动作写 `ai_action_log`（`llm_layer='ai'`）留痕。
- 真机自测（`verify_crud_agent.py`，11/11 PASS）已覆盖：LLM 规划(ai) / 规则兜底(rule) / 截断(9→3) / 批量&权限拦截 / 真实 ActionExecutor 改 config / 快照 / 日志。

---

## 3. 怎么调整（白盒化操作路径）

| 想调什么 | 去哪改 | 是否热更新 |
|---|---|---|
| 图表类型匹配、粒度禁用 | `app/core/brain_modules/s3_chart_rules.yaml` | 重启生效 |
| 各阈值（KPI 上限/图表数/评分档/洞察阈值/S4-S6 超时与开关） | `app/core/brain_modules/threshold_config.py`（`DEFAULT_THRESHOLDS`） | 重启生效 |
| 各 AI 节点提示词（行业指标处理注意点、UI 样式、图标编排模版） | `app/core/prompts/*.md`；**可在管理后台·提示词中心在线编辑**（经 `prompt_manager.loaded_prompt` 覆盖文件） | 提示词中心改完即时生效 |
| 规则→可调点映射总表 | `app/core/brain_modules/rule_config_catalog.py` | 重启生效 |

> 提示词中心（R3）已接入生成链路：`load_prompt()` 先查提示词中心的「启用中覆盖」，再回退 `prompts/*.md`，再回退代码内置。故在中心维护的 ui 样式 / 图标编排 / 行业指标模版，**确实会影响** AI 生成结果。

---

## 4. 真机验证结论（不是 grep 自证）

- `verify_user4fixes.py`：**27 PASS / 0 FAIL**（#1 清洗「不处理」选项、#3 意图逗号模式、#4 模板套用 0 图反馈）。
- `verify_crud_agent.py`：**11 PASS / 0 FAIL**（S6 规划 LLM(ai)/规则(rule) → R15 护栏 → 真实执行 → 快照 → 日志全链路）。
- 完整 `brain_run_pipeline` 真跑（前台进程直连 LLM）：产出看板 `score=78.75 / passed=True / 6 图表`，`generated_by=llm`、`ai_primary=True`、S5 `s5_ai_verdict=pass`、已写 `ai_action_log`。证明 AI 主执行 + 规则兜底 + 日志留痕 端到端成立。

---

## 5. 已知待补（诚实登记，非隐瞒）

1. **本说明文档此前缺失**：规则代码已白盒化（R1–R15 全注册），但缺这份人读说明——本次补齐。
2. **LLM provider 健康度下降**：`.env` 中多数 provider 现已 429/403/404/欠费（openrouter 404、unisound 欠费、deepseek/zhipu 429、sensenova 结构损坏）。实测仅 `deepseek-flash-v41`  intermittent 可用。failover 能兜底，但「AI 主执行」稳定性依赖可用 provider，**建议 prune 失效 key**（待你确认后处理，属配置变更）。
3. **改造方案文档（`AI-Report完整改造方案.md` v1.0）已过时**：实际代码已到 v4 收口 + S6 在途，计划文档未同步——建议另起 v2 对齐基准（待你拍板）。
4. **用户验收（你本人点验）尚未做**：以上为 AI 真机自测，最终「用户验收✅」需你过一遍真实看板。
