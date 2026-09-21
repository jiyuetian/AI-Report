"""为 L1 回归创建隔离 QA 库表结构（不碰生产 aibi.db）。

注意：import app.main 会启动后台调度线程导致进程不退出，故建表后强制 os._exit(0)。
"""
import sys
import os
import types
import asyncio

BACKEND = "C:/Users/Asus009/Desktop/临时/ai大赛/AI-Report/backend"
sys.path.insert(0, BACKEND)
QA_DB = "C:/Users/Asus009/Desktop/临时/ai大赛/AI-Report/backend/data/qa_l1test.db"
os.environ["SQLITE_DATABASE_URL"] = f"sqlite+aiosqlite:///{QA_DB}"

_magic = types.ModuleType("magic")
_magic.from_file = lambda *a, **k: "application/octet-stream"
sys.modules["magic"] = _magic

from app.core.database import engine  # noqa: E402
from app.models.base import Base  # noqa: E402
import app.main  # noqa: E402  (注册所有 model 到 Base；其后台线程由 os._exit 强杀)

print("ENGINE_URL=", engine.url)


async def _create():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


asyncio.run(_create())
print("TABLES_CREATED")
# 强制退出，避免 app.main 的后台线程阻止进程结束、进而阻断 pytest 的 &&
os._exit(0)
