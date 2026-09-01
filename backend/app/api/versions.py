"""
版本管理 API - M4-03
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.version_manager import VersionManager

router = APIRouter(prefix="/versions", tags=["Versions"])


class CreateVersionRequest(BaseModel):
    """创建版本请求"""
    dashboard_id: str
    name: str
    description: str = ""


class RollbackRequest(BaseModel):
    """回退请求"""
    version_id: str


class CompareRequest(BaseModel):
    """对比请求"""
    version_id_1: str
    version_id_2: str


@router.post("/create")
async def create_version(
    request: CreateVersionRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = "anonymous"
):
    """创建新版本"""
    try:
        version = await VersionManager.create_version(
            db, request.dashboard_id, request.name, request.description, user_id
        )
        return {
            "success": True,
            "version": {
                "id": version.version_id,
                "number": version.version_number,
                "name": version.name,
                "prompt_version": version.prompt_version
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list/{dashboard_id}")
async def list_versions(
    dashboard_id: str,
    include_auto: bool = True,
    db: AsyncSession = Depends(get_db)
):
    """获取版本列表"""
    versions = await VersionManager.get_version_list(db, dashboard_id, include_auto)
    return {
        "versions": [
            {
                "id": v.version_id,
                "number": v.version_number,
                "name": v.name,
                "description": v.description,
                "prompt_version": v.prompt_version,
                "created_at": v.created_at.isoformat(),
                "is_auto_save": v.is_auto_save,
                "created_by": v.created_by
            }
            for v in versions
        ]
    }


@router.post("/rollback/{dashboard_id}")
async def rollback_version(
    dashboard_id: str,
    request: RollbackRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = "anonymous"
):
    """回退到指定版本"""
    try:
        result = await VersionManager.rollback_to_version(
            db, dashboard_id, request.version_id, user_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/compare")
async def compare_versions(
    request: CompareRequest,
    db: AsyncSession = Depends(get_db)
):
    """对比两个版本"""
    try:
        result = await VersionManager.compare_versions(
            db, request.version_id_1, request.version_id_2
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
