"""
数据库连接管理
"""
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.core.config import settings


def _resolve_db_url() -> str:
    """启动时探测 Postgres，连不上则自动回退 SQLite（本地无需装数据库）。"""
    if not settings.DB_FALLBACK_SQLITE:
        return settings.DATABASE_URL
    try:
        import asyncio
        import asyncpg
        conn = None
        async def _probe():
            nonlocal conn
            conn = await asyncpg.connect(
                user=os.getenv("PGUSER", "postgres"),
                password=os.getenv("PGPASSWORD", "postgres"),
                host="localhost", port=5432,
                database=os.getenv("PGDATABASE", "aibi")
            )
            await conn.close()
        # 1.3 修复：用独立临时 loop 探活并关闭，避免导入期 get_event_loop() 绑定到
        # 后续被 uvicorn 关闭的旧 loop（进而引发 "Event loop is closed"）
        _loop = asyncio.new_event_loop()
        try:
            _loop.run_until_complete(_probe())
        finally:
            _loop.close()
        print("📦 使用数据库：PostgreSQL")
        return settings.DATABASE_URL
    except Exception as exc:
        print(f"⚠️ 未检测到PostgreSQL（{type(exc).__name__}），回退到SQLite")
        return settings.SQLITE_DATABASE_URL


# 创建异步引擎
_ENGINE_URL = _resolve_db_url()
_ENGINE_KWARGS = {"echo": settings.DEBUG, "future": True}
# SQLite：提升 busy_timeout，避免并发写锁导致 "database is locked"（默认5秒在同时跑质检+生成时过短）
if _ENGINE_URL.startswith("sqlite"):
    _ENGINE_KWARGS["connect_args"] = {"timeout": 30}
    # 每个 SSE 流式响应全程持有一个连接，且本地并发会话多，
    # 默认 QueuePool(size=5, overflow=10) 在十几路并发时就会被占满导致 500。
    # 对 SQLite 提高池容量：并发读(WAL)自由，写仍单写但事务快，ms 级排队即可。
    _ENGINE_KWARGS.update({
        "pool_size": 40,
        "max_overflow": 0,
        "pool_timeout": 90,
    })
else:
    # PostgreSQL 生产环境：适度扩容 + 允许突发
    _ENGINE_KWARGS.update({
        "pool_size": 20,
        "max_overflow": 20,
        "pool_timeout": 60,
    })

engine = create_async_engine(_ENGINE_URL, **_ENGINE_KWARGS)

# 创建异步会话工厂
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def get_db():
    """获取数据库会话（用于FastAPI依赖注入）"""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
