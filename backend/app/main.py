"""FastAPI主入口"""
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from app.core.config import settings
from app.api import health, upload, auth, datasets, quality, brain, brain_v2, llm, s1, s2, s3, s4_s5, brain_run_sse, dashboards, chat, tokens, token_applications, lineage, versions, share, exports, exceptions, golden, loadtest, admin, admin_prompts, reports, skills


def _ensure_dataset_owner(sync_conn):
    """增量迁移：datasets 新增 created_by 归属列（G2.1 横向越权修复）

    仅新增可空列，SQLite 原生支持 ALTER TABLE ADD COLUMN，无需重建表。
    存量数据 created_by 为 NULL，按 legacy 处理（任何已登录用户可读）。
    """
    from sqlalchemy import text, inspect
    insp = inspect(sync_conn)
    if "datasets" not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns("datasets")}
    if "created_by" not in existing:
        sync_conn.execute(text("ALTER TABLE datasets ADD COLUMN created_by VARCHAR(36)"))
        print("🔧 datasets.created_by 已新增（归属列，存量数据视为 legacy）")


def _ensure_report_columns(sync_conn):
    """增量迁移：确保 brain_trace_summaries 含报告生成所需列"""
    from sqlalchemy import text, inspect
    insp = inspect(sync_conn)
    if "brain_trace_summaries" not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns("brain_trace_summaries")}
    migrations = [
        ("version_id", "VARCHAR(36)"),
        ("status", "VARCHAR(20)"),
        ("result", "JSON"),
    ]
    for col, coltype in migrations:
        if col not in existing:
            sync_conn.execute(text(f"ALTER TABLE brain_trace_summaries ADD COLUMN {col} {coltype}"))
            print(f"  + 新增列 brain_trace_summaries.{col}")


def _ensure_dataset_nullable_table(sync_conn):
    """增量迁移：datasets.duckdb_table 改为可空（文档型数据集不建表）

    SQLite 无法原地放宽列约束，按标准 12 步迁移重建表。
    数据集 id 全部保留，因此 quality_issues/clean_rules/charts 等外键引用表无需改动。
    """
    from sqlalchemy import text, inspect
    insp = inspect(sync_conn)
    if "datasets" not in insp.get_table_names():
        return
    cols = {c["name"]: c for c in insp.get_columns("datasets")}
    if cols.get("duckdb_table", {}).get("nullable"):
        return  # 已是可空

    from sqlalchemy.schema import CreateTable
    from sqlalchemy.dialects import sqlite as sqlite_dialect
    from app.models.dataset import Dataset

    col_names = [c.name for c in Dataset.__table__.columns]
    new_table = "datasets_new"
    ddl = str(CreateTable(Dataset.__table__).compile(dialect=sqlite_dialect.dialect()))
    ddl = ddl.replace("CREATE TABLE datasets", f"CREATE TABLE {new_table}")

    select_sql = "SELECT " + ", ".join(col_names) + f" FROM datasets"

    sync_conn.execute(text("PRAGMA foreign_keys = OFF"))
    sync_conn.execute(text("BEGIN"))
    try:
        sync_conn.execute(text(ddl))
        sync_conn.execute(text(f"INSERT INTO {new_table} ({', '.join(col_names)}) {select_sql}"))
        sync_conn.execute(text("DROP TABLE datasets"))
        sync_conn.execute(text(f"ALTER TABLE {new_table} RENAME TO datasets"))
        sync_conn.execute(text("COMMIT"))
    except Exception:
        sync_conn.execute(text("ROLLBACK"))
        sync_conn.execute(text("PRAGMA foreign_keys = ON"))
        raise
    sync_conn.execute(text("PRAGMA foreign_keys = ON"))
    print("🔧 datasets.duckdb_table 已迁移为可空（数据无损重建）")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理 - 修复：自动创建数据库表"""
    # 启动时执行
    print("🚀 AI-BI-Report starting up...")

    # 打印 LLM 配置确认
    from app.core.config import settings
    import os
    _env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")
    _env_exists = os.path.exists(_env_path)
    print(f"[config] .env 已加载: {_env_exists}, LLM_BASE_URL={settings.LLM_BASE_URL}, LLM_MODEL={settings.LLM_MODEL or '(空,使用默认)'}")
    
    # 修复：自动创建数据库表（开发环境）
    if settings.DEBUG:
        from app.models.base import Base
        from app.core.database import engine
        
        # 导入所有模型以确保注册到Base.metadata
        from app.models import (
            User, File, Dataset, QualityIssue, CleanRule,
            Chart, Dashboard, ChatSession, ChatMessage, TokenQuota, TokenApplication,
            AuditLog, Prompt, TokenBlacklist
        )
        
        # 迁移：datasets.duckdb_table 放宽为可空（文档型数据集不建表）
        async with engine.begin() as conn:
            await conn.run_sync(_ensure_dataset_nullable_table)

        # 重建后重新确保 datasets 表存在（新列定义）
        if settings.DEBUG:
            from app.models.base import Base
            from app.core.database import engine
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

        print("✅ 数据库表已创建/更新")

        # 载入令牌吊销缓存（D2-5）：重启后已登出的旧 token 仍失效
        from app.core.security import load_blacklist_cache
        await load_blacklist_cache()

        # 增量迁移：为已存在的 brain_trace_summaries 补充报告生成新列
        async with engine.begin() as conn:
            await conn.run_sync(_ensure_report_columns)

        # 增量迁移：datasets 新增 created_by 归属列（G2.1 横向越权修复）
        async with engine.begin() as conn:
            await conn.run_sync(_ensure_dataset_owner)

        print("✅ 报告扩展列已就绪")

        # Prompt 中心：启动时补齐默认板块记录并载入内存覆盖缓存
        from app.core.database import async_session_factory
        async with async_session_factory() as init_db:
            from app.api.admin_prompts import init_prompt_records
            await init_prompt_records(init_db)
            await init_db.commit()
        print("✅ Prompt 中心已初始化")
    
    yield
    
    # 关闭时执行
    print("🛑 AI-BI-Report shutting down...")


# 创建FastAPI应用
app = FastAPI(
    title="AI快速BI报表工具 API",
    description="AI-powered BI Reporting Tool API",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.DEBUG else ["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 根路由
@app.get("/", tags=["Root"])
async def root():
    return {
        "name": "AI快速BI报表工具 API",
        "version": "2.0.0",
        "docs": "/docs"
    }


# 注册API路由
app.include_router(health.router, prefix="/api/v1")
app.include_router(upload.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(datasets.router, prefix="/api/v1")
app.include_router(quality.router, prefix="/api/v1")
app.include_router(brain.router, prefix="/api/v1")
app.include_router(brain_v2.router, prefix="/api/v1")
app.include_router(llm.router, prefix="/api/v1")
app.include_router(s1.router, prefix="/api/v1")
app.include_router(s2.router, prefix="/api/v1")
app.include_router(s3.router, prefix="/api/v1")
app.include_router(s4_s5.router, prefix="/api/v1")
app.include_router(brain_run_sse.router, prefix="/api/v1")
app.include_router(dashboards.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(tokens.router, prefix="/api/v1")
app.include_router(token_applications.router, prefix="/api/v1")
app.include_router(lineage.router, prefix="/api/v1")
app.include_router(versions.router, prefix="/api/v1")
app.include_router(share.router, prefix="/api/v1")
app.include_router(exports.router, prefix="/api/v1")
app.include_router(exceptions.router, prefix="/api/v1")
app.include_router(golden.router, prefix="/api/v1")
app.include_router(loadtest.router, prefix="/api/v1")
app.include_router(admin_prompts.router, prefix="/api/v1")
app.include_router(reports.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(skills.router, prefix="/api/v1")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)