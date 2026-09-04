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
        asyncio.get_event_loop().run_until_complete(_probe())
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
