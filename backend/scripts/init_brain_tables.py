"""
初始化策略大脑表 - M2-01
创建 brain_configs, brain_traces, brain_trace_summaries 表
"""
import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.models.brain import BrainConfig, BrainTrace, BrainTraceSummary
from app.core.config import settings


async def init_tables():
    """初始化表结构"""
    print("🔧 初始化策略大脑表...")
    
    # 创建异步引擎
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=True
    )
    
    # 创建表
    async with engine.begin() as conn:
        from app.models.brain import Base
        await conn.run_sync(Base.metadata.create_all)
    
    print("✅ 表创建完成")
    print("  - brain_configs: 配置存储+版本")
    print("  - brain_traces: 五阶段trace")
    print("  - brain_trace_summaries: 运行汇总")
    
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(init_tables())