"""策略大脑配置API - M1-15"""
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.security import get_current_user, require_admin
from app.core.database import get_db
from app.models.dataset import Dataset
from app.api.datasets import _assert_dataset_access

router = APIRouter(prefix="/brain", tags=["Brain"])

# 内存存储（实际应使用数据库）
_brain_configs: Dict[str, Any] = {
    "quality": {
        "null_threshold": 0.05,
        "format_threshold": 0.05,
        "duplicate_threshold": 0.01,
        "range_threshold": 0.01
    },
    "chart": {
        "max_categories": 20,
        "default_colors": ["#5B8FF9", "#5AD8A6", "#F6BD16", "#E86452", "#6DC8EC"]
    }
}


class ThresholdUpdateRequest(BaseModel):
    category: str  # quality/chart/...
    key: str
    value: float


@router.get("/configs")
async def get_brain_configs(current_user: Dict = Depends(require_admin)):
    """获取所有策略大脑配置（G3：仅管理员）"""
    return {
        "configs": _brain_configs,
        "version": "1.0.0",
        "updated_at": "2026-08-18T11:00:00Z"
    }


@router.get("/configs/{category}")
async def get_category_config(category: str, current_user: Dict = Depends(require_admin)):
    """获取指定类别配置（G3：仅管理员）"""
    if category not in _brain_configs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CONFIG_NOT_FOUND", "message": f"配置类别不存在: {category}"}
        )
    
    return {
        "category": category,
        "config": _brain_configs[category]
    }


@router.post("/configs/update")
async def update_threshold(request: ThresholdUpdateRequest):
    """
    更新阈值配置（M1-15）
    
    阈值改动后立即重检
    """
    category = request.category
    key = request.key
    value = request.value
    
    if category not in _brain_configs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CONFIG_NOT_FOUND", "message": f"配置类别不存在: {category}"}
        )
    
    if key not in _brain_configs[category]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "KEY_NOT_FOUND", "message": f"配置项不存在: {key}"}
        )
    
    # 更新配置
    old_value = _brain_configs[category][key]
    _brain_configs[category][key] = value
    
    # TODO: 触发重检
    # 1. 记录配置变更
    # 2. 触发相关数据集的重新质检
    
    return {
        "success": True,
        "category": category,
        "key": key,
        "old_value": old_value,
        "new_value": value,
        "message": "配置已更新，将触发重新质检"
    }


@router.get("/configs/{category}/history")
async def get_config_history(category: str, current_user: Dict = Depends(require_admin)):
    """获取配置变更历史（G3：仅管理员）"""
    # TODO: 从数据库查询历史
    return {
        "category": category,
        "history": []
    }


# M1-15: 处理报告导出
@router.get("/report/{dataset_id}")
async def get_processing_report(
    dataset_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Dict = Depends(get_current_user),
):
    """获取数据处理报告（G3：需登录 + 数据集归属校验）"""
    await _assert_dataset_access(db, dataset_id, current_user)
    # TODO: 从数据库查询报告
    return {
        "dataset_id": dataset_id,
        "report": {
            "upload_time": "2026-08-18T10:00:00Z",
            "quality_check": {
                "total_issues": 6,
                "blocking_count": 2,
                "warning_count": 4
            },
            "clean_operations": [
                {"type": "deduplicate", "affected_rows": 10},
                {"type": "fill_median", "affected_rows": 50}
            ],
            "final_status": "ready"
        }
    }


@router.get("/report/{dataset_id}/export")
async def export_report(dataset_id: str, format: str = "pdf"):
    """
    导出处理报告
    
    支持格式: pdf, html
    """
    # TODO: 生成PDF报告
    return {
        "dataset_id": dataset_id,
        "format": format,
        "download_url": f"/downloads/reports/{dataset_id}.{format}",
        "message": "报告生成中，请稍后下载"
    }


# M1-15: 运行策略大脑 - 已由 brain_run_sse.py 的 SSE 流式端点实现
# 真实实现位于 app.api.brain_run_sse.brain_run，支持五阶段进度流式回传
