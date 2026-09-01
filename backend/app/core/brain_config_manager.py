"""
策略大脑配置管理 - 热更新+版本+回滚
M2-01 核心模块
"""
import json
import redis
import hashlib
from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_
from app.models.brain import BrainConfig, BrainTrace, BrainTraceSummary
import os

# Redis连接（配置热更新缓存） - Redis不可用时自动降级为纯数据库模式
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    redis_client.ping()
except Exception:
    redis_client = None
    print("[BrainConfig] Redis不可用，降级为纯数据库模式")

# 缓存键前缀
CONFIG_CACHE_PREFIX = "brain:config:"


class BrainConfigManager:
    """大脑配置管理器 - 支持热更新"""
    
    @staticmethod
    async def get_config(db: AsyncSession, config_key: str, use_cache: bool = True) -> Optional[Dict]:
        """
        获取配置（带缓存）
        
        流程：
        1. 先查Redis缓存
        2. 缓存未命中查数据库
        3. 写入缓存
        """
        cache_key = f"{CONFIG_CACHE_PREFIX}{config_key}"
        
        # 1. 查缓存
        if use_cache and redis_client:
            cached = redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
        
        # 2. 查数据库（取最新生效版本）
        result = await db.execute(
            select(BrainConfig).where(
                and_(
                    BrainConfig.config_key == config_key,
                    BrainConfig.is_active == 1
                )
            ).order_by(desc(BrainConfig.version))
        )
        config = result.scalar_one_or_none()
        
        if not config:
            return None
        
        config_data = config.to_dict()
        
        # 3. 写入缓存（TTL 1小时）
        if use_cache and redis_client:
            redis_client.setex(cache_key, 3600, json.dumps(config_data))
        
        return config_data
    
    @staticmethod
    async def get_configs_by_category(db: AsyncSession, category: str) -> List[Dict]:
        """获取某类别的所有生效配置"""
        result = await db.execute(
            select(BrainConfig).where(
                and_(
                    BrainConfig.category == category,
                    BrainConfig.is_active == 1
                )
            ).order_by(BrainConfig.config_key)
        )
        configs = result.scalars().all()
        return [c.to_dict() for c in configs]
    
    @staticmethod
    async def update_config(
        db: AsyncSession,
        config_key: str,
        content: Dict,
        category: str,
        description: str = "",
        created_by: str = "system"
    ) -> Dict:
        """
        更新配置（自动版本递增，热更新）
        
        关键：
        1. 查询当前最新版本
        2. 旧配置标记为历史版本
        3. 创建新版本
        4. 清除缓存
        """
        # 1. 查询当前版本
        result = await db.execute(
            select(BrainConfig).where(
                BrainConfig.config_key == config_key
            ).order_by(desc(BrainConfig.version))
        )
        current = result.scalar_one_or_none()
        
        new_version = 1
        if current:
            new_version = current.version + 1
            # 旧版本标记为历史
            current.is_active = 0
        
        # 2. 创建新版本
        new_config = BrainConfig(
            config_key=config_key,
            category=category,
            version=new_version,
            content=content,
            description=description,
            is_active=1,
            created_by=created_by
        )
        db.add(new_config)
        await db.commit()
        await db.refresh(new_config)
        
        # 3. 清除缓存（热更新关键：下次请求从DB读取新配置）
        cache_key = f"{CONFIG_CACHE_PREFIX}{config_key}"
        if redis_client:
            redis_client.delete(cache_key)
        
        return {
            "success": True,
            "config_key": config_key,
            "version": new_version,
            "message": "配置已更新，热更新生效",
            "config": new_config.to_dict()
        }
    
    @staticmethod
    async def rollback_config(db: AsyncSession, config_key: str, target_version: int) -> Dict:
        """
        回滚到指定版本
        
        流程：
        1. 标记当前版本为历史
        2. 激活目标版本
        3. 清除缓存
        """
        # 标记当前生效为历史
        await db.execute(
            BrainConfig.__table__.update()
            .where(and_(
                BrainConfig.config_key == config_key,
                BrainConfig.is_active == 1
            ))
            .values(is_active=0)
        )
        
        # 激活目标版本
        result = await db.execute(
            select(BrainConfig).where(
                and_(
                    BrainConfig.config_key == config_key,
                    BrainConfig.version == target_version
                )
            )
        )
        target = result.scalar_one_or_none()
        
        if not target:
            await db.rollback()
            return {"success": False, "error": "目标版本不存在"}
        
        target.is_active = 1
        await db.commit()
        
        # 清除缓存
        cache_key = f"{CONFIG_CACHE_PREFIX}{config_key}"
        if redis_client:
            redis_client.delete(cache_key)
        
        return {
            "success": True,
            "config_key": config_key,
            "rolled_to_version": target_version,
            "message": "已回滚到指定版本"
        }
    
    @staticmethod
    async def get_config_history(db: AsyncSession, config_key: str) -> List[Dict]:
        """获取配置变更历史"""
        result = await db.execute(
            select(BrainConfig).where(
                BrainConfig.config_key == config_key
            ).order_by(desc(BrainConfig.version))
        )
        configs = result.scalars().all()
        return [c.to_dict() for c in configs]
    
    @staticmethod
    def clear_all_cache():
        """清除所有配置缓存（紧急情况下使用）"""
        if not redis_client:
            return
        keys = redis_client.keys(f"{CONFIG_CACHE_PREFIX}*")
        if keys:
            redis_client.delete(*keys)


class BrainTraceManager:
    """大脑Trace管理 - 五阶段全链路落库"""
    
    STAGE_NAMES = {
        "S1": "主题识别",
        "S2": "目标生成",
        "S3": "图表推荐",
        "S4": "编排",
        "S5": "评分"
    }
    
    @staticmethod
    async def start_run(
        db: AsyncSession,
        run_id: str,
        dataset_id: str,
        user_id: str
    ) -> str:
        """开始一次运行，创建汇总记录"""
        summary = BrainTraceSummary(
            run_id=run_id,
            dataset_id=dataset_id,
            user_id=user_id,
            overall_status="running",
            current_stage="S1"
        )
        db.add(summary)
        await db.commit()
        return run_id
    
    @staticmethod
    async def start_stage(
        db: AsyncSession,
        run_id: str,
        dataset_id: str,
        stage: str,
        stage_input: Dict
    ) -> str:
        """开始一个阶段"""
        trace = BrainTrace(
            run_id=run_id,
            dataset_id=dataset_id,
            stage=stage,
            stage_name=BrainTraceManager.STAGE_NAMES.get(stage, ""),
            stage_status="running",
            stage_input=stage_input
        )
        db.add(trace)
        await db.commit()
        await db.refresh(trace)
        
        # 更新汇总表
        await db.execute(
            BrainTraceSummary.__table__.update()
            .where(BrainTraceSummary.run_id == run_id)
            .values(current_stage=stage)
        )
        await db.commit()
        
        return trace.id
    
    @staticmethod
    async def complete_stage(
        db: AsyncSession,
        trace_id: str,
        stage_output: Dict,
        stage_metrics: Dict = None
    ):
        """完成一个阶段"""
        result = await db.execute(
            select(BrainTrace).where(BrainTrace.id == trace_id)
        )
        trace = result.scalar_one_or_none()
        
        if trace:
            trace.stage_status = "success"
            trace.stage_output = stage_output
            trace.stage_metrics = stage_metrics or {}
            trace.completed_at = datetime.now()
            await db.commit()
    
    @staticmethod
    async def fail_stage(
        db: AsyncSession,
        trace_id: str,
        error_info: Dict
    ):
        """阶段失败"""
        result = await db.execute(
            select(BrainTrace).where(BrainTrace.id == trace_id)
        )
        trace = result.scalar_one_or_none()
        
        if trace:
            trace.stage_status = "failed"
            trace.error_info = error_info
            trace.completed_at = datetime.now()
            await db.commit()
    
    @staticmethod
    async def update_stage_status(
        db: AsyncSession,
        run_id: str,
        stage: str,
        status: str
    ):
        """更新汇总表中的阶段状态"""
        column_map = {
            "S1": "s1_status",
            "S2": "s2_status",
            "S3": "s3_status",
            "S4": "s4_status",
            "S5": "s5_status"
        }
        column = column_map.get(stage)
        if column:
            await db.execute(
                BrainTraceSummary.__table__.update()
                .where(BrainTraceSummary.run_id == run_id)
                .values({column: status})
            )
            await db.commit()
    
    @staticmethod
    async def complete_run(
        db: AsyncSession,
        run_id: str,
        dashboard_id: str = None,
        final_score: int = None,
        passed: bool = False
    ):
        """完成整个运行"""
        result = await db.execute(
            select(BrainTraceSummary).where(BrainTraceSummary.run_id == run_id)
        )
        summary = result.scalar_one_or_none()
        
        if summary:
            summary.overall_status = "completed" if passed else "failed"
            summary.dashboard_id = dashboard_id
            summary.final_score = final_score
            summary.passed = 1 if passed else 0
            summary.completed_at = datetime.now()
            await db.commit()
    
    @staticmethod
    async def get_run_traces(db: AsyncSession, run_id: str) -> List[Dict]:
        """获取一次运行的所有trace"""
        result = await db.execute(
            select(BrainTrace).where(
                BrainTrace.run_id == run_id
            ).order_by(BrainTrace.created_at)
        )
        traces = result.scalars().all()
        return [t.to_dict() for t in traces]
    
    @staticmethod
    async def get_run_summary(db: AsyncSession, run_id: str) -> Optional[Dict]:
        """获取运行汇总"""
        result = await db.execute(
            select(BrainTraceSummary).where(BrainTraceSummary.run_id == run_id)
        )
        summary = result.scalar_one_or_none()
        return summary.to_dict() if summary else None