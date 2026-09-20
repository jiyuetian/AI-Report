"""健康检查API"""
import asyncio
import httpx
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.core.config import settings

router = APIRouter(tags=["Health"])


async def _check_llm_reachable(attempts: int = 3) -> dict:
    """检查 LLM 是否可达（fail-closed：任何不确定都判为不可达）。

    判断依据：用 chat/completions 发一次最小真实请求，要求
      1) HTTP 200；
      2) 响应 JSON 含非空 choices（确认真的在完成，而非网关假 200）；
    否则一律判不可达。目的：避免「hello 探针 200、但真实图表生成挂起」的假阳性
    （InsightDesk 踩过的同源坑：轻量探针通过 ≠ 真实负载可用）。
    探针文案避免字面 "ping"：讯飞网关对 content=="ping" 返回 10404「no category
    route found」，故用中性文案。

    重试机制（2026-09-20 加）：NVIDIA nemotron 接口实测偶发超时（约 30% 的调用
    会在 15s 内 ReadTimeout），原单次探针易假阴性→误判不可达→S3 整条降级规则兜底，
    绿标永不亮。故默认重试 attempts 次 + 2s 退避；仅当 attempts 次全失败才
    fail-closed 判不可达，符合原 fail-closed 哲学。health 端点传 attempts=1 保持快速。
    """
    base_url = settings.LLM_BASE_URL
    api_key = settings.LLM_API_KEY
    if not base_url or not api_key:
        return {"reachable": False, "reason": "未配置 LLM_BASE_URL 或 LLM_API_KEY"}
    probe_timeout = 15.0
    last_reason = "未执行探针"
    for attempt in range(attempts):
        try:
            payload = {
                "model": settings.LLM_MODEL,
                "messages": [{"role": "user", "content": "请只回复一个字：好"}],
                # 2026-09-20：max_tokens=5 对商汤/Kimi/DeepSeek 网关类模型过小→返回空 content
                # → 误判不可达 → S3 整条降级规则兜底，绿标永不亮。提到 64 给足余量。
                "max_tokens": 64,
                "stream": False,
            }
            # 商汤网关（token.sensenova.cn）需要 business_type=chat，否则返回空 content
            if "sensenova" in base_url:
                payload["business_type"] = "chat"
            # kimi 系列仅允许 temperature=1，否则 400 invalid_request_error
            if "kimi" in (settings.LLM_MODEL or ""):
                payload["temperature"] = 1
            async with httpx.AsyncClient(timeout=probe_timeout) as client:
                resp = await client.post(
                    f"{base_url.rstrip('/')}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
            if resp.status_code != 200:
                last_reason = f"HTTP {resp.status_code} {resp.text[:120]}"
            else:
                try:
                    data = resp.json()
                except Exception:
                    last_reason = "响应非 JSON"
                    data = None
                if data is not None:
                    choices = (data.get("choices") or []) if isinstance(data, dict) else []
                    content = (choices[0].get("message") or {}).get("content") if choices else None
                    if content:
                        return {"reachable": True, "reason": "ok"}
                    last_reason = "响应无有效 choices（疑似网关假 200）"
        except Exception as e:
            # 探针异常记原因，重试（仍 fail-closed，仅全失败才判不可达）
            last_reason = f"probe_error: {str(e)[:200]}"
        # 非最后一次才退避重试
        if attempt < attempts - 1:
            await asyncio.sleep(2)
    # fail-closed：attempts 次全失败才判不可达，避免冒险挂起
    return {"reachable": False, "reason": last_reason}


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """健康检查端点。

    P4-3 修复：只返回服务状态与版本，不泄露内部 provider 错误/会话 sid 等敏感信息。
    """
    llm_status = await _check_llm_reachable(attempts=1)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "healthy",
            "service": "ai-bi-report-api",
            "version": "2.0.0",
            "llm_reachable": llm_status.get("reachable")
        }
    )