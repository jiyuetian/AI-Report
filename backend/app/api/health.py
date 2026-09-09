"""健康检查API"""
import httpx
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.core.config import settings

router = APIRouter(tags=["Health"])


async def _check_llm_reachable() -> dict:
    """检查 LLM 是否可达"""
    base_url = settings.LLM_BASE_URL
    api_key = settings.LLM_API_KEY
    if not base_url or not api_key:
        return {"reachable": False, "reason": "未配置 LLM_BASE_URL 或 LLM_API_KEY"}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                f"{base_url.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {api_key}"}
            )
            if resp.status_code == 200:
                return {"reachable": True, "reason": "ok"}
            return {"reachable": False, "reason": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"reachable": False, "reason": str(e)[:200]}


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """健康检查端点"""
    llm_status = await _check_llm_reachable()
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "healthy",
            "service": "ai-bi-report-api",
            "version": "2.0.0",
            "llm": llm_status
        }
    )