# -*- coding: utf-8 -*-
"""
B3 阈值收口 —— 规则阈值单一真相源。

旧问题（B3 痛点）：R2/R6/R7 的阈值散落在多处硬编码：
  - s3_chart_engine_v2.py:343  `chart_constraints = {"pie":{"max_slices":8}, ...}`
  - s4_orchestrator.py:714      `if s >= 70 / >=50 / >=30` 三级处置阈值
  - s3_chart_rules.yaml:254     `max_slices: 8`
  → 改一处忘改另一处就会不一致，且不在 brain_configs 里、管理员不可调。

本模块把所有「规则阈值」集中登记为 DEFAULT_THRESHOLDS，并带 THRESHOLD_META
（归属哪条规则 R2/R6/R7、语义、来源、默认值）；`resolve_thresholds(db)` 在有 DB 时
合并 brain_configs 的 `thresholds` 键覆盖，否则回退默认值。各消费方（图表引擎、
S5 分级）一律从这里取数，杜绝散落硬编码。
"""
from typing import Dict, Any, Optional

# 阈值默认值（单一真相源）
DEFAULT_THRESHOLDS: Dict[str, Any] = {
    # R2 图表结构正确性
    "r2_pie_max_slices": 8,             # 饼图最大切片数（>8 自动收敛 Top7+其他）
    "r2_bar_max_bars": 20,              # 柱状图最大柱数
    "r2_bar_horizontal_threshold": 10,  # 柱数≥此值自动转横向柱状
    "r2_line_max_series": 5,            # 折线图最大系列数
    # R6 看板评分卡分级处置阈值（S5）
    "r6_grade_accept": 70,              # ≥ 直接出厂
    "r6_grade_regen": 50,               # 50~69 降级重生成
    "r6_grade_minimal": 30,             # 30~49 仅保留 KPI+趋势
    # R7 自评/自修复
    "r7_self_repair_max_rounds": 2,     # 自修复最大轮次（PRD 要求 ≤2）
    "r7_self_eval_pass": 70,            # 自评通过阈值
    # H4 规则前置后 LLM 精修超时（秒）——≤10s 兜底，避免 LLM 拖慢主链路
    "r4_llm_refine_timeout": 10,
    # H5 叙事硬排序豁免开关（默认开；关掉=允许 AI/用户自由排序）
    "narrative_enforce_strict_sort": True,
    # ── G3（2026-10-29）：洞察层阈值收口（原硬编码在 s3_insight_layer.compute_insights 内联）──
    "insight_top_share": 0.30,          # Top 贡献度集中度阈值（≥ 触发）
    "insight_delta": 0.20,              # 环比/同比显著变化阈值（|Δ|≥ 触发）
    "insight_outlier_sigma": 3.0,       # 离群判定 σ 倍数（max > mean + kσ 触发）
    "insight_concentration_hhi": 0.25,  # 结构归因 CR2（前二占比）阈值，≥ 视为高度集中
    "insight_forecast_min_points": 3,   # 趋势外推所需最少数据点数
    "insight_max_cards": 8,             # 单组洞察卡最多保留条数（防信息过载）
    # ── G1（2026-10-29）：S4/S5 AI 主执行开关与超时（AI 优先，规则降为兜底+护栏）──
    "s4_ai_enabled": True,              # S4 编排是否由 AI 主执行（关=纯规则编排）
    "s4_ai_timeout": 30,                # S4 AI 编排硬超时（秒），超时退规则编排
    "s5_ai_enabled": True,              # S5 评分是否由 AI 共同裁判（关=纯规则评分卡）
    "s5_ai_timeout": 25,                # S5 AI 裁判硬超时（秒），超时退规则评分
    "r3_max_kpis": 4,                   # 看板 KPI 卡上限（护栏，AI 不可突破）
    "s4_max_charts": 6,                 # 看板图表总数上限（护栏，AI 编排后仍截断）
    # ── 债A（2026-10-29）：S1/S2 AI 主执行开关与超时（AI 优先，规则降为兜底+护栏）──
    "s1_ai_enabled": True,              # S1 主题识别是否由 AI 主执行（关=纯词典兜底）
    "s1_ai_timeout": 25,                # S1 AI 识别硬超时（秒），超时退词典兜底
    "s1_ai_guardrail_threshold": 0.8,   # 词典命中置信度≥此值且 AI 偏离 → 护栏强制纠正
    "s2_ai_enabled": True,              # S2 目标生成是否由 AI 主执行（关=纯规则生成）
    "s2_ai_timeout": 30,                # S2 AI 生成硬超时（秒），超时退规则生成
    "s2_max_goals": 6,                  # S2 目标数上限（护栏，AI 生成后仍截断）
    # ── G4（2026-10-29）：洞察层 AI 增强开关与超时（规则事实底座 + AI 分析师解读）──
    # AI 编排的叙事方式：ai_first=AI 顺序为准+KPI 前置硬底线；strict=完全按 NARRATIVE_PRIORITY 硬排序
    "s4_narrative_mode": "ai_first",
    "insight_ai_enabled": True,         # 洞察是否由 AI 增强解读
    "insight_ai_timeout": 25,           # 洞察 AI 解读硬超时（秒），超时退规则洞察
}

# 阈值白盒元信息（B1 注册表引用）
THRESHOLD_META: Dict[str, Dict[str, Any]] = {
    "r2_pie_max_slices": {"rule": "R2", "desc": "饼图最大切片数", "source": "config", "default": 8},
    "r2_bar_max_bars": {"rule": "R2", "desc": "柱状图最大柱数", "source": "config", "default": 20},
    "r2_bar_horizontal_threshold": {"rule": "R2", "desc": "柱数≥此值转横向柱状", "source": "config", "default": 10},
    "r2_line_max_series": {"rule": "R2", "desc": "折线图最大系列数", "source": "config", "default": 5},
    "r6_grade_accept": {"rule": "R6", "desc": "S5 评分≥此值直接出厂", "source": "config", "default": 70},
    "r6_grade_regen": {"rule": "R6", "desc": "S5 评分≥此值降级重生成", "source": "config", "default": 50},
    "r6_grade_minimal": {"rule": "R6", "desc": "S5 评分≥此值仅保留 KPI+趋势", "source": "config", "default": 30},
    "r7_self_repair_max_rounds": {"rule": "R7", "desc": "自修复最大轮次", "source": "config", "default": 2},
    "r7_self_eval_pass": {"rule": "R7", "desc": "自评通过阈值", "source": "config", "default": 70},
    "r4_llm_refine_timeout": {"rule": "R4", "desc": "规则前置后 LLM 精修超时(秒)", "source": "config", "default": 10},
    "narrative_enforce_strict_sort": {"rule": "R5", "desc": "叙事硬排序豁免开关(默认开)", "source": "config", "default": True},
    # G3 洞察层（R10 洞察/归因/预测/建议规则）
    "insight_top_share": {"rule": "R10", "desc": "Top贡献集中度阈值(≥触发)", "source": "config", "default": 0.30},
    "insight_delta": {"rule": "R10", "desc": "环比/同比显著变化阈值(|Δ|≥触发)", "source": "config", "default": 0.20},
    "insight_outlier_sigma": {"rule": "R10", "desc": "离群判定σ倍数(max>mean+kσ)", "source": "config", "default": 3.0},
    "insight_concentration_hhi": {"rule": "R10", "desc": "结构归因前二占比(CR2)阈值", "source": "config", "default": 0.25},
    "insight_forecast_min_points": {"rule": "R10", "desc": "趋势外推最少数据点数", "source": "config", "default": 3},
    "insight_max_cards": {"rule": "R10", "desc": "单组洞察卡最多条数", "source": "config", "default": 8},
    # G1 S4/S5 AI 主执行（R11 AI 主执行与兜底 / R12 AI 裁判）
    "s4_ai_enabled": {"rule": "R11", "desc": "S4编排AI主执行开关", "source": "config", "default": True},
    "s4_ai_timeout": {"rule": "R11", "desc": "S4 AI编排硬超时(秒)", "source": "config", "default": 30},
    "s5_ai_enabled": {"rule": "R12", "desc": "S5 AI共同裁判开关", "source": "config", "default": True},
    "s5_ai_timeout": {"rule": "R12", "desc": "S5 AI裁判硬超时(秒)", "source": "config", "default": 25},
    # 债A S1/S2 AI 主执行（R13 S1 AI主执行与兜底 / R14 S2 AI主执行与护栏）
    "s1_ai_enabled": {"rule": "R13", "desc": "S1主题识别AI主执行开关", "source": "config", "default": True},
    "s1_ai_timeout": {"rule": "R13", "desc": "S1 AI识别硬超时(秒)", "source": "config", "default": 25},
    "s1_ai_guardrail_threshold": {"rule": "R13", "desc": "S1词典护栏阈值(≥且AI偏离则纠正)", "source": "config", "default": 0.8},
    "s2_ai_enabled": {"rule": "R14", "desc": "S2目标生成AI主执行开关", "source": "config", "default": True},
    "s2_ai_timeout": {"rule": "R14", "desc": "S2 AI生成硬超时(秒)", "source": "config", "default": 30},
    "s2_max_goals": {"rule": "R14", "desc": "S2目标数上限(护栏)", "source": "config", "default": 6},
    # 编排护栏（R5）
    "r3_max_kpis": {"rule": "R5", "desc": "看板KPI卡上限(护栏)", "source": "config", "default": 4},
    "s4_max_charts": {"rule": "R5", "desc": "看板图表总数上限(护栏)", "source": "config", "default": 6},
    "s4_narrative_mode": {"rule": "R11", "desc": "AI编排叙事模式(ai_first|strict)", "source": "config", "default": "ai_first"},
    # G4 洞察 AI 增强（R10）
    "insight_ai_enabled": {"rule": "R10", "desc": "洞察层AI增强解读开关", "source": "config", "default": True},
    "insight_ai_timeout": {"rule": "R10", "desc": "洞察AI解读硬超时(秒)", "source": "config", "default": 25},
}

# brain_configs 中承载覆盖值的配置键
CONFIG_KEY = "thresholds"


def get_default(key: str, default: Optional[Any] = None) -> Any:
    return DEFAULT_THRESHOLDS.get(key, default)


async def resolve_thresholds(db=None) -> Dict[str, Any]:
    """合并 DB 覆盖（brain_configs.thresholds）与默认值，返回完整阈值 dict。

    db 为 None（离线/单测）时直接返回默认副本。
    """
    merged = dict(DEFAULT_THRESHOLDS)
    if db is None:
        return merged
    try:
        from app.core.brain_config_manager import BrainConfigManager
        cfg = await BrainConfigManager.get_config(db, CONFIG_KEY)
        if cfg and isinstance(cfg.get("content"), dict):
            for k, v in cfg["content"].items():
                if k in DEFAULT_THRESHOLDS:
                    merged[k] = v
    except Exception:
        # 配置不可达时安全回退默认，绝不阻断主链路
        pass
    return merged
