"""Skill 注册表下发 API：前端 SkillPanel 据此动态渲染能力入口。

启动时把各 Phase 的 skill 模块统一注册进全局 registry；registry 本身零侵入现有管线。
详见 docs/组件化改造设计文档_2026-09-18.md（v0.2-aligned）。
"""
from fastapi import APIRouter

from app.core.skills.registry import registry
from app.core.skills.chart_skills import register_chart_skills
from app.core.skills.quality_skills import register_quality_skills
from app.core.skills.bonus_skills import register_bonus_skills
from app.core.skills.brain_skills import register_brain_skills

# 各 Phase 能力自注册（薄封装、零逻辑改动；不改变任何一次真实生成行为）
register_chart_skills(registry)     # Phase 1a：chart:<type>
register_quality_skills(registry)   # Phase 2：quality:check（含 #8 可解释样本契约）
register_bonus_skills(registry)     # Phase 3：derived_metric / feasibility_check / visual_eval / theme:govern
register_brain_skills(registry)     # Phase 4(安全部分)：understand:theme / understand:goal / chart:recommend / score:card

router = APIRouter()


@router.get("/skills")
async def list_skills():
    metas = registry.all_meta()
    return {"count": len(metas), "skills": metas}
