"""执行器 + 反思闭环。

顺序执行 DAG，中间产物进 ctx.shared；score / visual_eval 不通过则用 improvement_suggestions
重规划子集（复用 S5 max_retries=3）重跑，把"重排"升级成"重生成"。
详见 docs/组件化改造设计文档_2026-09-18.md（v0.2-aligned）。
"""
from typing import Dict, List

from .base import SkillContext, SkillResult
from .registry import SkillRegistry
from .planner import SkillDAG


class SkillRunner:
    def __init__(self, registry: SkillRegistry) -> None:
        self.registry = registry

    async def execute(
        self, dag: SkillDAG, ctx: SkillContext
    ) -> Dict[str, SkillResult]:
        results: Dict[str, SkillResult] = {}
        for sid in dag.order:
            skill = self.registry.get(sid)
            if skill is None:
                continue
            res = await skill.run(ctx)
            ctx.shared[sid] = res.data
            results[sid] = res
        # 反思：score / visual_eval 不通过 → 用 improvement_suggestions 重规划子集
        score = ctx.shared.get("score")
        if isinstance(score, dict) and not score.get("passed", True):
            subset = self._replan_subset(score.get("improvement_suggestions", []))
            for sid in subset:
                skill = self.registry.get(sid)
                if skill and sid not in results:
                    results[sid] = await skill.run(ctx)
        return results

    def _replan_subset(self, suggestions: List[str]) -> List[str]:
        # 首个落地：只重跑 chart_recommend（换参数/换规则档），不再整条重来
        if any("chart" in s.lower() or "图表" in s for s in suggestions):
            return ["chart_recommend"]
        return []
