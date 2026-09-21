"""
Token管理API - M3-03
配额查询、消耗、重置、APScheduler调度
"""
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.core.database import get_db
from app.core.token_manager import TokenManager, schedule_daily_reset
from app.core.security import require_admin
from app.models.chat import TokenQuota, TokenApplication

router = APIRouter(prefix="/tokens", tags=["Tokens-Token管理"])


# ============== 请求/响应模型 ==============

class TokenConsumeRequest(BaseModel):
    """Token消耗请求"""
    tokens: int = Field(..., ge=1, description="消耗的Token数")
    reason: Optional[str] = Field("对话消耗", description="消耗原因")


class TokenStatusResponse(BaseModel):
    """Token状态响应"""
    user_id: str
    daily_limit: int
    used_today: int
    extra_quota: int
    total_limit: int
    remaining: int
    usage_percent: float
    status: str  # normal/warning/exhausted
    is_exhausted: bool
    is_warning: bool


# ============== API端点 ==============

@router.get("/quota", response_model=TokenStatusResponse)
async def get_token_quota(
    db: AsyncSession = Depends(get_db),
    current_user: str = "anonymous"
):
    """
    获取Token配额状态
    
    用于前端显示Token余量条
    """
    status = await TokenManager.get_quota_status(db, current_user)
    
    return TokenStatusResponse(
        user_id=status["user_id"],
        daily_limit=status["daily_limit"],
        used_today=status["used_today"],
        extra_quota=status["extra_quota"],
        total_limit=status["total_limit"],
        remaining=status["remaining"],
        usage_percent=status["usage_percent"],
        status=status["status"],
        is_exhausted=status["is_exhausted"],
        is_warning=status["is_warning"]
    )


@router.post("/consume", response_model=Dict)
async def consume_tokens(
    request: TokenConsumeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: str = "anonymous"
):
    """
    消耗Token
    
    检查并扣除Token，返回是否允许继续
    """
    allowed, message, info = await TokenManager.check_and_consume(
        db, current_user, request.tokens
    )
    
    return {
        "success": allowed,
        "message": message,
        "quota_info": info
    }


@router.get("/can-send", response_model=Dict)
async def can_send_message(
    db: AsyncSession = Depends(get_db),
    current_user: str = "anonymous"
):
    """
    检查是否能发送消息
    
    用于前端判断输入框是否禁用
    
    Returns:
        {
            "allowed": true/false,
            "disable_reason": "Token已耗尽..."
        }
    """
    allowed, reason = await TokenManager.can_send_message(db, current_user)
    
    return {
        "allowed": allowed,
        "disable_reason": reason if not allowed else "",
        "can_send": allowed  # 兼容前端
    }


@router.post("/admin/reset", response_model=Dict)
async def admin_reset_quota(
    user_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    admin: Dict[str, Any] = Depends(require_admin)
):
    """
    管理员重置Token配额 (修复：添加权限控制)
    
    user_id为空则重置所有用户
    """
    result = await TokenManager.reset_daily_quota(db, user_id)
    return result


@router.post("/admin/schedule-reset", response_model=Dict)
async def trigger_scheduled_reset(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    admin: Dict[str, Any] = Depends(require_admin)
):
    """
    触发定时重置 (模拟APScheduler)
    
    实际生产环境使用APScheduler配置:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    scheduler = AsyncIOScheduler()
    scheduler.add_job(schedule_daily_reset, 'cron', hour=0, minute=0)
    scheduler.start()
    """
    background_tasks.add_task(schedule_daily_reset, db)
    
    return {
        "success": True,
        "message": "Token配额重置任务已触发",
        "note": "生产环境请配置APScheduler定时任务",
        "scheduler_config": {
            "cron": "0 0 * * *",
            "timezone": "Asia/Shanghai",
            "description": "每天0点重置所有用户Token配额"
        }
    }


@router.get("/status", response_model=Dict)
async def get_full_status(
    db: AsyncSession = Depends(get_db),
    current_user: str = "anonymous"
):
    """
    获取完整Token状态 (含预警信息)
    """
    quota = await TokenManager.get_quota_status(db, current_user)
    
    # 构建预警文案
    warning_message = None
    if quota["status"] == "exhausted":
        warning_message = {
            "type": "exhausted",
            "title": "Token已耗尽",
            "content": "您的Token已用完，对话输入框已禁用。请联系管理员申请加量。",
            "action": "申请加量"
        }
    elif quota["status"] == "warning":
        warning_message = {
            "type": "warning",
            "title": "Token即将耗尽",
            "content": f"已使用{quota['usage_percent']:.0f}%，剩余{quota['remaining']}Token，建议及时申请加量",
            "action": "申请加量"
        }
    
    return {
        "user_id": current_user,
        "quota": quota,
        "warning": warning_message,
        "input_disabled": quota["is_exhausted"],
        "show_warning_bar": quota["usage_percent"] >= 90
    }


# ============== 测试接口 ==============

@router.post("/_internal/test-consume", response_model=Dict)
async def test_consume_tokens(
    tokens: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: str = "test_user"
):
    """
    测试Token消耗流程
    
    内部测试接口
    """
    # 先重置确保有可用的
    await TokenManager.reset_daily_quota(db, current_user)
    
    # 消耗指定Token
    allowed, message, info = await TokenManager.check_and_consume(
        db, current_user, tokens
    )
    
    # 获取最新状态
    status = await TokenManager.get_quota_status(db, current_user)
    
    return {
        "success": True,
        "test_result": {
            "consumed": tokens,
            "allowed": allowed,
            "message": message,
            "quota_after": status
        }
    }


@router.post("/_internal/test-warning", response_model=Dict)
async def test_warning_state(
    db: AsyncSession = Depends(get_db),
    current_user: str = "test_warning_user"
):
    """
    测试>90%预警状态
    
    模拟消耗到预警阈值
    """
    # 重置
    await TokenManager.reset_daily_quota(db, current_user)
    
    # 消耗90%以上
    quota = await TokenManager.get_or_create_quota(db, current_user)
    consume_amount = int(quota.daily_limit * 0.95)  # 消耗95%
    
    allowed, message, info = await TokenManager.check_and_consume(
        db, current_user, consume_amount
    )
    
    # 再次检查触发预警
    allowed2, message2, info2 = await TokenManager.check_and_consume(
        db, current_user, 10
    )
    
    status = await TokenManager.get_quota_status(db, current_user)
    
    return {
        "success": True,
        "test_result": {
            "consumed": consume_amount + 10,
            "usage_percent": status["usage_percent"],
            "is_warning": status["is_warning"],
            "warning_triggered": info2.get("warning") is not None,
            "status": status
        }
    }


@router.post("/_internal/test-exhausted", response_model=Dict)
async def test_exhausted_state(
    db: AsyncSession = Depends(get_db),
    current_user: str = "test_exhausted_user"
):
    """
    测试Token耗尽状态
    
    模拟耗尽后输入框禁用
    """
    # 重置
    await TokenManager.reset_daily_quota(db, current_user)
    
    # 消耗全部
    quota = await TokenManager.get_or_create_quota(db, current_user)
    await TokenManager.check_and_consume(db, current_user, quota.daily_limit + 100)
    
    # 检查是否能发送
    can_send, reason = await TokenManager.can_send_message(db, current_user)
    status = await TokenManager.get_quota_status(db, current_user)
    
    return {
        "success": True,
        "test_result": {
            "is_exhausted": status["is_exhausted"],
            "can_send": can_send,
            "disable_reason": reason,
            "input_should_be_disabled": not can_send,
            "status": status
        }
    }