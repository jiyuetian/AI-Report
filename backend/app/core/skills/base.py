"""Skill 统一协议：所有分析能力（S1~S5、质检、图表、报告、导出、派生指标、可行性等）薄封装为此基类。

设计原则：薄封装——现有类内部逻辑一行不改，只补元数据 + 统一 run(ctx) 入口。
详见 docs/组件化改造设计文档_2026-09-18.md（v0.2-aligned）。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SkillCapability:
    """能力标签，供 Planner 剪枝（复用现有 health 探测结果）"""

    llm: bool = False  # 是否依赖 LLM（不可达时跳过）
    duckdb: bool = False  # 是否依赖 DuckDB
    write: bool = False  # 是否写数据层（决定执行顺序/事务边界）


@dataclass
class SkillMeta:
    id: str
    name: str
    description: str  # 给 Planner / 未来 LLM 规划器读的自然语言描述
    tags: List[str] = field(default_factory=list)  # ["understand","chart","quality","clean","lineage","report","export","derived","feasibility"]
    depends_on: List[str] = field(default_factory=list)  # 上游 skill id（用于拓扑排序）
    capability: SkillCapability = field(default_factory=SkillCapability)
    input_schema: Dict[str, Any] = field(default_factory=dict)  # JSON schema（轻量，先 Dict 后接 pydantic）
    output_schema: Dict[str, Any] = field(default_factory=dict)
    # v0.2 加分：前端 UI 元数据，SkillPanel 直接消费
    panel_kind: Optional[str] = None  # "quality"|"chart"|"lineage"|"appendix"|"report"|"admin"
    visible_when: Optional[str] = None  # 可选谓词名，如 "has_dashboard"


@dataclass
class SkillContext:
    db: Any  # AsyncSession
    duck: Any  # DuckDBManager
    dataset_id: str
    user_id: str
    run_id: str
    shared: Dict[str, Any] = field(default_factory=dict)  # 跨 skill 传递中间产物
    capability_profile: Dict[str, Any] = field(default_factory=dict)  # health probe 结果（llm_reachable 等）


@dataclass
class SkillResult:
    skill_id: str
    ok: bool
    data: Dict[str, Any] = field(default_factory=dict)
    trace: Dict[str, Any] = field(default_factory=dict)  # 回写 brain_traces.stage_output
    skipped: bool = False
    skip_reason: str = ""


class Skill(ABC):
    meta: SkillMeta

    @abstractmethod
    async def run(self, ctx: SkillContext) -> SkillResult:
        ...
