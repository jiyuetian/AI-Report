# -*- coding: utf-8 -*-
"""
B1 白盒登记 —— R1~R9 全部可调参数集中登记。

旧问题（B1 痛点）：§三 列了 9 条白盒规则，但各自的「可调参数落在哪」散落各处，
无统一注册表；管理员想调阈值不知道改哪个文件/配置键。

本模块是单一注册表：每条规则 → 其可调参数列表，每个参数标注
  - source: yaml | config | prompt  （落地位置）
  - key:    具体文件 / brain_configs 键 / prompt slug
  - default:默认值（与代码/配置现状一致，便于核对）
  - desc:   语义

消费方/校验方（含 _verify_b1_rule_config.py）一律从这里读取「规则→可调点」映射，
保证白盒可追溯、可调可改可版本回滚。
"""
from typing import Dict, List, Any

# 来源类型
YAML = "yaml"
CONFIG = "config"
PROMPT = "prompt"

RULE_CONFIG_CATALOG: Dict[str, List[Dict[str, Any]]] = {
    "R1": [
        {"param": "图表-数据匹配矩阵", "source": YAML,
         "key": "app/core/brain_modules/s3_chart_rules.yaml::rules[].priority",
         "default": "priority 数值（越大越优先）", "desc": "字段类型+业务语义→图表类型，自上而下首条命中"},
        {"param": "粒度约束", "source": YAML,
         "key": "app/core/brain_modules/s3_chart_rules.yaml::grain_constraints",
         "default": "macro/aggregate/detail 各自 forbidden 图型", "desc": "不同粒度禁止的图表类型"},
    ],
    "R2": [
        {"param": "饼图最大切片", "source": CONFIG, "key": "r2_pie_max_slices", "default": 8,
         "desc": "切片>8 不可读，自动收敛 Top7+其他（见 threshold_config）"},
        {"param": "柱状图最大柱数", "source": CONFIG, "key": "r2_bar_max_bars", "default": 20,
         "desc": "柱数上限"},
        {"param": "横向柱状阈值", "source": CONFIG, "key": "r2_bar_horizontal_threshold", "default": 10,
         "desc": "柱数≥此值转横向柱状"},
        {"param": "折线最大系列", "source": CONFIG, "key": "r2_line_max_series", "default": 5,
         "desc": "系列过多自动收敛"},
    ],
    "R3": [
        {"param": "目标生成提示词", "source": PROMPT, "key": "s2_goal_generator",
         "default": "prompt 内置模板", "desc": "字段组合→分析目标触发的提示词"},
        {"param": "目标生成模板键", "source": CONFIG, "key": "goal_prompt_v1",
         "default": "v1 模板", "desc": "S2 规则优先时的目标模板，可在管理中心编辑"},
    ],
    "R4": [
        {"param": "主题识别词典", "source": CONFIG, "key": "theme_dict",
         "default": "内置金融/担保主题词", "desc": "S1 词典优先命中，模糊才交 LLM"},
    ],
    "R5": [
        {"param": "编排规则", "source": CONFIG, "key": "orchestrate_rules",
         "default": "五步编排（选KPI→去冗余→分层→叙事排序→模板命中）",
         "desc": "看板编排顺序与约束"},
        {"param": "叙事硬排序", "source": YAML,
         "key": "app/core/brain_modules/s3_chart_engine_v2.py::_enforce_narrative_order_dicts",
         "default": "KPI→趋势→对比→分布→其他→风险", "desc": "叙事顺序（保留硬底线+业务关键图豁免，见 H5）"},
        # G1 护栏（2026-10-29）：AI 编排后仍强制生效的看板结构上限
        {"param": "KPI 卡上限", "source": CONFIG, "key": "r3_max_kpis", "default": 4,
         "desc": "看板 KPI 卡上限（护栏：AI 编排结果超过即截断，保证可读性）"},
        {"param": "图表总数上限", "source": CONFIG, "key": "s4_max_charts", "default": 6,
         "desc": "看板图表总数上限（护栏：AI 编排后仍截断）"},
    ],
    "R6": [
        {"param": "评分权重", "source": CONFIG, "key": "score_weights",
         "default": "coverage/narrative/redundancy/accuracy/readability 权重和=1",
         "desc": "五维评分权重（合并式加载，旧3键不覆盖新维度）"},
        {"param": "出厂阈值", "source": CONFIG, "key": "r6_grade_accept", "default": 70,
         "desc": "S5 评分≥此值直接出厂"},
        {"param": "重生成阈值", "source": CONFIG, "key": "r6_grade_regen", "default": 50,
         "desc": "50~69 降级重生成"},
        {"param": "最小降级阈值", "source": CONFIG, "key": "r6_grade_minimal", "default": 30,
         "desc": "30~49 仅保留 KPI+趋势"},
    ],
    "R7": [
        {"param": "自修复最大轮次", "source": CONFIG, "key": "r7_self_repair_max_rounds", "default": 2,
         "desc": "Self-Repair ≤2 次（PRD 要求）"},
        {"param": "自评通过阈值", "source": CONFIG, "key": "r7_self_eval_pass", "default": 70,
         "desc": "规则校验通过即放行，不随 LLM 低分翻转（pass 解耦）"},
    ],
    "R8": [
        {"param": "CRUD 权限模式", "source": CONFIG, "key": "crud_guard_mode",
         "default": "legacy(anonymous/current) 仅超管可见可删",
         "desc": "权限+留痕护栏；非超管不可越权（ISS-025 已闭环）"},
    ],
    "R9": [
        {"param": "血缘采集开关", "source": CONFIG, "key": "lineage_enabled",
         "default": "true", "desc": "六层血缘（L0-L5）采集开关，结构性无可调阈值"},
    ],
    # ── G2/G3/G4（2026-10-29）洞察与归因：把原硬编码在 s3_insight_layer 内的阈值白盒化 ──
    "R10": [
        {"param": "集中度阈值", "source": CONFIG, "key": "insight_top_share", "default": 0.30,
         "desc": "某维度最大分组占比 ≥ 此值 → top_contributor 集中度卡（原硬编码 0.30）"},
        {"param": "环比/同比显著阈值", "source": CONFIG, "key": "insight_delta", "default": 0.20,
         "desc": "|Δ| ≥ 此值 → mom_yoy_delta 突变卡（原硬编码 0.20）"},
        {"param": "离群 σ 倍数", "source": CONFIG, "key": "insight_outlier_sigma", "default": 3.0,
         "desc": "max > mean + kσ → outliers 离群卡（原硬编码 3）"},
        {"param": "结构归因 CR2 阈值", "source": CONFIG, "key": "insight_concentration_hhi", "default": 0.25,
         "desc": "前二分组合计占比 ≥ 此值 → attribution 结构归因卡（G2 新增）"},
        {"param": "趋势外推最少点数", "source": CONFIG, "key": "insight_forecast_min_points", "default": 3,
         "desc": "序列点数 ≥ 此值才做线性外推（G2 新增 forecast 卡）"},
        {"param": "单组洞察卡上限", "source": CONFIG, "key": "insight_max_cards", "default": 8,
         "desc": "每组洞察最多保留条数，防止信息过载（G2 新增）"},
        {"param": "洞察 AI 增强开关", "source": CONFIG, "key": "insight_ai_enabled", "default": True,
         "desc": "规则事实底座之上是否由 AI 做分析师级解读（关=纯规则洞察）"},
        {"param": "洞察 AI 超时", "source": CONFIG, "key": "insight_ai_timeout", "default": 25,
         "desc": "洞察 AI 解读硬超时(秒)，超时退回规则洞察"},
        {"param": "归因/建议提示词", "source": PROMPT, "key": "s3_insight_deepen",
         "default": "app/core/prompts/s3_insight_deepen.md",
         "desc": "G2/G4 洞察深化的提示词（外置，可在提示词中心维护）"},
    ],
    # ── G1（2026-10-29）AI 主执行：S4 编排由 AI 在框架内自由重排，规则降为兜底+护栏 ──
    "R11": [
        {"param": "S4 AI 主执行开关", "source": CONFIG, "key": "s4_ai_enabled", "default": True,
         "desc": "True=AI 先重排/选 KPI/去冗余；失败或超时退规则编排（A2 同款翻转）"},
        {"param": "S4 AI 超时", "source": CONFIG, "key": "s4_ai_timeout", "default": 30,
         "desc": "S4 AI 编排硬超时(秒)，超时即规则兜底，绝不拖死主链路"},
        {"param": "S4 编排提示词", "source": PROMPT, "key": "s4_ai_orchestrate",
         "default": "app/core/prompts/s4_ai_orchestrate.md",
         "desc": "AI 编排的提示词（外置，含护栏约束说明：不得臆造图表/不得超限）"},
    ],
    # ── G1（2026-10-29）AI 裁判：S5 采用「规则地基 + AI 质量把关」双票否决 ──
    "R12": [
        {"param": "S5 AI 裁判开关", "source": CONFIG, "key": "s5_ai_enabled", "default": True,
         "desc": "True=AI 参与 S5 评分与 critique；失败或超时退规则评分卡"},
        {"param": "S5 AI 超时", "source": CONFIG, "key": "s5_ai_timeout", "default": 25,
         "desc": "S5 AI 裁判硬超时(秒)，超时即规则评分"},
        {"param": "S5 裁判提示词", "source": PROMPT, "key": "s5_ai_score",
         "default": "app/core/prompts/s5_ai_score.md",
         "desc": "AI 作为 S5 主裁判的评分提示词（外置，含五维口径）"},
    ],
    # ── 债A（2026-10-29）AI 主执行：S1 主题识别由 AI 主执行，词典降为护栏+兜底 ──
    "R13": [
        {"param": "S1 AI 主执行开关", "source": CONFIG, "key": "s1_ai_enabled", "default": True,
         "desc": "True=AI 先识别主题；失败/超时退词典兜底（翻转旧「词典优先+LLM兜底」）"},
        {"param": "S1 AI 超时", "source": CONFIG, "key": "s1_ai_timeout", "default": 25,
         "desc": "S1 AI 识别硬超时(秒)，超时即词典兜底，绝不拖死主链路"},
        {"param": "S1 词典护栏阈值", "source": CONFIG, "key": "s1_ai_guardrail_threshold", "default": 0.8,
         "desc": "词典命中置信度≥此值且 AI 偏离 → 护栏强制纠正到词典结果"},
        {"param": "S1 识别提示词", "source": PROMPT, "key": "s1_ai_theme",
         "default": "app/core/prompts/s1_ai_theme.md",
         "desc": "AI 主执行主题识别的提示词（外置，含词典参考与主题候选）"},
    ],
    # ── 债A（2026-10-29）AI 主执行：S2 目标生成由 AI 主执行，规则 base_goals 降为底座+护栏 ──
    "R14": [
        {"param": "S2 AI 主执行开关", "source": CONFIG, "key": "s2_ai_enabled", "default": True,
         "desc": "True=AI 先生成目标；失败/超时退规则生成（翻转旧「规则优先+LLM增强」）"},
        {"param": "S2 AI 超时", "source": CONFIG, "key": "s2_ai_timeout", "default": 30,
         "desc": "S2 AI 生成硬超时(秒)，超时即规则生成"},
        {"param": "S2 目标数上限", "source": CONFIG, "key": "s2_max_goals", "default": 6,
         "desc": "S2 目标数上限（护栏：AI 生成后仍截断，保证可读性）"},
        {"param": "S2 生成提示词", "source": PROMPT, "key": "s2_ai_goal",
         "default": "app/core/prompts/s2_ai_goal.md",
         "desc": "AI 主执行目标生成的提示词（外置，含规则底座+飞轮经验）"},
    ],
}

# 所有规则编号（R1~R14）
ALL_RULE_IDS = [f"R{i}" for i in range(1, 15)]
