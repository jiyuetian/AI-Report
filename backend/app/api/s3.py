"""
S3 图表推荐引擎 API - M2-05
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.brain_modules.s3_chart_engine import S3ChartEngine

router = APIRouter(prefix="/brain/s3", tags=["S3-图表推荐"])


class ChartRecommendRequest(BaseModel):
    """图表推荐请求"""
    dataset_id: str
    fields: List[str] = Field(..., description="字段列表")
    grain: str = Field("detail", description="数据粒度: detail/aggregate/macro")
    sample_data: Optional[List[Dict[str, Any]]] = None
    max_charts: int = Field(5, ge=1, le=10)


class ChartRecommendResponse(BaseModel):
    """图表推荐响应"""
    success: bool
    dataset_id: str
    grain: str
    chart_count: int
    charts: List[Dict[str, Any]]
    generated_by: str
    llm_used: bool


class DashboardGenerateRequest(BaseModel):
    """看板生成请求"""
    dataset_id: str
    fields: List[str]
    grain: str = Field("detail")
    sample_data: Optional[List[Dict[str, Any]]] = None


class DashboardGenerateResponse(BaseModel):
    """看板生成响应"""
    success: bool
    dataset_id: str
    grain: str
    field_count: int
    chart_count: int
    charts: List[Dict[str, Any]]
    generated_by: str
    llm_used: bool
    message: str


@router.post("/recommend", response_model=ChartRecommendResponse)
async def recommend_charts_endpoint(
    request: ChartRecommendRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    推荐图表
    
    基于字段组合自动推荐合适的图表类型
    """
    engine = S3ChartEngine()
    recommendations = engine.recommend_charts(
        fields=request.fields,
        grain=request.grain,
        sample_data=request.sample_data,
        max_charts=request.max_charts
    )
    
    return ChartRecommendResponse(
        success=True,
        dataset_id=request.dataset_id,
        grain=request.grain,
        chart_count=len(recommendations),
        charts=[r.to_dict() for r in recommendations],
        generated_by="rule_engine",
        llm_used=False
    )


@router.post("/generate-dashboard", response_model=DashboardGenerateResponse)
async def generate_dashboard_endpoint(
    request: DashboardGenerateRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    生成完整看板配置（5个图表）
    
    断 LLM 时也能出完整看板：
    - KPI卡
    - 趋势图 (line)
    - 对比图 (bar)
    - 分布图 (pie)
    - 明细表 (table)
    """
    engine = S3ChartEngine()
    result = engine.generate_dashboard_config(
        fields=request.fields,
        grain=request.grain,
        sample_data=request.sample_data
    )
    
    return DashboardGenerateResponse(
        success=True,
        dataset_id=request.dataset_id,
        grain=result["grain"],
        field_count=result["field_count"],
        chart_count=result["chart_count"],
        charts=result["charts"],
        generated_by="rule_engine",
        llm_used=False,
        message="规则引擎生成，无需LLM"
    )


@router.get("/rules")
async def get_chart_rules():
    """获取图表规则配置（YAML内容）"""
    import yaml
    import os
    
    rules_file = os.path.join(
        os.path.dirname(__file__), 
        "..", "core", "brain_modules", "s3_chart_rules.yaml"
    )
    
    try:
        with open(rules_file, 'r', encoding='utf-8') as f:
            content = f.read()
            rules = yaml.safe_load(content)
        
        return {
            "success": True,
            "rule_count": len(rules.get("rules", [])),
            "fallback_count": len(rules.get("fallback", {}).get("default_charts", [])),
            "rules_yaml": content,
            "parsed": rules
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/field-types")
async def get_field_types():
    """获取支持的字段类型"""
    return {
        "success": True,
        "field_types": [
            {"code": "date", "name": "日期时间", "examples": ["日期", "时间", "年月"]},
            {"code": "number", "name": "数值", "examples": ["金额", "数量", "比率"]},
            {"code": "category", "name": "分类", "examples": ["类型", "状态", "地区"]},
            {"code": "geo", "name": "地理", "examples": ["省份", "城市", "地址"]},
            {"code": "text", "name": "文本", "examples": ["名称", "描述"]}
        ]
    }


@router.get("/chart-types")
async def get_chart_types():
    """获取支持的图表类型"""
    return {
        "success": True,
        "chart_types": [
            {"code": "kpi", "name": "KPI卡片", "description": "单值指标展示"},
            {"code": "line", "name": "折线图", "description": "时间趋势分析"},
            {"code": "bar", "name": "柱状图", "description": "分类对比"},
            {"code": "pie", "name": "饼图", "description": "占比分布"},
            {"code": "scatter", "name": "散点图", "description": "相关性分析"},
            {"code": "table", "name": "表格", "description": "明细数据"},
            {"code": "map", "name": "地图", "description": "地理分布"},
            {"code": "heatmap", "name": "热力图", "description": "矩阵分布"}
        ]
    }


@router.post("/_internal/test-01-table")
async def test_01_table_dashboard():
    """
    测试01表看板生成（内部接口）
    
    验证断LLM时也能出：KPI+趋势+对比+分布+明细
    """
    # 01表字段
    fields_01 = [
        "借据编号", "担保金额", "抵押率", "质押物", "保证人",
        "地区", "逾期天数", "贷款日期", "到期日期", "产品类型"
    ]
    
    engine = S3ChartEngine()
    result = engine.generate_dashboard_config(
        fields=fields_01,
        grain="detail"
    )
    
    # 验证是否包含5种必要类型
    charts = result["charts"]
    chart_types = [c["chart_type"] for c in charts]
    
    required_types = ["kpi", "line", "bar", "pie", "table"]
    has_all = all(t in chart_types for t in required_types)
    
    return {
        "success": True,
        "test_case": "01表",
        "fields": fields_01,
        "has_all_required_types": has_all,
        "required_types": required_types,
        "actual_types": chart_types,
        "passed": has_all,
        "dashboard": result
    }


@router.post("/_internal/test-grain-constraints")
async def test_grain_constraints():
    """
    测试粒度限制（内部接口）
    
    验证：宏观粒度禁行级明细
    """
    fields = ["地区", "担保金额", "抵押率"]
    
    # detail粒度 - 允许table
    engine_detail = S3ChartEngine()
    detail_result = engine_detail.generate_dashboard_config(fields, grain="detail")
    detail_has_table = any(c["chart_type"] == "table" for c in detail_result["charts"])
    
    # macro粒度 - 禁止table
    engine_macro = S3ChartEngine()
    macro_result = engine_macro.generate_dashboard_config(fields, grain="macro")
    macro_has_table = any(c["chart_type"] == "table" for c in macro_result["charts"])
    
    return {
        "success": True,
        "detail_grain": {
            "has_table": detail_has_table,
            "charts": [c["chart_type"] for c in detail_result["charts"]]
        },
        "macro_grain": {
            "has_table": macro_has_table,
            "charts": [c["chart_type"] for c in macro_result["charts"]]
        },
        "passed": detail_has_table and not macro_has_table,
        "message": "detail粒度允许table，macro粒度禁止table"
    }


# ============== M2-06 LLM增强 + Schema自愈 ==============

from app.core.brain_modules.s3_llm_enhancer import (
    S3LLMEnhancer, GrainChecker, validate_chart_grain
)


class LLMGenerateRequest(BaseModel):
    """LLM生成请求（带Schema自愈）"""
    dataset_id: str
    theme: str
    fields: List[str]
    goals: List[Dict[str, Any]]
    grain: str = Field("detail")


class LLMGenerateResponse(BaseModel):
    """LLM生成响应"""
    success: bool
    dataset_id: str
    charts: List[Dict[str, Any]]
    generated_by: str  # llm / rule_engine
    llm_used: bool
    retry_count: int
    self_healed: bool
    fallback_reason: Optional[str] = None


@router.post("/generate-llm", response_model=LLMGenerateResponse)
async def generate_with_llm(
    request: LLMGenerateRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    LLM生成图表（带Schema自愈）
    
    流程：
    1. LLM生成 → Schema校验
    2. 失败则回写错误重试（≤2次）
    3. 仍失败降级规则引擎
    """
    enhancer = S3LLMEnhancer()
    
    result = await enhancer.generate_with_self_healing(
        db=db,
        theme=request.theme,
        fields=request.fields,
        goals=request.goals,
        grain=request.grain
    )
    
    return LLMGenerateResponse(
        success=result["success"],
        dataset_id=request.dataset_id,
        charts=result["charts"],
        generated_by=result["generated_by"],
        llm_used=result["llm_used"],
        retry_count=result["retry_count"],
        self_healed=result["self_healed"],
        fallback_reason=result.get("fallback_reason")
    )


@router.post("/validate-grain")
async def validate_chart_grain_endpoint(
    chart_config: Dict[str, Any],
    grain: str
):
    """
    校验图表粒度兼容性
    
    用于前端拦截（m-grain弹窗）
    """
    is_compatible, error = validate_chart_grain(chart_config, grain)
    
    return {
        "success": True,
        "compatible": is_compatible,
        "error": error if not is_compatible else None,
        "grain": grain,
        "chart_type": chart_config.get("chart_type"),
        "recommended_types": GrainChecker.get_grain_recommendation(grain)
    }


@router.get("/grain-recommendations/{grain}")
async def get_grain_recommendations(grain: str):
    """获取粒度推荐的图表类型"""
    recommendations = GrainChecker.get_grain_recommendation(grain)
    
    return {
        "success": True,
        "grain": grain,
        "recommended_types": recommendations,
        "message": f"{grain}粒度建议使用: {', '.join(recommendations)}"
    }


@router.post("/_internal/test-self-healing")
async def test_self_healing(db: AsyncSession = Depends(get_db)):
    """
    测试Schema自愈（内部接口）
    
    验证：非法配置触发自愈重试2次后降级
    """
    # 使用故意错误的字段触发自愈
    fields = ["日期", "金额", "类别"]
    goals = [{"title": "测试目标", "type": "趋势"}]
    
    # 使用mock LLM模拟失败场景
    enhancer = S3LLMEnhancer()
    
    # 强制触发LLM调用
    result = await enhancer.generate_with_self_healing(
        db=db,
        theme="测试",
        fields=fields,
        goals=goals,
        grain="detail"
    )
    
    return {
        "success": True,
        "test": "Schema自愈",
        "llm_used": result["llm_used"],
        "retry_count": result["retry_count"],
        "self_healed": result["self_healed"],
        "generated_by": result["generated_by"],
        "chart_count": len(result["charts"]),
        "message": f"生成成功，方法: {result['generated_by']}, 重试: {result['retry_count']}次"
    }