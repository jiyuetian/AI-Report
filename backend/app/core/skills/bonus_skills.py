"""Phase 3 加分项 Skill 化：薄封装现有 派生指标 / 可行性 / 视觉评估 / 主题治理 模块。

内部逻辑一行不改，仅暴露统一 run(ctx)；运行期从 ctx.shared 取输入，异常降级不阻塞管线。
这些都是项目里已经存在、但原设计文档未纳入的好东西，现收为 skill 让 Planner 可编排、前端可消费。
"""
from typing import Any, Dict

from .base import Skill, SkillMeta, SkillCapability, SkillContext, SkillResult
from .registry import SkillRegistry


class DerivedMetricSkill(Skill):
    """自动反推派生指标（如 抵押率=担保余额÷抵押物评估价值），白盒公式+匹配率。"""

    def __init__(self) -> None:
        self.meta = SkillMeta(
            id="derived_metric",
            name="派生指标反推",
            description="自动反推派生指标（如 抵押率=担保余额÷抵押物评估价值），白盒公式+匹配率，"
                        "反哺图表口径与血缘。",
            tags=["derived"],
            depends_on=["understand:theme"],
            capability=SkillCapability(duckdb=True),
            panel_kind="appendix",
            input_schema={"fields": "list"},
            output_schema={"metrics": "list"},
        )

    async def run(self, ctx: SkillContext) -> SkillResult:
        try:
            from app.core.derived_metric_service import detect_derived_metrics

            fields = (ctx.shared or {}).get("fields") or []
            if not fields:
                return SkillResult(self.meta.id, False, {}, skip_reason="ctx.shared.fields 未提供")
            res = detect_derived_metrics(fields, ctx.dataset_id)
            return SkillResult(skill_id=self.meta.id, ok=True, data={"metrics": res})
        except Exception as e:
            return SkillResult(skill_id=self.meta.id, ok=False, data={}, skip_reason=f"派生指标执行异常: {e}")


class FeasibilitySkill(Skill):
    """上传/对话请求即查可行性，不可行直接给原因，不浪费 LLM。"""

    def __init__(self) -> None:
        self.meta = SkillMeta(
            id="feasibility_check",
            name="可行性拦截",
            description="上传/对话请求即查可行性（粒度/字段存在/图表数/类型合理性），不可行直接给原因，不浪费 LLM。",
            tags=["feasibility"],
            depends_on=[],
            capability=SkillCapability(llm=False),
            panel_kind=None,
            input_schema={"request": "object"},
            output_schema={"feasible": "bool", "reasons": "list"},
        )

    async def run(self, ctx: SkillContext) -> SkillResult:
        try:
            from app.core.feasibility_checker import FeasibilityChecker

            req = (ctx.shared or {}).get("request") or {}
            checker = FeasibilityChecker()
            # 兼容两种公开入口
            if hasattr(checker, "check_request"):
                res = checker.check_request(req)
            else:
                res = checker.check_feasibility(req)
            return SkillResult(skill_id=self.meta.id, ok=True, data={"result": res})
        except Exception as e:
            return SkillResult(skill_id=self.meta.id, ok=False, data={}, skip_reason=f"可行性执行异常: {e}")


class VisualEvalSkill(Skill):
    """作为 Reflector 评分器，视觉维度查空壳/配色，低分触发重生成（复用 S5ScoreCard.max_retries=3）。"""

    def __init__(self) -> None:
        self.meta = SkillMeta(
            id="visual_eval",
            name="视觉评估",
            description="作为 Reflector 评分器，视觉维度查空壳/配色，评分低于阈值触发重生成"
                        "（复用 S5ScoreCard.max_retries=3）。",
            tags=["quality"],
            depends_on=["chart:recommend"],
            capability=SkillCapability(llm=False),
            panel_kind="chart",
            input_schema={"chart_config": "object"},
            output_schema={"score": "number", "issues": "list"},
        )

    async def run(self, ctx: SkillContext) -> SkillResult:
        try:
            from app.core.visual_evaluator import VisualEvaluator

            cfg = (ctx.shared or {}).get("chart_config") or {}
            res = VisualEvaluator.evaluate(cfg)
            return SkillResult(skill_id=self.meta.id, ok=True, data={"result": res})
        except Exception as e:
            return SkillResult(skill_id=self.meta.id, ok=False, data={}, skip_reason=f"视觉评估执行异常: {e}")


class ThemeGovernanceSkill(Skill):
    """暗色治理单一可信源（themeContext/ThemeProvider）+ 提示词版本元数据；新面板自动继承暗色（承接 #6）。"""

    def __init__(self) -> None:
        self.meta = SkillMeta(
            id="theme:govern",
            name="主题与提示词治理",
            description="暗色治理单一可信源（themeContext/ThemeProvider）+ 提示词版本元数据；"
                        "新面板自动继承暗色（承接 #6）。",
            tags=["governance"],
            depends_on=[],
            capability=SkillCapability(),
            panel_kind=None,
            input_schema={},
            output_schema={"version": "string"},
        )

    async def run(self, ctx: SkillContext) -> SkillResult:
        return SkillResult(
            skill_id=self.meta.id, ok=True,
            data={"version": "v0.2-aligned",
                  "theme_sources": ["theme.css", "themeContext.ts", "charts/ThemeProvider.tsx"]},
        )


def register_bonus_skills(reg: SkillRegistry) -> int:
    n = 0
    for s in [DerivedMetricSkill(), FeasibilitySkill(), VisualEvalSkill(), ThemeGovernanceSkill()]:
        reg.register(s)
        n += 1
    return n
