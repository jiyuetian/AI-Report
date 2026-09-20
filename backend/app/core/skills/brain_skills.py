"""Phase 4 S1-S5 薄封装：把 理解/目标/图表/评分 四阶段收为 skill，统一 run(ctx)。

执行契约（与 brain_run_pipeline 内联逻辑一致，零行为回退）：
- run() 返回 SkillResult.data 即「内联代码原本拿到的对象」：
  - understand:theme  -> data = detect_theme(...) 的返回 dict（含 theme_tag 等）
  - understand:goal  -> data = generate_analysis_goals(...) 的返回（goals 列表）
  - chart:recommend  -> data = s3_result dict（含 charts / generated_by / fallback_reason）
  - score:card       -> data = S5ScoreCard.score(...) 的返回 dict
- 尊重 ctx.capability_profile["llm_reachable"]：不可达时 S1/S3 走规则引擎，不调 LLM、不挂起。
- 任何异常 -> ok=False，pipeline 的 _exec_skill 会自动回退到原内联逻辑。

详见 docs/组件化改造设计文档_2026-09-18.md（v0.2-aligned）。
"""
from typing import Any, Dict

from .base import Skill, SkillMeta, SkillCapability, SkillContext, SkillResult
from .registry import SkillRegistry


class ThemeDetectSkill(Skill):
    """S1 主题识别：从字段与样本识别分析主题，供 S2 生成目标。"""

    def __init__(self) -> None:
        self.meta = SkillMeta(
            id="understand:theme",
            name="主题识别(S1)",
            description="S1 主题识别：从字段与样本识别分析主题（担保/风控/财务等），供 S2 生成目标。",
            tags=["understand"],
            depends_on=[],
            capability=SkillCapability(duckdb=True, llm=True),
            panel_kind=None,
            input_schema={"fields": "list", "sample_data": "list"},
            output_schema={"theme_tag": "string"},
        )

    async def run(self, ctx: SkillContext) -> SkillResult:
        try:
            from app.core.brain_modules import detect_theme

            llm_ok = ctx.capability_profile.get("llm_reachable", True)
            res = await detect_theme(
                db=ctx.db,
                fields=ctx.shared.get("fields", []),
                sample_data=ctx.shared.get("sample_data"),
                dataset_name=ctx.shared.get("dataset_name", ctx.dataset_id),
                use_llm=llm_ok,
            )
            return SkillResult(skill_id=self.meta.id, ok=True, data=res)
        except Exception as e:
            return SkillResult(skill_id=self.meta.id, ok=False, data={}, skip_reason=f"S1 执行异常: {e}")


class GoalGenSkill(Skill):
    """S2 目标生成：基于主题与字段生成分析目标清单，约束图表范围。"""

    def __init__(self) -> None:
        self.meta = SkillMeta(
            id="understand:goal",
            name="目标生成(S2)",
            description="S2 目标生成：基于主题与字段生成分析目标清单，约束图表范围。",
            tags=["understand"],
            depends_on=["understand:theme"],
            capability=SkillCapability(duckdb=True, llm=True),
            panel_kind=None,
            input_schema={"theme": "object", "fields": "list", "grain": "string"},
            output_schema={"goals": "list"},
        )

    async def run(self, ctx: SkillContext) -> SkillResult:
        try:
            from app.core.brain_modules import generate_analysis_goals
            from app.core.config import settings

            # 与内联逻辑一致：S2 是否用 LLM 由 settings.BRAIN_S2_USE_LLM 决定（默认规则引擎），
            # 叠加 LLM 不可达时强制规则，避免离线挂起。
            llm_ok = ctx.capability_profile.get("llm_reachable", True)
            use_llm = bool(settings.BRAIN_S2_USE_LLM) and llm_ok
            goals = await generate_analysis_goals(
                db=ctx.db,
                theme=ctx.shared.get("theme"),
                fields=ctx.shared.get("fields", []),
                grain=ctx.shared.get("grain", "detail"),
                use_llm=use_llm,
            )
            return SkillResult(skill_id=self.meta.id, ok=True, data=goals)
        except Exception as e:
            return SkillResult(skill_id=self.meta.id, ok=False, data=[], skip_reason=f"S2 执行异常: {e}")


class ChartRecommendSkill(Skill):
    """S3 图表推荐：基于字段类型/粒度推荐图表集合，复用 ChartSkill 元数据。"""

    def __init__(self) -> None:
        self.meta = SkillMeta(
            id="chart:recommend",
            name="图表推荐(S3)",
            description="S3 图表推荐：基于字段类型/粒度推荐图表集合，复用 ChartSkill 元数据。",
            tags=["chart"],
            depends_on=["understand:goal", "derived_metric"],
            capability=SkillCapability(duckdb=True, llm=True),
            panel_kind="chart",
            input_schema={"fields": "list", "grain": "string", "derived_metrics": "list"},
            output_schema={"charts": "list", "generated_by": "string"},
        )

    async def run(self, ctx: SkillContext) -> SkillResult:
        try:
            llm_ok = ctx.capability_profile.get("llm_reachable", True)
            if not llm_ok:
                from app.core.brain_modules.s3_chart_engine_v2 import S3ChartEngine

                engine = S3ChartEngine(derived_metrics=ctx.shared.get("derived_metrics"))
                cfg = engine.generate_dashboard_config(
                    fields=ctx.shared.get("fields", []),
                    grain=ctx.shared.get("grain", "detail"),
                    derived_metrics=ctx.shared.get("derived_metrics"),
                )
                return SkillResult(
                    skill_id=self.meta.id,
                    ok=True,
                    data={
                        "charts": cfg.get("charts", []),
                        "generated_by": "rule_engine",
                        "fallback_reason": "LLM 不可达，规则引擎兜底",
                    },
                )
            from app.core.brain_modules import generate_charts_with_llm

            res = await generate_charts_with_llm(
                db=ctx.db,
                theme=ctx.shared.get("theme"),
                fields=ctx.shared.get("fields", []),
                goals=ctx.shared.get("goals", []),
                grain=ctx.shared.get("grain", "detail"),
                derived_metrics=ctx.shared.get("derived_metrics"),
            )
            return SkillResult(skill_id=self.meta.id, ok=True, data=res)
        except Exception as e:
            return SkillResult(
                skill_id=self.meta.id,
                ok=False,
                data={"charts": [], "generated_by": "rule_engine"},
                skip_reason=f"S3 执行异常: {e}",
            )


class ScoreCardSkill(Skill):
    """S5 评分卡：对生成看板打多维分，低分触发 Reflector 重生成（max_retries=3）。"""

    def __init__(self) -> None:
        self.meta = SkillMeta(
            id="score:card",
            name="评分卡(S5)",
            description="S5 评分卡：对生成看板打多维分，低分触发 Reflector 重生成（max_retries=3）。",
            tags=["quality"],
            depends_on=["chart:recommend"],
            capability=SkillCapability(duckdb=True, llm=False),
            panel_kind="chart",
            input_schema={"dashboard": "object"},
            output_schema={"score": "object"},
        )

    async def run(self, ctx: SkillContext) -> SkillResult:
        try:
            from app.core.brain_modules.s4_orchestrator import S5ScoreCard

            sc = S5ScoreCard()
            await sc.load_score_config(ctx.db)
            dashboard = ctx.shared.get("dashboard", {})
            res = sc.score(dashboard) if hasattr(sc, "score") else None
            return SkillResult(skill_id=self.meta.id, ok=True, data=res or {})
        except Exception as e:
            return SkillResult(skill_id=self.meta.id, ok=False, data={}, skip_reason=f"S5 执行异常: {e}")


def register_brain_skills(reg: SkillRegistry) -> int:
    n = 0
    for s in [ThemeDetectSkill(), GoalGenSkill(), ChartRecommendSkill(), ScoreCardSkill()]:
        reg.register(s)
        n += 1
    return n
