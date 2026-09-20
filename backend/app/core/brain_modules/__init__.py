"""
策略大脑模块 - S1/S2/S3/S4/S5
"""
from .s1_theme_detector import S1ThemeDetector, detect_theme, ThemeDetectionResult
from .s2_goal_generator import S2GoalGenerator, generate_analysis_goals, AnalysisGoal
from .s3_chart_engine_v2 import S3ChartEngine, recommend_charts, generate_dashboard
from .s3_llm_enhancer import S3LLMEnhancer, generate_charts_with_llm, validate_chart_grain
from .s4_orchestrator import S4Orchestrator, S5ScoreCard, orchestrate_and_score

__all__ = [
    "S1ThemeDetector",
    "detect_theme",
    "ThemeDetectionResult",
    "S2GoalGenerator",
    "generate_analysis_goals",
    "AnalysisGoal",
    "S3ChartEngine",
    "recommend_charts",
    "generate_dashboard",
    "S3LLMEnhancer",
    "generate_charts_with_llm",
    "validate_chart_grain",
    "S4Orchestrator",
    "S5ScoreCard",
    "orchestrate_and_score"
]