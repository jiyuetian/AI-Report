"""FastAPI主入口"""
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from app.core.config import settings
from app.api import health, upload, auth, datasets, quality, brain, brain_v2, llm, s1, s2, s3, s4_s5, brain_run_sse, dashboards, chat, tokens, token_applications, lineage, versions, share, exports, exceptions, golden, loadtest


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理 - 修复：自动创建数据库表"""
    # 启动时执行
    print("🚀 AI-BI-Report starting up...")
    
    # 修复：自动创建数据库表（开发环境）
    if settings.DEBUG:
        from app.models.base import Base
        from app.core.database import engine
        
        # 导入所有模型以确保注册到Base.metadata
        from app.models import (
            User, File, Dataset, QualityIssue, CleanRule,
            Chart, Dashboard, ChatSession, ChatMessage, TokenQuota, TokenApplication,
            AuditLog
        )
        
        async with engine.begin() as conn:
            # 使用run_sync在异步上下文中执行同步操作
            await conn.run_sync(Base.metadata.create_all)
        
        print("✅ 数据库表已创建/更新")
    
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)