"""规划器：取代 brain_run_pipeline 的硬编码顺序。

按 goal + capability_profile + tags 选技能，拓扑排序 depends_on 生成执行序。
默认链 + 显式依赖排序，不靠 LLM 自由编排（保白盒）。
详见 docs/组件化改造设计文档_2026-09-18.md（v0.2-aligned）。
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from .base import SkillMeta
from .registry import SkillRegistry


@dataclass
class SkillDAG:
    order: List[str]
    parallel_groups: List[List[str]] = field(default_factory=list)


class SkillPlanner:
    def __init__(self, registry: SkillRegistry) -> None:
        self.registry = registry

    def build(
        self,
        goal: str,
        profile: Dict[str, Any],
        tags: Optional[List[str]] = None,
    ) -> SkillDAG:
        # 1. 选定 skills：默认全链，按 tags 剪枝
        if tags:
            selected: Dict[str, SkillMeta] = {}
            for t in tags:
                for s in self.registry.list_by_tag(t):
                    selected[s.meta.id] = s.meta
        else:
            selected = {s.meta.id: s.meta for s in self.registry._skills.values()}

        # 2. 能力剪枝（如 llm 不可达 → 剔除 capability.llm 的 skill）
        capable_ids = {s.meta.id for s in self.registry.list_capable(profile)}
        selected = {k: v for k, v in selected.items() if k in capable_ids}

        # 3. 拓扑排序 depends_on → 执行序
        order = self._topo_sort(selected)
        return SkillDAG(order=order)

    def _topo_sort(self, metas: Dict[str, SkillMeta]) -> List[str]:
        visited: Set[str] = set()
        result: List[str] = []

        def visit(mid: str) -> None:
            if mid in visited:
                return
            visited.add(mid)
            m = metas.get(mid)
            if m:
                for dep in m.depends_on:
                    if dep in metas:
                        visit(dep)
            result.append(mid)

        for mid in metas:
            visit(mid)
        return result
