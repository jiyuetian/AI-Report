"""LLM 多 key 容错验证（不联网，用 httpx.MockTransport 拦截 /chat/completions）。

覆盖：
- 切 key 成功：provider#0 返 429 → 切 provider#1 返 200
- 全败降级：两个 provider 都 429 → success=False, fallback_used=True
- 4xx 立即跳：provider#0 返 401（key 无效）→ 不内层重试，直接切 provider#1
- 超时切 key：provider#0 抛 TimeoutException → 切 provider#1 成功

运行：从 backend/ 目录 `python -m pytest tests/test_llm_multikeys.py -q`
"""
import asyncio
import httpx
import pytest

from app.core.llm_gateway import LLMGateway, LLMRequest, LLMResponse


def _mock_client(status: int, json_body=None, raise_exc=None):
    async def handler(request):
        if raise_exc is not None:
            raise raise_exc
        return httpx.Response(status, json=json_body or {})
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://mock")


def _make_gw(behaviors: dict):
    """behaviors: {provider_name: ("429"|"401"|"200"|"timeout")}。返回 (gw, calls)。"""
    calls = {}

    def factory(prov):
        name = prov.get("name")
        # 调用次数在 handler 里按 name 累加（_get_client 有缓存，构造只一次）
        async def handler(request):
            calls[name] = calls.get(name, 0) + 1
            b = behaviors.get(name)
            if b == "429":
                return httpx.Response(429, json={"error": "rate limited"}, headers={"retry-after": "0"})
            if b == "401":
                return httpx.Response(401, json={"error": "unauthorized"})
            if b == "timeout":
                raise httpx.ConnectTimeout("mock timeout")
            # 200
            return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok": true}'}}]})
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://mock")

    gw = LLMGateway(providers=[
        {"name": "p0", "base_url": "http://p0", "api_key": "sk-p0", "model": "m0"},
        {"name": "p1", "base_url": "http://p1", "api_key": "sk-p1", "model": "m1"},
    ])
    gw._get_client = factory
    return gw, calls


def _run(gw: LLMGateway):
    async def _go():
        return await gw.chat_complete(LLMRequest(prompt="x", json_mode=True), fallback_response={"ok": False})
    return asyncio.run(_go())


def test_failover_429_then_success():
    gw, calls = _make_gw({"p0": "429", "p1": "200"})
    resp = _run(gw)
    assert isinstance(resp, LLMResponse)
    assert resp.success is True
    assert calls.get("p1", 0) >= 1  # provider#1 被调用（切 key 成功）
    assert calls.get("p0", 0) >= 1


def test_all_keys_failed():
    gw, calls = _make_gw({"p0": "429", "p1": "429"})
    resp = _run(gw)
    assert resp.success is False
    assert resp.fallback_used is True
    assert calls.get("p0", 0) >= 1 and calls.get("p1", 0) >= 1


def test_4xx_immediate_jump_no_retry():
    gw, calls = _make_gw({"p0": "401", "p1": "200"})
    resp = _run(gw)
    assert resp.success is True
    # 401 属 key 无效，内层不重试：p0 只应被调用 1 次
    assert calls.get("p0", 0) == 1
    assert calls.get("p1", 0) >= 1


def test_timeout_then_success():
    gw, calls = _make_gw({"p0": "timeout", "p1": "200"})
    resp = _run(gw)
    assert resp.success is True
    assert calls.get("p1", 0) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
