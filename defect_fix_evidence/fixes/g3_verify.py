"""
G3 验证脚本：13 个未认证端点加鉴权后，确认"无 token → 401，带 token → 通过鉴权门禁"。

运行环境：后端 venv 的 python（含 fastapi/httpx/aiosqlite/duckdb/redis/jose）
  /c/Users/Asus009/.workbuddy/binaries/python/envs/default/Scripts/python.exe g3_verify.py

说明：本机 starlette 0.36.3 与 httpx 0.28 不兼容（TestClient 的 app= 快捷参数已被移除），
故直接用 httpx.AsyncClient + ASGITransport 调 ASGI app，并手动建表（替代 lifespan startup）。

隔离策略（不碰生产库 backend/data/aibi.db）：
  - SQLITE_DATABASE_URL 指向本次临时 QA 库
  - DUCKDB_PATH 指向独立文件，避免与任何运行实例争锁
  - REDIS_URL 置无效 → security 降级为内存锁定兜底

判定：
  - 普通端点：无 token 必须 401；带普通用户 token 必须 != 401（200/404 均可，仅验证鉴权门禁）
  - 管理员端点(llm/config、brain/configs 系列)：无 token 401；普通用户 403；管理员 200
"""
import os
import sys
import asyncio
import types
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent.parent / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# ---- 隔离 QA 库（绝对路径，避免误触生产 aibi.db）----
# 每次运行用独立子目录（含 pid），避免 safe-delete 拦截 unlink 且避开旧实例残留锁。
qa_dir = BACKEND / "data" / f"qa_g3_{os.getpid()}"
qa_dir.mkdir(parents=True, exist_ok=True)
qa_sqlite = qa_dir / "qa_g3_verify.db"
qa_duck = qa_dir / "qa_g3_verify.duckdb"

os.environ["SQLITE_DATABASE_URL"] = f"sqlite+aiosqlite:///{qa_sqlite.as_posix()}"
os.environ["DUCKDB_PATH"] = str(qa_duck)
os.environ["DB_FALLBACK_SQLITE"] = "true"
os.environ["REDIS_URL"] = "redis://127.0.0.1:1"  # 强制 redis 不可用 → 内存兜底
os.environ["NO_PROXY"] = "127.0.0.1,localhost"
os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)

# libmagic 系统库缺失，upload.py 仅用到 magic.from_file(path, mime=True)，注入最小桩。
_magic = types.ModuleType("magic")
_magic.from_file = lambda path, mime=False: "application/octet-stream"
sys.modules["magic"] = _magic

from fastapi import FastAPI  # noqa: E402
from httpx import AsyncClient, ASGITransport  # noqa: E402
from app.core.security import create_access_token  # noqa: E402
from app.core.database import engine  # noqa: E402
from app.models.base import Base  # noqa: E402
from app.main import app  # noqa: E402  (import 必须在 env 设置之后；所有 model 随 router 注册到 Base)


async def create_tables():
    print("[setup] creating tables ...", flush=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("[setup] tables created", flush=True)


ADMIN_TOK = create_access_token(
    {"sub": "qa_admin", "username": "qaadmin", "roles": [], "is_superuser": True}
)
USER_TOK = create_access_token(
    {"sub": "qa_user", "username": "qauser", "roles": [], "is_superuser": False}
)


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


# (名称, 方法, 路径, 是否管理员端点)
CASES = [
    ("datasets_list",        "GET", "/api/v1/datasets",                         False),
    ("dataset_detail",       "GET", "/api/v1/datasets/nope-id",                 False),
    ("brain_report",         "GET", "/api/v1/brain/report/nope-id",             False),
    ("quality_issues",       "GET", "/api/v1/quality/nope-id/issues",           False),
    ("lineage_graph",        "GET", "/api/v1/lineage/graph/nope-id",            False),
    ("lineage_stats",        "GET", "/api/v1/lineage/stats/nope-id",           False),
    ("chat_sessions_latest", "GET", "/api/v1/chat/sessions/latest?dashboard_id=x", False),
    ("shares_my_list",       "GET", "/api/v1/shares/my/list",                   False),
    ("exports_my_list",      "GET", "/api/v1/exports/my/list",                  False),
    ("llm_config",           "GET", "/api/v1/llm/config",                       True),
    ("brain_configs",        "GET", "/api/v1/brain/configs",                    True),
    ("brain_config_cat",     "GET", "/api/v1/brain/configs/quality",            True),
    ("brain_config_hist",    "GET", "/api/v1/brain/configs/threshold/history",  True),
]


async def main():
    await create_tables()
    transport = ASGITransport(app=app)
    results = []
    async with AsyncClient(transport=transport, base_url="http://testserver", timeout=15.0) as client:
        for name, method, path, is_admin in CASES:
            print(f"[test] {name} ...", flush=True)
            r0 = await client.request(method, path)
            no_token_401 = (r0.status_code == 401)

            r1 = await client.request(method, path, headers=H(USER_TOK))
            user_passes = (r1.status_code != 401)

            ok = no_token_401 and user_passes
            detail = f"no_tok={r0.status_code} user_tok={r1.status_code}"

            if is_admin:
                user_403 = (r1.status_code == 403)
                r2 = await client.request(method, path, headers=H(ADMIN_TOK))
                admin_200 = (r2.status_code == 200)
                ok = ok and user_403 and admin_200
                detail += f" admin_tok={r2.status_code}"

            results.append((name, ok, detail))
            print(f"[{'PASS' if ok else 'FAIL'}] {name:22s} {detail}", flush=True)

    failed = [n for n, ok, _ in results if not ok]
    print("\n==== G3 SUMMARY ====")
    print(f"total={len(results)} pass={len(results)-len(failed)} fail={len(failed)}")
    if failed:
        print("FAILED:", ", ".join(failed))
        sys.exit(1)
    print("G3_VERIFY_ALL_PASS")


if __name__ == "__main__":
    try:
        asyncio.run(asyncio.wait_for(main(), timeout=120))
        print("[done] verify finished", flush=True)
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)
