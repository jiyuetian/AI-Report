"""单一机器可读能力源。各 skill 模块 import 时调用 register() 自注册。

前端 GET /api/v1/skills 读取 all_meta() 动态渲染 SkillPanel 入口。
详见 docs/组件化改造设计文档_2026-09-18.md（v0.2-aligned）。
"""
from typing import Any, Dict, List, Optional

from .base import Skill, SkillMeta


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: Dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        # 允许重复注册（薄封装测试 / 热重载时常见），后者覆盖前者
        self._skills[skill.meta.id] = skill

    def get(self, skill_id: str) -> Optional[Skill]:
        return self._skills.get(skill_id)

    def list_by_tag(self, tag: str) -> List[Skill]:
        return [s for s in self._skills.values() if tag in s.meta.tags]

    def all_meta(self) -> List[SkillMeta]:
        return [s.meta for s in self._skills.values()]

    def list_capable(self, profile: Dict[str, Any]) -> List[Skill]:
        """按 capability_profile 过滤：llm_reachable=False 时剔除 capability.llm 的 skill"""
        llm_ok = bool(profile.get("llm_reachable", True))
        out: List[Skill] = []
        for s in self._skills.values():
            if s.meta.capability.llm and not llm_ok:
                continue
            out.append(s)
        return out

    def __len__(self) -> int:
        return len(self._skills)


# 全局注册表单例：所有 skill 模块共享同一实例
registry = SkillRegistry()
