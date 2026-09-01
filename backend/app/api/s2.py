"""
S2 目标生成器 API - M2-04
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.brain_modules.s2_goal_generator import S2GoalGenerator, generate_analysis_goals

router = APIRouter(prefix="/brain/s2", tags=["S2-目标生成"])


class GoalGenerateRequest(BaseModel):
    """目标生成请求"""
    dataset_id: str
    theme: str = Field(..., description="数据主题（如：担保风控）")
    fields: List[str] = Field(..., description="字段列表")
    grain: str = Field("detail", description="数据粒度：detail/macro")
    use_llm: bool = Field(False, description="是否使用LLM增强（默认False降本）")
    sample_data: Optional[List[Dict[str, Any]]] = None


class GoalGenerateResponse(BaseModel):
    """目标生成响应"""
    success: bool
    dataset_id: str
    theme: str
    goal_count: int
    goals: List[Dict[str, Any]]
    method: str  # rule_based / llm_enhanced


class V2TableGoalRequest(BaseModel):
    """v2五表目标生成请求"""
    table_type: str = Field(..., pattern="^(01|02|03|04|05)$")
    dataset_id: str
    fields: List[str]


@router.post("/generate", response_model=GoalGenerateResponse)
async def generate_goals(
    request: GoalGenerateRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    生成分析目标
    
    生成6个候选目标，包含：
    - 中文业务化表述（避免技术术语）
    - KPI/趋势/对比/分布/预警/画像/关联 等类型
    """
    generator = S2GoalGenerator()
    goals = await generator.generate(
        db=db,
        theme=request.theme,
        fields=request.fields,
        grain=request.grain,
        use_llm=request.use_llm,
        sample_data=request.sample_data
    )
    
    return GoalGenerateResponse(
        success=True,
        dataset_id=request.dataset_id,
        theme=request.theme,
        goal_count=len(goals),
        goals=[g.to_dict() for g in goals],
        method="llm_enhanced" if request.use_llm else "rule_based"
    )


@router.post("/generate-v2-table", response_model=GoalGenerateResponse)
async def generate_v2_table_goals(
    request: V2TableGoalRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    v2五表目标生成
    
    根据表类型自动映射主题：
    - 01/05表 → 担保风控
    - 02表 → 客户画像
    - 03表 → 逾期分析
    - 04表 → 产品分析
    """
    theme_map = {
        "01": "担保风控",
        "02": "客户画像",
        "03": "逾期分析",
        "04": "产品分析",
        "05": "担保风控"
    }
    
    theme = theme_map.get(request.table_type, "担保风控")
    
    generator = S2GoalGenerator()
    goals = await generator.generate(
        db=db,
        theme=theme,
        fields=request.fields,
        grain="detail"
    )
    
    return GoalGenerateResponse(
        success=True,
        dataset_id=request.dataset_id,
        theme=theme,
        goal_count=len(goals),
        goals=[g.to_dict() for g in goals],
        method="rule_based"
    )


@router.get("/prompt-template")
async def get_prompt_template(db: AsyncSession = Depends(get_db)):
    """获取当前目标生成Prompt模板"""
    from app.core.brain_config_manager import BrainConfigManager
    
    config = await BrainConfigManager.get_config(db, "goal_prompt_v1")
    
    if config:
        return {
            "success": True,
            "template_key": "goal_prompt_v1",
            "version": config.get("version", 1),
            "template": config.get("content", {}).get("template", "")
        }
    
    # 返回默认模板
    generator = S2GoalGenerator()
    return {
        "success": True,
        "template_key": "goal_prompt_v1",
        "version": 1,
        "template": generator._default_prompt_template(),
        "source": "default"
    }


@router.post("/_internal/test-v2-tables")
async def test_v2_table_goals(db: AsyncSession = Depends(get_db)):
    """
    测试v2五表目标生成
    
    验证01表产出目标包含：
    - 逾期监控
    - 地区对比
    - 抵押风险
    """
    test_cases = [
        ("01", ["借据编号", "担保金额", "抵押率", "质押物", "地区", "逾期天数"]),
        ("02", ["客户编号", "客户名称", "客户类型", "注册地区"]),
        ("03", ["月份", "逾期金额", "逾期天数", "不良率", "地区"]),
        ("04", ["产品类型", "贷款品种", "合同金额", "收益率"]),
        ("05", ["担保编号", "担保方式", "担保金额", "抵押物名称", "地区"])
    ]
    
    results = []
    for table_type, fields in test_cases:
        goals = await generate_analysis_goals(
            db=db,
            theme={"01": "担保风控", "02": "客户画像", "03": "逾期分析", "04": "产品分析", "05": "担保风控"}[table_type],
            fields=fields
        )
        
        # 检查目标类型覆盖
        types = [g["type"] for g in goals]
        has_required = all(t in types for t in ["趋势", "对比", "分布"])
        
        # 01表特殊检查
        if table_type == "01":
            titles = [g["title"] for g in goals]
            has_theme_keywords = any(k in " ".join(titles) for k in ["逾期", "地区", "抵押", "风险", "担保"])
        else:
            has_theme_keywords = True
        
        results.append({
            "table_type": table_type,
            "goal_count": len(goals),
            "goals": goals,
            "types": types,
            "has_required_types": has_required,
            "has_theme_keywords": has_theme_keywords,
            "passed": has_required and has_theme_keywords
        })
    
    all_passed = all(r["passed"] for r in results)
    
    return {
        "success": True,
        "all_passed": all_passed,
        "results": results
    }


@router.get("/types")
async def get_goal_types():
    """获取目标类型说明"""
    return {
        "success": True,
        "types": [
            {"code": "KPI", "name": "关键指标", "description": "核心数值指标，如总额、数量"},
            {"code": "趋势", "name": "趋势分析", "description": "时间序列变化趋势"},
            {"code": "对比", "name": "对比分析", "description": "不同维度间的对比"},
            {"code": "分布", "name": "分布分析", "description": "数据分布特征"},
            {"code": "预警", "name": "风险预警", "description": "异常识别和预警"},
            {"code": "画像", "name": "画像分析", "description": "对象特征画像"},
            {"code": "关联", "name": "关联分析", "description": "因素间关联关系"}
        ]
    }