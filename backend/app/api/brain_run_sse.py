"""
/brain/run SSE - M2-08 (R1返工: 接入真实大脑)
五阶段进度流式回传（对应Loading页五阶段）
"""
import asyncio
import json
import uuid
from typing import AsyncGenerator, Dict, Any, Optional
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from datetime import datetime

from app.core.database import async_session_factory
from app.core.brain_config_manager import BrainTraceManager
from app.core.duckdb_manager import get_duckdb
from app.core.brain_modules import (
    detect_theme, generate_analysis_goals, generate_charts_with_llm,
    orchestrate_and_score
)
from app.models.dataset import Dataset
from app.models.dashboard import Dashboard
from app.models.quality import QualityIssue

router = APIRouter(prefix="/brain", tags=["Brain-Run-SSE"])


class BrainRunRequest(BaseModel):
    """Brain运行请求"""
    dataset_id: str
    user_id: str = "anonymous"


class StageProgress:
    """阶段进度"""
    def __init__(self, run_id: str, dataset_id: str):
        self.run_id = run_id
        self.dataset_id = dataset_id
        self.current_stage = ""
        self.stage_status = "idle"  # idle/running/completed/failed
        self.progress = 0
        self.message = ""
        self.detail = {}
    
    def to_event(self) -> str:
        """转换为SSE事件格式"""
        data = {
            "run_id": self.run_id,
            "dataset_id": self.dataset_id,
            "stage": self.current_stage,
            "stage_name": self._get_stage_name(self.current_stage),
            "status": self.stage_status,
            "progress": self.progress,
            "message": self.message,
            "detail": self.detail
        }
        return f"event: stage\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
    
    @staticmethod
    def _get_stage_name(stage: str) -> str:
        names = {
            "S1": "主题识别",
            "S2": "目标生成",
            "S3": "图表推荐",
            "S4": "编排优化",
            "S5": "评分验证",
            "COMPLETE": "完成"
        }
        return names.get(stage, stage)


async def get_dataset_info(db: AsyncSession, dataset_id: str) -> Dict[str, Any]:
    """从数据库获取数据集信息"""
    result = await db.execute(
        select(Dataset).where(Dataset.id == dataset_id)
    )
    dataset = result.scalar_one_or_none()
    
    if not dataset:
        raise ValueError(f"数据集不存在: {dataset_id}")
    
    fields = []
    if dataset.schema_json and "columns" in dataset.schema_json:
        fields = [col.get("name", col.get("column")) for col in dataset.schema_json["columns"]]
    
    # 从DuckDB获取样本数据
    db_duck = get_duckdb()
    table_name = f"ds_{dataset_id.replace('-', '_')}"
    sample_data = []
    if db_duck.table_exists(table_name):
        try:
            rows = db_duck.conn.execute(f'SELECT * FROM "{table_name}" LIMIT 5').fetchall()
            cols = [d[0] for d in db_duck.conn.execute(f'SELECT * FROM "{table_name}" LIMIT 0').description]
            sample_data = [dict(zip(cols, row)) for row in rows]
        except Exception as e:
            print(f"[Brain] 获取样本数据失败: {e}")
    
    return {
        "dataset_id": dataset_id,
        "fields": fields,
        "grain": dataset.grain or "detail",
        "row_count": dataset.row_count,
        "theme_hint": dataset.profile_json.get("theme") if dataset.profile_json else None,
        "sample_data": sample_data,
        "dataset_name": dataset.name or ""
    }


async def brain_run_pipeline(
    run_id: str,
    dataset_id: str,
    user_id: str
) -> AsyncGenerator[str, None]:
    """
    Brain运行管道 (接入真实大脑模块)
    
    五阶段：
    1. S1: 主题识别
    2. S2: 目标生成  
    3. S3: 图表推荐（LLM + Schema自愈）
    4. S4+S5: 编排优化+评分验证
    """
    
    async with async_session_factory() as db:
        progress = StageProgress(run_id, dataset_id)
        
        try:
            # 获取数据集信息
            dataset_info = await get_dataset_info(db, dataset_id)
            fields = dataset_info["fields"]
            grain = dataset_info["grain"]
            sample_data = dataset_info["sample_data"]
            dataset_name = dataset_info["dataset_name"]
            
            print(f"[Brain] 开始管道: dataset={dataset_id}, fields={fields}, grain={grain}")
            
            # ========== S1: 主题识别 ==========
            progress.current_stage = "S1"
            progress.stage_status = "running"
            progress.progress = 10
            progress.message = "正在分析数据主题..."
            yield progress.to_event()
            
            s1_trace_id = await BrainTraceManager.start_stage(db, run_id, dataset_id, "S1", {"fields": fields})
            s1_result = await detect_theme(
                db=db,
                fields=fields,
                sample_data=sample_data,
                dataset_name=dataset_name
            )
            await BrainTraceManager.complete_stage(db, s1_trace_id, {"result": s1_result})
            
            theme_tag = s1_result.get("theme_tag", "通用分析")
            progress.stage_status = "completed"
            progress.progress = 20
            progress.message = f"主题识别完成: {theme_tag}"
            progress.detail = s1_result
            yield progress.to_event()
            
            print(f"[Brain] S1完成: {theme_tag}")
            
            # ========== S2: 目标生成 ==========
            progress.current_stage = "S2"
            progress.stage_status = "running"
            progress.progress = 30
            progress.message = "正在生成分析目标..."
            yield progress.to_event()
            
            s2_trace_id = await BrainTraceManager.start_stage(db, run_id, dataset_id, "S2", {
                "theme": theme_tag, "fields": fields
            })
            goals = await generate_analysis_goals(
                db=db,
                theme=theme_tag,
                fields=fields,
                grain=grain,
                use_llm=False
            )
            await BrainTraceManager.complete_stage(db, s2_trace_id, {"goals": goals})
            
            goals_count = len(goals)
            progress.stage_status = "completed"
            progress.progress = 40
            progress.message = f"生成{goals_count}个分析目标"
            progress.detail = {"goals": goals, "count": goals_count}
            yield progress.to_event()
            
            print(f"[Brain] S2完成: {goals_count}个目标")
            
            # ========== S3: 图表推荐（LLM + Schema自愈） ==========
            progress.current_stage = "S3"
            progress.stage_status = "running"
            progress.progress = 50
            progress.message = "正在推荐图表..."
            yield progress.to_event()
            
            s3_trace_id = await BrainTraceManager.start_stage(db, run_id, dataset_id, "S3", {
                "theme": theme_tag, "fields": fields, "goals": goals
            })
            s3_result = await generate_charts_with_llm(
                db=db,
                theme=theme_tag,
                fields=fields,
                goals=goals,
                grain=grain
            )
            await BrainTraceManager.complete_stage(db, s3_trace_id, {"result": s3_result})
            
            charts = s3_result.get("charts", [])
            generated_by = s3_result.get("generated_by", "rule_engine")
            progress.stage_status = "completed"
            progress.progress = 60
            progress.message = f"推荐{len(charts)}个图表 ({generated_by})"
            progress.detail = s3_result
            yield progress.to_event()
            
            print(f"[Brain] S3完成: {len(charts)}个图表, source={generated_by}")
            
            # ========== S4+S5: 编排优化+评分验证 ==========
            progress.current_stage = "S4"
            progress.stage_status = "running"
            progress.progress = 70
            progress.message = "正在编排优化看板..."
            yield progress.to_event()
            
            s4_trace_id = await BrainTraceManager.start_stage(db, run_id, dataset_id, "S4", {
                "charts": charts
            })
            
            s4_s5_result = await orchestrate_and_score(
                db=db,
                charts=charts,
                dataset_id=dataset_id
            )
            
            await BrainTraceManager.complete_stage(db, s4_trace_id, {"result": s4_s5_result})
            
            final_charts = s4_s5_result.get("charts", charts)
            overall_score = s4_s5_result.get("overall_score", 0)
            passed = s4_s5_result.get("passed", False)
            
            progress.current_stage = "S5"
            progress.stage_status = "running"
            progress.progress = 85
            progress.message = f"评分中: {overall_score}分"
            progress.detail = s4_s5_result
            yield progress.to_event()
            
            s5_trace_id = await BrainTraceManager.start_stage(db, run_id, dataset_id, "S5", {
                "score": s4_s5_result.get("overall_score", 0),
                "passed": s4_s5_result.get("passed", False),
                "chart_count": len(charts)
            })
            await BrainTraceManager.complete_stage(db, s5_trace_id, {"result": s4_s5_result})
            
            progress.stage_status = "completed"
            progress.progress = 90
            progress.message = f"评分{'通过' if passed else '未通过'}: {overall_score}分"
            yield progress.to_event()
            
            print(f"[Brain] S4+S5完成: score={overall_score}, passed={passed}")
            
            # ========== 保存看板到数据库 ==========
            dashboard_id = f"dash_{dataset_id[:8]}_{uuid.uuid4().hex[:6]}"
            
            # 构建看板配置
            dashboard_config = {
                "charts": final_charts,
                "chart_count": len(final_charts),
                "theme": theme_tag,
                "goals": goals,
                "generated_by": generated_by,
                "score": {
                    "overall": overall_score,
                    "passed": passed,
                    "dimensions": s4_s5_result.get("dimension_scores", {})
                }
            }
            
            # 保存Dashboard记录
            dash = Dashboard(
                id=dashboard_id,
                name=f"{dataset_name}看板",
                description=f"基于{theme_tag}主题的自动分析看板",
                status="published",
                score=overall_score,
                passed=passed,
                dataset_ids=[dataset_id],
                primary_dataset_id=dataset_id,
                config=dashboard_config,
                layout={"narrative": "结论→佐证→明细", "chart_count": len(final_charts)},
                created_by=user_id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(dash)
            await db.commit()
            
            await BrainTraceManager.complete_run(
                db, run_id,
                dashboard_id=dashboard_id,
                final_score=int(overall_score),
                passed=passed
            )
            
            # ========== 完成 ==========
            progress.current_stage = "COMPLETE"
            progress.stage_status = "completed"
            progress.progress = 100
            progress.message = "看板生成完成！"
            progress.detail = {
                "dashboard_id": dashboard_id,
                "chart_count": len(final_charts),
                "final_score": overall_score,
                "passed": passed,
                "theme": theme_tag
            }
            yield progress.to_event()
            
            print(f"[Brain] 完成: dashboard_id={dashboard_id}, charts={len(final_charts)}")
            
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            print(f"[Brain] 管道失败: {e}\n{error_detail}")
            
            progress.stage_status = "failed"
            progress.message = f"处理失败: {str(e)}"
            progress.detail = {"error": str(e)}
            yield progress.to_event()


async def check_blocking_issues(db: AsyncSession, dataset_id: str) -> tuple[bool, list]:
    """
    M1-10 二次质检门禁：检查必拦项是否全部处理
    """
    from sqlalchemy import select, and_
    
    result = await db.execute(
        select(QualityIssue).where(
            and_(
                QualityIssue.dataset_id == dataset_id,
                QualityIssue.severity == "blocking",
                QualityIssue.status.in_(["pending", "confirmed"])
            )
        )
    )
    blocking_issues = result.scalars().all()
    
    if not blocking_issues:
        return True, []
    
    issues_list = [
        {
            "id": iss.id,
            "issue_type": iss.type,
            "field": iss.field_name,
            "message": iss.message
        }
        for iss in blocking_issues
    ]
    return False, issues_list


@router.post("/run")
async def brain_run(request: BrainRunRequest):
    """
    运行策略大脑（SSE流式）
    
    M1-10 二次质检门禁：必拦未清零 → 返回403
    
    五阶段进度流式回传：
    - S1: 主题识别
    - S2: 目标生成
    - S3: 图表推荐
    - S4: 编排优化
    - S5: 评分验证
    """
    run_id = str(uuid.uuid4())
    
    async with async_session_factory() as db:
        passed, blocking_issues = await check_blocking_issues(db, request.dataset_id)
        
        if not passed:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "QUALITY_GATE_BLOCKED",
                    "message": f"存在 {len(blocking_issues)} 个未处理的必拦问题",
                    "blocking_issues": blocking_issues,
                    "resolution": "请先修复数据质量问题后再运行策略大脑"
                }
            )
    
    async def event_generator():
        async for event in brain_run_pipeline(
            run_id=run_id,
            dataset_id=request.dataset_id,
            user_id=request.user_id
        ):
            yield event
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/run/{run_id}/status")
async def get_run_status(run_id: str):
    """查询运行状态"""
    async with async_session_factory() as db:
        summary = await BrainTraceManager.get_run_summary(db, run_id)
        if summary:
            return {
                "success": True,
                "run_id": run_id,
                "status": summary.get("status", "unknown"),
                "current_stage": summary.get("current_stage", ""),
                "progress": summary.get("progress", 0)
            }
        return {
            "success": True,
            "run_id": run_id,
            "status": "unknown",
            "progress": 0
        }


@router.post("/run/{run_id}/cancel")
async def cancel_run(run_id: str):
    """取消运行"""
    return {
        "success": True,
        "run_id": run_id,
        "message": "取消请求已发送"
    }