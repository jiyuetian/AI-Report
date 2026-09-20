"""独立探针：脱离 uvicorn 进程，单独验证 LLMGateway 真实调用是否会导致进程崩溃。
用法: <python312> probe_llm.py
"""
import os
import sys
import asyncio
import traceback

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BACKEND_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


async def main():
    print("[probe] 开始导入 app.core.llm_gateway ...", flush=True)
    from app.core.llm_gateway import LLMGateway, LLMRequest
    print("[probe] 导入完成", flush=True)

    gw = LLMGateway()
    print(f"[probe] mock_mode={gw.mock_mode}", flush=True)

    req = LLMRequest(
        prompt="只回复一个词：pong",
        json_mode=False,
        max_tokens=16,
        temperature=0.1,
        request_id="probe-1",
        user_id="probe",
        timeout=30,
    )

    print("[probe] ---- 1) 直接 httpx 调用（对照） ----", flush=True)
    try:
        import httpx
        from app.core.config import settings
        async with httpx.AsyncClient(
            base_url=settings.LLM_BASE_URL,
            headers={
                "Authorization": f"Bearer {settings.LLM_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=30,
        ) as c:
            r = await c.post("/chat/completions", json={
                "model": settings.LLM_MODEL,
                "messages": [{"role": "user", "content": "只回复一个词：pong"}],
                "max_tokens": 16,
                "stream": False,
            })
            print(f"[probe] 裸httpx status={r.status_code}", flush=True)
            print(f"[probe] 裸httpx body={r.text[:300]}", flush=True)
    except Exception as e:
        print(f"[probe] 裸httpx 异常: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()

    print("[probe] ---- 2) 复用长生命周期 self.client（网关同款） ----", flush=True)
    try:
        r = await gw.client.post("/chat/completions", json={
            "model": None,
            "messages": [{"role": "user", "content": "只回复一个词：pong"}],
            "max_tokens": 16,
        }, timeout=30)
        print(f"[probe] gw.client status={r.status_code}", flush=True)
        print(f"[probe] gw.client body={r.text[:300]}", flush=True)
    except Exception as e:
        print(f"[probe] gw.client 异常: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()

    print("[probe] ---- 3) 走完整 LLMGateway.chat_complete ----", flush=True)
    try:
        resp = await gw.chat_complete(req)
        print(f"[probe] chat_complete success={resp.success} err={resp.error}", flush=True)
        print(f"[probe] content={resp.content!r}", flush=True)
    except Exception as e:
        print(f"[probe] chat_complete 异常: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()

    print("[probe] 全部完成", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
    print("[probe] 进程正常退出 code=0", flush=True)
