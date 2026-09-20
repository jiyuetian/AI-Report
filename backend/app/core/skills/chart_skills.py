"""图表引擎 Skill 化（Phase 1a）：把 s3_chart_rules.yaml 中的图表类型注册为 chart:<type> skill。

这是后端单一机器可读的图表能力源；前端 ChartRenderer 后续可据此核对/补全渲染分支
（例如当前前端 ChartConfig 联合类型缺 histogram，正是"规则与执行脱节"的漏渲染根因）。

Phase 1a 仅注册元数据（低风险、可回滚）；Phase 1b 由 chart_recommend 与 ChartRenderer 实际委托 render。
详见 docs/组件化改造设计文档_2026-09-18.md（v0.2-aligned）Phase 1。
"""
import os
from typing import Any, Dict, List

try:
    import yaml
except ImportError:  # pragma: no cover - 项目运行时 yaml 必装
    yaml = None

from .base import Skill, SkillMeta, SkillCapability, SkillContext, SkillResult
from .registry import SkillRegistry

_RULES_PATH = os.path.join(os.path.dirname(__file__), "..", "brain_modules", "s3_chart_rules.yaml")

# 中文展示名（与前端 ChartConfig / 用户语言一致）
_DISPLAY_NAMES = {
    "kpi": "KPI 指标卡",
    "line": "折线趋势图",
    "bar": "柱状对比图",
    "pie": "占比饼图",
    "scatter": "散点分布图",
    "table": "明细表格",
    "map": "地理地图",
    "histogram": "分布直方图",
    "heatmap": "热力图",
}


def _load_chart_types() -> Dict[str, Dict[str, Any]]:
    """从 yaml 解析出每种 chart type 的代表性元信息（首个使用该 type 的 rule）。"""
    out: Dict[str, Dict[str, Any]] = {}
    if yaml is None or not os.path.exists(_RULES_PATH):
        return out
    with open(_RULES_PATH, encoding="utf-8") as f:
        doc = yaml.safe_load(f) or {}
    for rule in doc.get("rules", []):
        chart = (rule or {}).get("chart") or {}
        ctype = chart.get("type")
        if not ctype or ctype in out:
            continue
        out[ctype] = {
            "rule_name": rule.get("name", ctype),
            "title_template": chart.get("title", ""),
            "config": chart.get("config", {}),
        }
    return out


class ChartSkill(Skill):
    """图表类型能力单元：携带该类型的渲染/规则元数据，供前端核对与后端委托。

    Phase 1a 仅注册元数据；Phase 1b 由 chart_recommend 与 ChartRenderer 实际委托 render。
    """

    def __init__(
        self,
        chart_type: str,
        display_name: str,
        description: str,
        title_template: str = "",
        config: Dict[str, Any] | None = None,
    ) -> None:
        self.chart_type = chart_type
        self._title_template = title_template
        self._config = config or {}
        self.meta = SkillMeta(
            id=f"chart:{chart_type}",
            name=display_name,
            description=description,
            tags=["chart"],
            depends_on=[],
            capability=SkillCapability(duckdb=True),
            panel_kind="chart",
            input_schema={"field_combo": "object"},
            output_schema={"chart_type": "string", "config": "object"},
        )

    async def run(self, ctx: SkillContext) -> SkillResult:
        # Phase 1a：返回该图表类型的元数据模板（前端 / S3 委托时的能力描述）
        return SkillResult(
            skill_id=self.meta.id,
            ok=True,
            data={
                "chart_type": self.chart_type,
                "title_template": self._title_template,
                "config": self._config,
            },
        )


def register_chart_skills(reg: SkillRegistry) -> int:
    """从 yaml 加载并注册所有 chart:<type> skill，返回注册数量。"""
    types = _load_chart_types()
    count = 0
    for ctype, info in types.items():
        display = _DISPLAY_NAMES.get(ctype, ctype)
        desc = f"{display}：{info.get('rule_name', '')}（来自 s3_chart_rules.yaml）"
        reg.register(
            ChartSkill(
                ctype,
                display,
                desc,
                info.get("title_template", ""),
                info.get("config"),
            )
        )
        count += 1
    return count
