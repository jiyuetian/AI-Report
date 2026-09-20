"""质检 Skill 化（Phase 2）：薄封装 core/quality_checker.QualityChecker。

把 #8 的「行号/原值/问题/清洗后结果」samples 定为 quality:check skill 的标准可解释输出契约
（samples 已由 quality_checker._build_samples 产出，前端 QualityCheckPanel 可展开）。
薄封装铁律：六类规则内部逻辑一行不改，仅暴露统一 run(ctx) 入口；运行期从 ctx.shared 取表清单，
异常降级为 ok=False 不阻塞管线。Phase 4 Planner 实际调度前，本 skill 仅作为能力注册存在。
"""
from typing import Any, Dict, List

from .base import Skill, SkillMeta, SkillCapability, SkillContext, SkillResult
from .registry import SkillRegistry


class QualityCheckSkill(Skill):
    def __init__(self) -> None:
        self.meta = SkillMeta(
            id="quality:check",
            name="数据质检",
            description="对数据集做空值/格式/类型/唯一/范围/逻辑等六类质检，返回问题清单与每行可解释样本"
                        "（行号/原值/问题/清洗后结果）。",
            tags=["quality", "clean"],
            depends_on=[],
            capability=SkillCapability(duckdb=True),
            panel_kind="quality",
            input_schema={"quality_targets": "list[{table_name, columns}]"},
            output_schema={"issues": "list", "samples": "list"},
        )

    async def run(self, ctx: SkillContext) -> SkillResult:
        targets = (ctx.shared or {}).get("quality_targets") or []
        if not targets:
            return SkillResult(
                skill_id=self.meta.id, ok=False, data={},
                skip_reason="ctx.shared.quality_targets 未提供（需 Planner 注入表清单）",
            )
        try:
            from app.core.quality_checker import QualityChecker

            checker = QualityChecker(ctx.duck, None)
            issues: List[Dict[str, Any]] = []
            for t in targets:
                res = checker.check_table(t["table_name"], t["columns"])
                for it in res.get("issues", []):
                    issues.append({
                        "table": t["table_name"],
                        "type": it.get("type"),
                        "column": it.get("column"),
                        "severity": it.get("severity"),
                        "message": it.get("message"),
                        "row_count": it.get("row_count"),
                        # #8 产品化契约：每行可解释样本（行号/原值/问题/清洗后）
                        "samples": it.get("samples", []),
                        "repair_options": it.get("repair_options", []),
                    })
            return SkillResult(skill_id=self.meta.id, ok=True, data={"issues": issues})
        except Exception as e:  # 降级：不阻塞管线
            return SkillResult(skill_id=self.meta.id, ok=False, data={}, skip_reason=f"质检执行异常: {e}")


def register_quality_skills(reg: SkillRegistry) -> int:
    reg.register(QualityCheckSkill())
    return 1
