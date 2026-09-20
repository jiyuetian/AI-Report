"""
策略大脑API V2 - M2-01
brain_configs: 配置存储+版本+热更新+回滚
brain_traces: 五阶段全链路trace落库
"""
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.brain_config_manager import BrainConfigManager, BrainTraceManager
from app.models.brain import BrainConfig, BrainTrace, BrainTraceSummary
import uuid

router = APIRouter(prefix="/brain", tags=["Brain V2"])


# ============== 配置管理模型 ==============

class ConfigCreateRequest(BaseModel):
    config_key: str = Field(..., description="配置键，如: theme_dict, goal_prompt")
    category: str = Field(..., description="配置类别: theme/goal/chart/orchestrate/score")
    content: Dict[str, Any] = Field(..., description="配置内容")
    description: str = Field("", description="配置说明")


class ConfigUpdateRequest(BaseModel):
    content: Dict[str, Any] = Field(..., description="新配置内容")
    description: str = Field("", description="配置说明")


class ConfigResponse(BaseModel):
    success: bool
    config_key: str
    version: int
    message: str


# ============== Trace模型 ==============

class StartRunRequest(BaseModel):
    dataset_id: str
    user_id: str = "anonymous"


class StartStageRequest(BaseModel):
    run_id: str
    dataset_id: str
    stage: str = Field(..., pattern="^(S1|S2|S3|S4|S5)$")
    stage_input: Dict[str, Any]


class CompleteStageRequest(BaseModel):
    trace_id: str
    stage_output: Dict[str, Any]
    stage_metrics: Optional[Dict[str, Any]] = None


class CompleteRunRequest(BaseModel):
    run_id: str
    dashboard_id: Optional[str] = None
    final_score: Optional[int] = None
    passed: bool = False


# ============== 配置管理API ==============

@router.get("/configs", response_model=Dict)
async def list_configs(
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    获取所有生效配置
    
    支持按类别过滤
    """
    if category:
        configs = await BrainConfigManager.get_configs_by_category(db, category)
    else:
        # 获取所有生效配置
        from sqlalchemy import select, and_
        result = await db.execute(
            select(BrainConfig).where(BrainConfig.is_active == 1)
        )
        configs = [c.to_dict() for c in result.scalars().all()]
    
    return {
        "success": True,
        "count": len(configs),
        "configs": configs
    }


@router.get("/configs/{config_key}", response_model=Dict)
async def get_config(
    config_key: str,
    db: AsyncSession = Depends(get_db)
):
    """
    获取指定配置（带热更新缓存）
    
    流程：
    1. 查Redis缓存
    2. 未命中查DB
    3. 写入缓存
    """
    config = await BrainConfigManager.get_config(db, config_key)
    
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CONFIG_NOT_FOUND", "message": f"配置不存在: {config_key}"}
        )
    
    return {
        "success": True,
        "config": config
    }


@router.post("/configs", response_model=Dict)
async def create_or_update_config(
    request: ConfigCreateRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    创建/更新配置（热更新）
    
    关键特性：
    1. 自动版本递增
    2. 旧版本自动标记为历史
    3. 清除缓存，下次请求立即生效
    """
    result = await BrainConfigManager.update_config(
        db=db,
        config_key=request.config_key,
        content=request.content,
        category=request.category,
        description=request.description
    )
    
    return result


@router.post("/configs/{config_key}/rollback", response_model=Dict)
async def rollback_config(
    config_key: str,
    target_version: int,
    db: AsyncSession = Depends(get_db)
):
    """
    回滚配置到指定版本
    
    热更新：回滚后立即生效
    """
    result = await BrainConfigManager.rollback_config(db, config_key, target_version)
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "ROLLBACK_FAILED", "message": result["error"]}
        )
    
    return result


@router.get("/configs/{config_key}/history", response_model=Dict)
async def get_config_history(
    config_key: str,
    db: AsyncSession = Depends(get_db)
):
    """获取配置变更历史（所有版本）"""
    history = await BrainConfigManager.get_config_history(db, config_key)
    
    return {
        "success": True,
        "config_key": config_key,
        "version_count": len(history),
        "history": history
    }


# ============== Trace管理API ==============

@router.post("/trace/run/start", response_model=Dict)
async def start_run(
    request: StartRunRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    开始一次策略大脑运行
    
    创建run_id和汇总记录
    """
    run_id = str(uuid.uuid4())
    
    await BrainTraceManager.start_run(
        db=db,
        run_id=run_id,
        dataset_id=request.dataset_id,
        user_id=request.user_id
    )
    
    return {
        "success": True,
        "run_id": run_id,
        "dataset_id": request.dataset_id,
        "status": "started"
    }


@router.post("/trace/stage/start", response_model=Dict)
async def start_stage(
    request: StartStageRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    开始一个阶段（S1-S5）
    
    创建trace记录
    """
    trace_id = await BrainTraceManager.start_stage(
        db=db,
        run_id=request.run_id,
        dataset_id=request.dataset_id,
        stage=request.stage,
        stage_input=request.stage_input
    )
    
    # 更新汇总表阶段状态
    await BrainTraceManager.update_stage_status(
        db=db,
        run_id=request.run_id,
        stage=request.stage,
        status="running"
    )
    
    return {
        "success": True,
        "trace_id": trace_id,
        "run_id": request.run_id,
        "stage": request.stage,
        "stage_name": BrainTraceManager.STAGE_NAMES.get(request.stage, "")
    }


@router.post("/trace/stage/complete", response_model=Dict)
async def complete_stage(
    request: CompleteStageRequest,
    db: AsyncSession = Depends(get_db)
):
    """完成一个阶段"""
    await BrainTraceManager.complete_stage(
        db=db,
        trace_id=request.trace_id,
        stage_output=request.stage_output,
        stage_metrics=request.stage_metrics
    )
    
    return {
        "success": True,
        "trace_id": request.trace_id,
        "status": "completed"
    }


@router.post("/trace/run/complete", response_model=Dict)
async def complete_run(
    request: CompleteRunRequest,
    db: AsyncSession = Depends(get_db)
):
    """完成整个运行"""
    await BrainTraceManager.complete_run(
        db=db,
        run_id=request.run_id,
        dashboard_id=request.dashboard_id,
        final_score=request.final_score,
        passed=request.passed
    )
    
    return {
        "success": True,
        "run_id": request.run_id,
        "status": "completed",
        "passed": request.passed
    }


@router.get("/trace/{run_id}", response_model=Dict)
async def get_run_traces(
    run_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    获取一次运行的完整trace
    
    包含5个阶段的详细记录
    """
    traces = await BrainTraceManager.get_run_traces(db, run_id)
    summary = await BrainTraceManager.get_run_summary(db, run_id)
    
    return {
        "success": True,
        "run_id": run_id,
        "summary": summary,
        "traces": traces,
        "stage_count": len(traces)
    }


@router.get("/trace/{run_id}/summary", response_model=Dict)
async def get_run_summary(
    run_id: str,
    db: AsyncSession = Depends(get_db)
):
    """获取运行汇总信息"""
    summary = await BrainTraceManager.get_run_summary(db, run_id)
    
    if not summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RUN_NOT_FOUND", "message": f"运行记录不存在: {run_id}"}
        )
    
    return {
        "success": True,
        "summary": summary
    }


# ============== 初始化数据 ==============

@router.post("/_internal/init-configs")
async def init_default_configs(db: AsyncSession = Depends(get_db)):
    """
    初始化默认配置（内部接口）
    
    包含五模块所需的所有配置：
    - 主题词典 (S1)
    - 目标Prompt (S2)
    - 图表规则 (S3)
    - 编排规则 (S4)
    - 评分权重 (S5)
    """
    default_configs = [
        {
            "config_key": "theme_dict",
            "category": "theme",
            "content": {
                "担保风控": ["担保", "抵押", "质押", "保证", "留置"],
                "逾期分析": ["逾期", "违约", "不良", "坏账", "呆账"],
                "地区分布": ["地区", "省份", "城市", "区域"],
                "客户画像": ["客户", "借款人", "企业", "个人"],
                "产品分析": ["产品", "贷款", "借据", "合同"]
            },
            "description": "主题识别词典 - S1模块"
        },
        {
            "config_key": "goal_prompt_v1",
            "category": "goal",
            "content": {
                "template": """你是一位资深风控分析师。请根据以下数据信息，生成6个候选分析目标：

数据主题: {{theme}}
数据粒度: {{grain}}
字段列表: {{fields}}

要求：
1. 目标必须是中文业务化表述，避免技术术语
2. 包含至少1个KPI类、1个趋势类、1个对比类目标
3. 目标应具体可操作

输出格式：JSON数组，每个元素包含goal_id, title, description, type""",
                "version": "1.0"
            },
            "description": "目标生成Prompt模板 V1 - S2模块"
        },
        {
            "config_key": "chart_rules",
            "category": "chart",
            "content": {
                "rules": [
                    {"field_types": ["date", "number"], "chart_types": ["line", "bar"]},
                    {"field_types": ["category", "number"], "chart_types": ["bar", "pie"], "max_categories": 8},
                    {"field_types": ["number", "number"], "chart_types": ["scatter"]},
                    {"grain": "macro", "max_detail_level": "aggregate"},
                    {"grain": "detail", "allow_table": True}
                ],
                "fallback_chart": "table"
            },
            "description": "图表推荐规则 - S3模块"
        },
        {
            "config_key": "orchestrate_rules",
            "category": "orchestrate",
            "content": {
                "max_kpi_cards": 4,
                "max_charts": 6,
                "narrative_order": ["conclusion", "evidence", "detail"],
                "redundancy_threshold": 0.8
            },
            "description": "编排规则 - S4模块"
        },
        {
            "config_key": "score_weights",
            "category": "score",
            "content": {
                "weights": {
                    "redundancy": 0.3,
                    "coverage": 0.4,
                    "narrative": 0.3
                },
                "pass_threshold": 70,
                "max_retries": 3
            },
            "description": "评分卡权重配置 - S5模块"
        }
    ]
    
    created = []
    for cfg in default_configs:
        result = await BrainConfigManager.update_config(
            db=db,
            config_key=cfg["config_key"],
            category=cfg["category"],
            content=cfg["content"],
            description=cfg["description"]
        )
        created.append(result)
    
    return {
        "success": True,
        "message": f"已初始化 {len(created)} 个默认配置",
        "configs": created
    }