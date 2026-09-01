"""
S4 编排器 + S5 评分卡 API - M2-07
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.brain_modules.s4_orchestrator import (
    S4Orchestrator, S5ScoreCard, orchestrate_and_score
)

router = APIRouter(prefix="/brain", tags=["S4-S5-编排评分"])


# ============== 请求/响应模型 ==============

class OrchestrateRequest(BaseModel):
    """编排请求"""
    dataset_id: str
    charts: List[Dict[str, Any]]
    max_charts: int = Field(6, ge=3, le=10)


class OrchestrateResponse(BaseModel):
    """编排响应"""
    success: bool
    dataset_id: str
    charts: List[Dict[str, Any]]
    chart_count: int
    kpi_count: int
    layers: Dict[str, List[Dict]]
    narrative_flow: str


class ScoreRequest(BaseModel):
    """评分请求"""
    dataset_id: str
    charts: List[Dict[str, Any]]


class ScoreResponse(BaseModel):
    """评分响应"""
    success: bool
    dataset_id: str
    overall_score: float
    passed: bool
    dimension_scores: Dict[str, float]
    chart_scores: List[Dict[str, Any]]
    retry_count: int
    improvement_suggestions: List[str]


class OrchestrateAndScoreRequest(BaseModel):
    """编排+评分请求"""
    dataset_id: str
    charts: List[Dict[str, Any]]


class OrchestrateAndScoreResponse(BaseModel):
    """编排+评分响应"""
    success: bool
    dataset_id: str
    charts: List[Dict[str, Any]]
    chart_count: int
    overall_score: float
    passed: bool
    dimension_scores: Dict[str, float]
    retry_count: int


# ============== API端点 ==============

@router.post("/s4/orchestrate", response_model=OrchestrateResponse)
async def orchestrate_endpoint(
    request: OrchestrateRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    S4 编排器
    
    功能：
    1. KPI挑选（最多4个）
    2. 去冗余
    3. 三层叙事组织（结论→佐证→明细）
    """
    orchestrator = S4Orchestrator()
    
    result = orchestrator.orchestrate(request.charts, request.max_charts)
    
    return OrchestrateResponse(
        success=True,
        dataset_id=request.dataset_id,
        charts=result["charts"],
        chart_count=result["chart_count"],
        kpi_count=result["kpi_count"],
        layers=result["layers"],
        narrative_flow=result["narrative_flow"]
    )


@router.post("/s5/score", response_model=ScoreResponse)
async def score_endpoint(
    request: ScoreRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    S5 评分卡
    
    评分维度：
    - redundancy: 冗余度（30%）
    - coverage: 覆盖度（40%）
    - narrative: 叙事性（30%）
    
    通过标准：≥70分
    """
    scorer = S5ScoreCard()
    await scorer.load_config(db)
    
    score = scorer.score_dashboard(request.charts)
    
    return ScoreResponse(
        success=True,
        dataset_id=request.dataset_id,
        overall_score=round(score.overall_score, 2),
        passed=score.passed,
        dimension_scores={k: round(v, 2) for k, v in score.dimension_scores.items()},
        chart_scores=[c.to_dict() for c in score.chart_scores],
        retry_count=score.retry_count,
        improvement_suggestions=score.improvement_suggestions
    )


@router.post("/s4s5/orchestrate-and-score", response_model=OrchestrateAndScoreResponse)
async def orchestrate_and_score_endpoint(
    request: OrchestrateAndScoreRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    S4+S5 编排+评分（带重试）
    
    如果评分<70，最多重排3次
    """
    result = await orchestrate_and_score(db, request.charts)
    
    score = result["score"]
    
    return OrchestrateAndScoreResponse(
        success=True,
        dataset_id=request.dataset_id,
        charts=result["charts"],
        chart_count=result["chart_count"],
        overall_score=round(score["overall_score"], 2),
        passed=score["passed"],
        dimension_scores={k: round(v, 2) for k, v in score["dimension_scores"].items()},
        retry_count=score["retry_count"]
    )


@router.get("/s5/score-config")
async def get_score_config(db: AsyncSession = Depends(get_db)):
    """获取评分配置"""
    scorer = S5ScoreCard()
    await scorer.load_config(db)
    
    return {
        "success": True,
        "weights": scorer.weights,
        "pass_threshold": scorer.pass_threshold,
        "max_retries": scorer.max_retries,
        "message": f"通过标准: ≥{scorer.pass_threshold}分"
    }


@router.post("/_internal/test-score")
async def test_score_calculation(db: AsyncSession = Depends(get_db)):
    """
    测试评分计算（内部接口）
    
    验证：
    1. 评分计算正确
    2. dashboards.score 字段更新
    """
    # 测试图表
    test_charts = [
        {"chart_type": "kpi", "title": "总担保金额", "x_field": None, "y_field": "担保金额"},
        {"chart_type": "line", "title": "担保趋势", "x_field": "日期", "y_field": "担保金额"},
        {"chart_type": "bar", "title": "地区对比", "x_field": "地区", "y_field": "担保金额"},
        {"chart_type": "pie", "title": "类型分布", "x_field": "类型", "y_field": "担保金额"},
        {"chart_type": "table", "title": "明细", "x_field": None, "y_field": None}
    ]
    
    scorer = S5ScoreCard()
    await scorer.load_config(db)
    score = scorer.score_dashboard(test_charts)
    
    return {
        "success": True,
        "test_charts_count": len(test_charts),
        "overall_score": round(score.overall_score, 2),
        "passed": score.passed,
        "dimension_scores": {k: round(v, 2) for k, v in score.dimension_scores.items()},
        "suggestions": score.improvement_suggestions,
        "expected_passed": score.overall_score >= 70
    }


@router.post("/_internal/test-orchestrate")
async def test_orchestrate():
    """
    测试编排（内部接口）
    
    验证：
    1. KPI挑选
    2. 去冗余
    3. 三层叙事
    """
    # 测试图表（含冗余）
    test_charts = [
        {"chart_type": "kpi", "title": "总担保金额", "x_field": None, "y_field": "担保金额"},
        {"chart_type": "kpi", "title": "总笔数", "x_field": None, "y_field": "笔数"},
        {"chart_type": "line", "title": "趋势1", "x_field": "日期", "y_field": "金额"},
        {"chart_type": "line", "title": "趋势2", "x_field": "日期", "y_field": "金额"},  # 冗余
        {"chart_type": "bar", "title": "对比", "x_field": "地区", "y_field": "金额"},
        {"chart_type": "pie", "title": "分布", "x_field": "类型", "y_field": "金额"},
        {"chart_type": "table", "title": "明细", "x_field": None, "y_field": None}
    ]
    
    orchestrator = S4Orchestrator()
    result = orchestrator.orchestrate(test_charts, max_charts=5)
    
    return {
        "success": True,
        "input_count": len(test_charts),
        "output_count": result["chart_count"],
        "kpi_count": result["kpi_count"],
        "layers": {
            "L1": len(result["layers"]["L1_conclusion"]),
            "L2": len(result["layers"]["L2_evidence"]),
            "L3": len(result["layers"]["L3_detail"])
        },
        "narrative_flow": result["narrative_flow"]
    }


@router.post("/_internal/test-retry")
async def test_retry_mechanism(db: AsyncSession = Depends(get_db)):
    """
    测试重排机制（内部接口）
    
    验证：评分<70时触发重排
    """
    # 低分图表（大量冗余）
    low_score_charts = [
        {"chart_type": "line", "title": "趋势", "x_field": "日期", "y_field": "金额"},
        {"chart_type": "line", "title": "同样的趋势", "x_field": "日期", "y_field": "金额"},  # 冗余
        {"chart_type": "line", "title": "还是趋势", "x_field": "日期", "y_field": "金额"},   # 冗余
    ]
    
    orchestrator = S4Orchestrator()
    scorer = S5ScoreCard()
    await scorer.load_config(db)
    
    score, final_charts = await scorer.score_with_retry(db, orchestrator, low_score_charts)
    
    return {
        "success": True,
        "input_count": len(low_score_charts),
        "output_count": len(final_charts),
        "retry_count": score.retry_count,
        "overall_score": round(score.overall_score, 2),
        "passed": score.passed,
        "message": f"重排{score.retry_count}次后评分: {score.overall_score:.1f}"
    }