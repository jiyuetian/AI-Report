"""健康检查API"""
import asyncio
import time
import httpx
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.deployment_posture import posture_summary

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
    fail-closed 判不可达，符合原 fail-closed 哲学。night19 任务 A：/health 不再直接调用本函数
    （改后台探针 + 进程内缓存，见 _run_llm_probe / GET /health/llm）；本函数作为真实探针由后台任务调用。
    """
    # 2026-09-28 修复（Item2 P0）：探针必须测「真实 provider 链」(LLM_PROVIDERS 经 llm_gateway 失败转移)，
    # 而非遗留单 provider 配置(settings.LLM_MODEL)。否则会出现：探针用旧配置判可达=True，
    # 但 brain/run 实际走 LLM_PROVIDERS，其中 zhipu 余额不足(HTTP 400 balance=0)/sensenova 429 等
    # 真实失败在 S3 才暴露，导致「AI 失败却没弹窗」(M1 弹窗被漏触发，看板被静默规则兜底)。
    # 用 llm_chat 真实打一次最小请求：任一 provider 成功即可达；全部失败(balance=0/429/超时)即不可达→弹用户选择。
    providers = getattr(settings, "LLM_PROVIDERS", None)
    if providers:
        try:
            from app.core.llm_gateway import llm_chat
            try:
                # night19 任务 A：去掉 2026-10-03 的 max_retries=0 + 18s 假快路径 hack。
                # 用户拍板：18s 上限不可取——探针应反映真实链路可用性（可靠、可追溯），允许跑几分钟；
                # 保留 llm_chat 内部真实重试语义（MAX_RETRIES），整体上限放宽到 180s。
                # 2026-11-02 调整：探针已改为「建议信号」（brain 管线乐观放行，不再硬锁全链路），
                # 故此处只需快速探一次真实链路是否可用即可，缩短上限避免无意义长阻塞。
                # 2026-11-12（#695）：原探针「请只回复一个字：好」是 8 字符自然语言请求，
                # 与真实质检/图表生成的长 JSON 负载完全脱节，短 prompt 绿灯不代表 AI 可用。
                # 改成 json_mode 的真实量级 JSON 请求（约 2k 字符），且必须能解析出 JSON。
                _probe_fields = "\n".join(
                    f"- 字段{i} (VARCHAR): 非空{900 + i}/1000行, 空值率0.0{i}, 唯一值{30 + i}个"
                    for i in range(10)
                )
                _probe_prompt = (
                    "你是数据质量分析师。以下是一张数据表的结构与统计，请判断是否存在规则未覆盖的潜在问题，"
                    "最多返回2条；只返回合法JSON，不要解释文字、不要推理过程、不要代码块围栏。"
                    "\n\n## 表结构\n" + _probe_fields +
                    "\n\n## 输出格式\n" +
                    '{"issues":[{"column":"真实字段名","severity":"warning","message":"概括","detail":"说明","row_count":1}]}' +
                    "\n无问题则返回 " + '{"issues":[]}' + "。"
                )
                resp = await asyncio.wait_for(
                    llm_chat(prompt=_probe_prompt, json_mode=True, timeout=45.0,
                             respect_cooldown=False, max_retries=1),
                    timeout=90.0,
                )
            except asyncio.TimeoutError:
                return {"reachable": False, "reason": "gateway 真实负载探针超时(>90s)"}
            if getattr(resp, "success", False) and getattr(resp, "response_json", None) is not None:
                return {"reachable": True, "reason": "ok (gateway·真实JSON负载探针)"}
            return {"reachable": False, "reason": f"gateway 真实负载探针不可用: {getattr(resp, 'error', '无有效JSON')}"}
        except Exception as e:
            return {"reachable": False, "reason": f"gateway_probe_error: {str(e)[:200]}"}

    # 遗留单 provider 兜底（仅当未配置 LLM_PROVIDERS 时走旧逻辑）
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


# ─────────────────────────────────────────────────────────────────────────────
# night19 任务 A：LLM 健康探针改造（去 18s 假快路径 + 后台探针 + 进程内缓存）
#   /health 立即返回缓存结果，不阻塞；/health/llm 返回缓存并触发后台真实探针；
#   真实探针走 _check_llm_reachable（真实 provider 链 + 真实重试，上限 180s），写进程内缓存。
# ─────────────────────────────────────────────────────────────────────────────
_LLM_PROBE_CACHE: dict = {
    "state": "unknown",          # probing | ok | fail | unknown
    "llm_reachable": None,       # True | False | None
    "checked_at": None,          # ISO 时间字符串
    "elapsed_ms": None,          # 本次探针耗时
    "reason": None,              # 人类可读说明
    "expected_max_wait_s": 90,   # 预期最长等待（前端醒目提示用）
}
# 2026-11-12（#695）：探针缓存 TTL。原实现 checked_at 可能停在昨天，/health 仍返回绿灯。
_LLM_PROBE_TTL_SECONDS = 120
_PROBE_LOCK = asyncio.Lock()


def _now_iso() -> str:
    from datetime import datetime
    return datetime.utcnow().isoformat()


def _probe_is_stale() -> bool:
    """缓存超过 TTL 即视为过期，禁止把隔夜绿灯当成本次可达。"""
    ts = _LLM_PROBE_CACHE.get("checked_at")
    if not ts:
        return True
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() > _LLM_PROBE_TTL_SECONDS
    except Exception:
        return True


async def _run_llm_probe() -> None:
    """真实探针（后台）：跑 _check_llm_reachable，把结果写进程内缓存。

    锁串行化；若已在探测中则直接返回，避免并发叠加。异常绝不抛出（fail-fast），
    以免拖垮 /health。
    """
    async with _PROBE_LOCK:
        if _LLM_PROBE_CACHE.get("state") == "probing":
            return
        _LLM_PROBE_CACHE.update(
            state="probing", llm_reachable=None,
            checked_at=_now_iso(), elapsed_ms=None, reason="后台探测中",
        )
        try:
            t0 = time.monotonic()
            res = await _check_llm_reachable(attempts=3)  # 真实重试语义（上限 180s）
            elapsed = int((time.monotonic() - t0) * 1000)
            reachable = bool(res.get("reachable"))
            _LLM_PROBE_CACHE.update(
                state="ok" if reachable else "fail",
                llm_reachable=reachable,
                checked_at=_now_iso(),
                elapsed_ms=elapsed,
                reason=res.get("reason"),
            )
        except Exception as e:  # 探针异常绝不抛，避免拖垮 /health
            _LLM_PROBE_CACHE.update(
                state="fail", llm_reachable=False,
                checked_at=_now_iso(),
                reason=f"probe_error: {str(e)[:200]}",
            )


def _trigger_probe_bg() -> None:
    """非阻塞触发一次后台探针（调用方不等待）。"""
    try:
        asyncio.create_task(_run_llm_probe())
    except RuntimeError:
        pass  # 无运行中的事件循环（如模块导入期）→ 跳过


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """健康检查端点（不阻塞在长探针上）。

    P4-3 修复：只返回服务状态与版本，不泄露内部 provider 错误/会话 sid 等敏感信息。
    night19 任务 A：立即返回缓存的上一次 LLM 探针结果；若从未探测过则后台触发一次真实探针。
    """
    state_now = _LLM_PROBE_CACHE.get("state")
    if state_now != "probing" and (state_now in (None, "unknown") or _probe_is_stale()):
        # 过期缓存立即作废，避免隔夜绿灯误导（reachable 置 None 而不是沿用旧值）
        _LLM_PROBE_CACHE.update(state="unknown", llm_reachable=None,
                                reason="探针结果已过期，正在重新探测")
        _trigger_probe_bg()
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "healthy",
            "service": "ai-bi-report-api",
            "version": "2.0.0",
            "llm_reachable": _LLM_PROBE_CACHE.get("llm_reachable"),
            "llm_state": _LLM_PROBE_CACHE.get("state"),
            "checked_at": _LLM_PROBE_CACHE.get("checked_at"),
            "probe_ttl_s": _LLM_PROBE_TTL_SECONDS,
            # Task #716：只下发一个布尔摘要，不暴露具体未通过项给外部探测者
            "deployment": posture_summary(),
        }
    )


@router.get("/health/llm", status_code=status.HTTP_200_OK)
async def health_llm_probe():
    """LLM 链路探针端点：返回缓存结果 + 触发后台真实探针。

    前端轮询直到 state 离开 probing 后显示 ok/fail。预期最长等待见 expected_max_wait_s。
    """
    state_now = _LLM_PROBE_CACHE.get("state")
    if state_now != "probing":
        # 每次显式调用 /health/llm 都触发一次新探针；过期缓存先作废，不返回隔夜结果。
        if _probe_is_stale():
            _LLM_PROBE_CACHE.update(state="unknown", llm_reachable=None,
                                    reason="探针结果已过期，正在重新探测")
        _trigger_probe_bg()
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "state": _LLM_PROBE_CACHE.get("state"),
            "llm_reachable": _LLM_PROBE_CACHE.get("llm_reachable"),
            "checked_at": _LLM_PROBE_CACHE.get("checked_at"),
            "elapsed_ms": _LLM_PROBE_CACHE.get("elapsed_ms"),
            "reason": _LLM_PROBE_CACHE.get("reason"),
            "expected_max_wait_s": _LLM_PROBE_CACHE.get("expected_max_wait_s"),
        }
    )