"""
Token管理器 - M3-03
按量计量、>90%预警、耗尽禁用、次日0点重置
"""
from typing import Dict, Any, Tuple, Optional
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_
from app.models.chat import TokenQuota, TokenApplication
import asyncio


class TokenManager:
    """Token管理器"""
    
    DEFAULT_DAILY_LIMIT = 5000  # 默认每日上限
    WARNING_THRESHOLD = 90      # 预警阈值(%)
    
    @staticmethod
    async def get_or_create_quota(
        db: AsyncSession,
        user_id: str
    ) -> TokenQuota:
        """获取或创建用户Token配额"""
        result = await db.execute(
            select(TokenQuota).where(TokenQuota.user_id == user_id)
        )
        quota = result.scalar_one_or_none()
        
        if not quota:
            quota = TokenQuota(
                user_id=user_id,
                daily_limit=TokenManager.DEFAULT_DAILY_LIMIT,
                used_today=0,
                remaining=TokenManager.DEFAULT_DAILY_LIMIT
            )
            db.add(quota)
            await db.commit()
            await db.refresh(quota)
        
        return quota
    
    @staticmethod
    async def check_and_consume(
        db: AsyncSession,
        user_id: str,
        tokens_needed: int
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        检查并消耗Token
        
        Returns:
            (allowed, message, quota_info)
        """
        # 获取配额
        quota = await TokenManager.get_or_create_quota(db, user_id)
        
        # 计算剩余 (含临时加量)
        total_limit = quota.daily_limit + (quota.extra_quota or 0)
        remaining = total_limit - quota.used_today
        
        # 检查是否耗尽
        if remaining <= 0:
            return False, "Token已耗尽，请输入框禁用", {
                "allowed": False,
                "reason": "exhausted",
                "used_today": quota.used_today,
                "daily_limit": quota.daily_limit,
                "extra_quota": quota.extra_quota or 0,
                "remaining": 0,
                "usage_percent": 100
            }
        
        # 检查单次上下文上限
        SINGLE_MESSAGE_LIMIT = 2000
        if tokens_needed > SINGLE_MESSAGE_LIMIT:
            return False, f"单次输入超过上限{SINGLE_MESSAGE_LIMIT}Token", {
                "allowed": False,
                "reason": "single_limit_exceeded",
                "max_allowed": SINGLE_MESSAGE_LIMIT,
                "requested": tokens_needed
            }
        
        # 修复：使用total_limit计算使用率（考虑extra_quota）
        usage_percent = (quota.used_today / total_limit) * 100 if total_limit > 0 else 0
        
        # 检查是否需要预警 (>90%) - 修复：使用total_limit计算
        warning_info = None
        if usage_percent >= TokenManager.WARNING_THRESHOLD and not quota.is_warning_shown:
            quota.is_warning_shown = 1
            warning_info = {
                "show_warning": True,
                "message": f"Token已使用{usage_percent:.1f}%，即将耗尽，请及时申请加量",
                "usage_percent": usage_percent,
                "remaining": remaining
            }
            await db.commit()
        
        # 消耗Token
        quota.used_today += tokens_needed
        quota.remaining = max(0, total_limit - quota.used_today)
        await db.commit()
        await db.refresh(quota)
        
        # 修复：重新计算使用率使用total_limit
        usage_percent = (quota.used_today / total_limit) * 100 if total_limit > 0 else 0
        
        return True, "Token消耗成功", {
            "allowed": True,
            "used_today": quota.used_today,
            "daily_limit": quota.daily_limit,
            "extra_quota": quota.extra_quota or 0,
            "remaining": quota.remaining,
            "usage_percent": round(usage_percent, 1),
            "warning": warning_info
        }
    
    @staticmethod
    async def get_quota_status(
        db: AsyncSession,
        user_id: str
    ) -> Dict[str, Any]:
        """获取Token配额状态"""
        quota = await TokenManager.get_or_create_quota(db, user_id)
        
        total_limit = quota.daily_limit + (quota.extra_quota or 0)
        remaining = total_limit - quota.used_today
        # 修复：使用 total_limit 计算使用率
        usage_percent = (quota.used_today / total_limit) * 100 if total_limit > 0 else 0
        
        status = "normal"
        if usage_percent >= 100:
            status = "exhausted"
        elif usage_percent >= TokenManager.WARNING_THRESHOLD:
            status = "warning"
        
        return {
            "user_id": user_id,
            "daily_limit": quota.daily_limit,
            "used_today": quota.used_today,
            "extra_quota": quota.extra_quota or 0,
            "total_limit": total_limit,
            "remaining": max(0, remaining),
            "usage_percent": round(usage_percent, 1),
            "status": status,
            "is_exhausted": quota.used_today >= total_limit,
            "is_warning": usage_percent >= TokenManager.WARNING_THRESHOLD,
            "warning_threshold": TokenManager.WARNING_THRESHOLD
        }
    
    @staticmethod
    async def reset_daily_quota(
        db: AsyncSession,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        重置每日配额 (次日0点执行) - 修复SQL表达式错误
        
        Args:
            user_id: 指定用户，None则重置所有
        """
        from sqlalchemy import func
        
        # 修复：使用数据库表达式正确计算remaining = daily_limit + COALESCE(extra_quota, 0)
        # 而不是使用Python的Column引用
        if user_id:
            # 重置指定用户
            result = await db.execute(
                update(TokenQuota)
                .where(TokenQuota.user_id == user_id)
                .values(
                    used_today=0,
                    remaining=TokenQuota.daily_limit + func.coalesce(TokenQuota.extra_quota, 0),
                    is_warning_shown=0,
                    last_reset_at=datetime.now()
                )
            )
        else:
            # 重置所有用户
            result = await db.execute(
                update(TokenQuota)
                .values(
                    used_today=0,
                    remaining=TokenQuota.daily_limit + func.coalesce(TokenQuota.extra_quota, 0),
                    is_warning_shown=0,
                    last_reset_at=datetime.now()
                )
            )
        
        await db.commit()
        
        return {
            "success": True,
            "message": f"Token配额已重置 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})",
            "reset_time": datetime.now().isoformat()
        }
    
    @staticmethod
    async def can_send_message(
        db: AsyncSession,
        user_id: str
    ) -> Tuple[bool, str]:
        """
        检查用户是否能发送消息 (用于前端输入框禁用判断)
        
        Returns:
            (allowed, disable_reason)
        """
        quota = await TokenManager.get_or_create_quota(db, user_id)
        total_limit = quota.daily_limit + (quota.extra_quota or 0)
        
        if quota.used_today >= total_limit:
            # Token已耗尽，禁用输入
            return False, "Token已耗尽，需申请加量后才能继续对话"
        
        return True, ""
    
    @staticmethod
    def estimate_tokens(text: str) -> int:
        """估算文本Token数 (简化版：汉字=2，英文单词=1)"""
        # 中文字符数
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        # 英文单词数 (按空格分)
        english_words = len([w for w in text.split() if any(c.isalpha() for c in w)])
        
        # 中英文混合估算：汉字*2 + 英文单词*1 + 标点符号*0.5
        tokens = chinese_chars * 2 + english_words + len([c for c in text if not c.isalnum() and not c.isspace()]) // 2
        
        return max(tokens, 1)  # 至少1个token


# APScheduler调度器配置 (用于定时重置)
SCHEDULER_CONFIG = {
    "reset_time": "0 0 * * *",  # 每天0点执行
    "timezone": "Asia/Shanghai"
}


async def schedule_daily_reset(db: AsyncSession):
    """
    每日0点重置所有用户Token配额
    
    使用APScheduler调度
    """
    await TokenManager.reset_daily_quota(db)
    print(f"[APScheduler] Token配额已重置 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")