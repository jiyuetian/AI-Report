"""健康检查API"""
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

router = APIRouter(tags=["Health"])


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """健康检查端点"""
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "healthy",
            "service": "ai-bi-report-api",
            "version": "2.0.0"
        }
    )