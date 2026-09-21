"""LLM 网关 - M2-02a/b/c
OpenAI兼容封装 + Jinja2模板 + token计量 + 限流队列
"""
import os
import json
import asyncio
import time
from typing import Dict, Any, List, Optional, AsyncGenerator
from dataclasses import dataclass
from jinja2 import Template
import httpx
from fastapi import HTTPException
import redis.asyncio as redis
from datetime import datetime
import re


def _extract_json(text: str) -> Optional[Any]:
    """从可能含推理文本的LLM输出中提取首个完整JSON对象/数组"""
    if not text:
        return None
    text = text.strip()
    # 直接解析
    try:
        return json.loads(text)
    except Exception:
        pass
    # 用花括号平衡匹配提取首个 {...}
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        while start != -1:
            depth = 0
            in_str = False
            escape = False
            for i in range(start, len(text)):
                ch = text[i]
                if in_str:
                    if escape:
                        escape = False
                    elif ch == "\\":
                        escape = True
                    elif ch == '"':
                        in_str = False
                    continue
                if ch == '"':
                    in_str = True
                elif ch == opener:
                    depth += 1
                elif ch == closer:
                    depth -= 1
                    if depth == 0:
                        candidate = text[start:i + 1]
                        try:
                            return json.loads(candidate)
                        except Exception:
                            break
                if depth < 0:
                    break
                if depth == 0 and i > start:
                    break
            start = text.find(opener, start + 1)
    return None

# 从settings加载配置（确保.env文件生效）
try:
    from app.core.config import settings, get_llm_provider_list
    LLM_API_KEY = settings.LLM_API_KEY or "mock-key-for-dev"
    LLM_BASE_URL = settings.LLM_BASE_URL or "http://localhost:8001/v1"
    LLM_MODEL = settings.LLM_MODEL or "gpt-4"
    REDIS_URL = settings.REDIS_URL or "redis://localhost:6379/1"
except Exception:
    # 兜底
    LLM_API_KEY = os.getenv("LLM_API_KEY", "mock-key-for-dev")
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:8001/v1")
    LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4")
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/1")

redis_client = redis.from_url(REDIS_URL, decode_responses=True)

MAX_RETRIES = 2  # 每 key 内瞬时重试 2 次（初始 1 + 重试 2 = 3 次）；外层再逐 provider 切换


def _mask(text: str) -> str:
    """脱敏：遮蔽响应错误中的密钥片段（sk-/nvapi-/agnes- 前缀），仅保留前缀避免误伤模型名。"""
    if not text:
        return text
    return re.sub(r'(sk|nvapi|agnes)[-A-Za-z0-9]{6,}', r'\1-***', text)
# 2026-09-20 放宽至 120s：NVIDIA nemotron-3.5-lightning 推理模型经 7897 代理出口，
# 图表 JSON 真实生成常需 50~120s，原 60s 会让单次调用未返回即超时→重试→降级规则兜底。
# 配合 BRAIN_S3_LLM_TIMEOUT=180（外层包裹）给足总时长，让慢推理模型返回以点亮绿标。
TIMEOUT_SECONDS = 120
CONCURRENCY_LIMIT = 2  # 并发限制


@dataclass
class LLMResponse:
    """LLM响应结构"""
    success: bool
    content: Optional[str]
    response_json: Optional[Dict] = None
    tokens_used: int = 0
    tokens_prompt: int = 0
    tokens_completion: int = 0
    duration_ms: int = 0
    model: str = ""
    error: Optional[str] = None
    retry_count: int = 0
    fallback_used: bool = False


@dataclass
class LLMRequest:
    """LLM请求结构"""
    prompt: str = ""  # 最终渲染后的prompt（messages 优先时可留空）
    json_mode: bool = True  # 强制JSON输出
    max_tokens: int = 2000
    temperature: float = 0.7
    request_id: str = ""
    user_id: str = ""
    timeout: Optional[float] = None  # 单次调用超时（秒），为空则用全局默认
    model: Optional[str] = None  # 模型覆盖（默认用 settings.LLM_MODEL）


class LLMConfigManager:
    """LLM配置管理 - 从DB读取Jinja2模板"""
    
    _cached_templates: Dict[str, Template] = {}
    
    @staticmethod
    async def load_template(db, template_key: str, version: Optional[str] = None) -> str:
        """
        从brain_configs加载Jinja2模板
        
        Args:
            template_key: 如 "goal_prompt_v1", "theme_recognition_v2"
            version: 模板版本，None则使用最新
        """
        from app.core.brain_config_manager import BrainConfigManager
        
        config = await BrainConfigManager.get_config(db, template_key)
        if not config:
            raise ValueError(f"模板不存在: {template_key}")
        
        content = config.get("content", {})
        template_str = content.get("template", "")
        
        if not template_str:
            raise ValueError(f"模板内容为空: {template_key}")
        
        return template_str
    
    @staticmethod
    def render_template(template_str: str, context: Dict[str, Any]) -> str:
        """渲染Jinja2模板"""
        template = Template(template_str)
        return template.render(**context)


class TokenCounter:
    """Token计数器 - 基于字符估计"""
    
    # 简单估算：1 token ≈ 4个字符（中文）
    CHARS_PER_TOKEN = 4
    
    @staticmethod
    def estimate(text: str) -> int:
        """估算token数量"""
        return max(1, len(text) // TokenCounter.CHARS_PER_TOKEN)
    
    @staticmethod
    def count_message(messages: List[Dict]) -> Dict[str, int]:
        """计算消息列表的token"""
        prompt_text = "\n".join([m.get("content", "") for m in messages])
        return {
            "prompt": TokenCounter.estimate(prompt_text),
            "total": TokenCounter.estimate(prompt_text) + 100  # 估算回复
        }


class RateLimiter:
    """限流器 - 并发限制队列（Redis不可用时降级为本地信号量）"""
    
    def __init__(self, max_concurrent: int = CONCURRENCY_LIMIT):
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.queue_key = "llm:request_queue"
        self.running_key = "llm:running_count"
        self._redis_available = None
        self._local_count = 0
    
    async def _check_redis(self) -> bool:
        """检查Redis是否可用"""
        if self._redis_available is not None:
            return self._redis_available
        try:
            await redis_client.ping()
            self._redis_available = True
        except Exception:
            self._redis_available = False
            print("[限流] Redis不可用，降级为本地信号量")
        return self._redis_available
    
    async def acquire(self, request_id: str) -> bool:
        """
        请求限流槽位
        支持Redis可用时排队，Redis不可用时降级为本地信号量
        """
        redis_ok = await self._check_redis()
        
        if redis_ok:
            try:
                return await self._acquire_redis(request_id)
            except Exception:
                self._redis_available = False
                print("[限流] Redis异常，降级为本地信号量")
        
        # 本地信号量降级
        await self.semaphore.acquire()
        self._local_count += 1
        return True
    
    async def _acquire_redis(self, request_id: str) -> bool:
        """基于Redis的限流"""
        running = int(await redis_client.get(self.running_key) or 0)
        
        if running >= self.max_concurrent:
            await redis_client.lpush(self.queue_key, request_id)
            while True:
                await asyncio.sleep(0.5)
                queue = await redis_client.lrange(self.queue_key, -1, -1)
                if queue and queue[0] == request_id:
                    await redis_client.rpop(self.queue_key)
                    break
        
        await redis_client.incr(self.running_key)
        return True
    
    async def release(self):
        """释放限流槽位"""
        redis_ok = await self._check_redis()
        if redis_ok:
            try:
                await redis_client.decr(self.running_key)
                return
            except Exception:
                self._redis_available = False
        
        self.semaphore.release()
        self._local_count -= 1
    
    async def get_queue_status(self) -> Dict:
        """获取队列状态"""
        redis_ok = await self._check_redis()
        if redis_ok:
            try:
                running = int(await redis_client.get(self.running_key) or 0)
                queued = await redis_client.llen(self.queue_key)
                return {
                    "running": running,
                    "max_concurrent": self.max_concurrent,
                    "queued": queued,
                    "available_slots": max(0, self.max_concurrent - running)
                }
            except Exception:
                self._redis_available = False
        
        return {
            "running": self._local_count,
            "max_concurrent": self.max_concurrent,
            "queued": 0,
            "available_slots": max(0, self.max_concurrent - self._local_count),
            "mode": "local_semaphore"
        }


# 全局限流器实例
rate_limiter = RateLimiter(CONCURRENCY_LIMIT)


class LLMGateway:
    """
    LLM 网关 - 核心调用类
    
    功能：
    1. OpenAI兼容API调用
    2. Jinja2模板渲染
    3. JSON模式强制输出
    4. 超时重试≤3次
    5. Token计量
    6. 并发限流队列
    7. 错误处理与降级
    """
    
    def __init__(self, providers: Optional[List[Dict]] = None):
        # providers: provider 列表（每项 {name,base_url,api_key,model,...}）。
        # 缺省则从 config.get_llm_provider_list() 读取（含单 key 回退）。
        self.providers = providers if providers is not None else get_llm_provider_list()
        self._clients: Dict[str, httpx.AsyncClient] = {}  # name -> client 惰性池
        self.mock_mode = not self.providers  # 无可用 provider → Mock 模式

    def _build_client(self, prov: Dict) -> httpx.AsyncClient:
        base_url = prov.get("base_url") or "http://localhost:8001/v1"
        api_key = prov.get("api_key") or "mock-key-for-dev"
        return httpx.AsyncClient(
            base_url=base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            timeout=TIMEOUT_SECONDS
        )

    def _get_client(self, prov: Dict) -> httpx.AsyncClient:
        name = prov.get("name", "default")
        if name not in self._clients:
            self._clients[name] = self._build_client(prov)
        return self._clients[name]
    
    async def chat_complete(
        self,
        request: LLMRequest,
        fallback_response: Optional[Dict] = None,
        messages: Optional[List[Dict]] = None
    ) -> LLMResponse:
        """
        基础聊天完成
        
        Args:
            request: LLM请求
            fallback_response: 降级响应（当全部重试失败时返回）
        """
        start_time = time.time()
        request_id = request.request_id or str(int(time.time() * 1000))
        
        # 1. 限流检查
        await rate_limiter.acquire(request_id)
        
        try:
            # 2. 构建消息：优先使用调用方传入的 messages；否则按 json_mode 决定系统提示
            if messages is None:
                system_content = (
                    "你是一个专业的数据分析助手，必须以JSON格式返回结果。"
                    if request.json_mode else
                    "你是一个专业的数据分析助手，请用自然流畅的中文回答，不要返回JSON。"
                )
                messages = [
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": request.prompt}
                ]
            
            # Mock 模式：无可用 provider，直接返回模拟数据
            if self.mock_mode:
                await asyncio.sleep(0.5)  # 模拟延迟
                mock_response = self._generate_mock_response(request)
                duration_ms = int((time.time() - start_time) * 1000)
                return LLMResponse(
                    success=True,
                    content=json.dumps(mock_response, ensure_ascii=False),
                    response_json=mock_response,
                    tokens_used=TokenCounter.estimate(request.prompt) + 500,
                    tokens_prompt=TokenCounter.estimate(request.prompt),
                    tokens_completion=500,
                    duration_ms=duration_ms,
                    model="mock-llm",
                    retry_count=0,
                )

            last_error = None
            # 外层：逐个 provider 容错（多 key / 跨 provider 切换）
            for pi, prov in enumerate(self.providers):
                client = self._get_client(prov)
                prov_name = prov.get("name", f"provider#{pi}")
                base_url = prov.get("base_url") or ""
                model = request.model or prov.get("model") or "gpt-4"
                need_business = "sensenova" in (base_url or "")  # SenseNova 需 business_type
                is_kimi = "kimi" in (model or "")  # kimi 仅允许 temperature=1

                key_exhausted = False
                # 内层：单 key 内瞬时重试（MAX_RETRIES 次）
                for retry in range(MAX_RETRIES + 1):
                    try:
                        print(f"[LLM] provider {prov_name} attempt {retry + 1}/{MAX_RETRIES + 1}, request_id={request_id}")
                        request_body = {
                            "model": model,
                            "messages": messages,
                            "max_tokens": request.max_tokens,
                            "temperature": 1.0 if is_kimi else request.temperature,
                        }
                        if need_business:
                            request_body["business_type"] = "chat"
                        if request.json_mode:
                            request_body["response_format"] = {"type": "json_object"}

                        eff_timeout = getattr(request, 'timeout', None) or TIMEOUT_SECONDS
                        response = await client.post(
                            "/chat/completions",
                            json=request_body,
                            timeout=eff_timeout
                        )
                        response.raise_for_status()
                        data = response.json()
                        content = data["choices"][0]["message"]["content"]
                        response_json = None
                        if request.json_mode:
                            response_json = _extract_json(content)
                            # 若JSON提取失败则不视为成功（交给上层降级），避免抛异常中断
                            if response_json is None:
                                raise ValueError("LLM响应未包含有效JSON")
                        usage = data.get("usage", {})
                        prompt_tokens = usage.get("prompt_tokens", TokenCounter.estimate(request.prompt))
                        completion_tokens = usage.get("completion_tokens", 0)
                        total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)
                        duration_ms = int((time.time() - start_time) * 1000)
                        await self._record_usage(request.user_id, total_tokens)
                        return LLMResponse(
                            success=True,
                            content=content,
                            response_json=response_json,
                            tokens_used=total_tokens,
                            tokens_prompt=prompt_tokens,
                            tokens_completion=completion_tokens,
                            duration_ms=duration_ms,
                            model=data.get("model", model),
                            retry_count=retry,
                        )
                    except httpx.TimeoutException as e:
                        last_error = f"LLM超时(attempt {retry + 1}): {e}"
                        print(f"[LLM] provider {prov_name} {last_error}")
                        if retry < MAX_RETRIES:
                            await asyncio.sleep(2 ** retry)  # 指数退避
                            continue
                        key_exhausted = True
                        break
                    except httpx.NetworkError as e:
                        last_error = f"LLM网络错误(attempt {retry + 1}): {e}"
                        print(f"[LLM] provider {prov_name} {last_error}")
                        if retry < MAX_RETRIES:
                            await asyncio.sleep(2 ** retry)
                            continue
                        key_exhausted = True
                        break
                    except httpx.HTTPStatusError as e:
                        status = e.response.status_code
                        try:
                            err_body = e.response.text[:500]
                        except Exception:
                            err_body = str(e)
                        if status == 429:
                            last_error = f"LLM限流(429, attempt {retry + 1}): {err_body}"
                            print(f"[LLM] provider {prov_name} {last_error}")
                            if retry < MAX_RETRIES:
                                # 优先采用服务端 Retry-After，否则指数退避
                                ra = e.response.headers.get("retry-after")
                                wait = float(ra) if (ra and str(ra).strip().isdigit()) else 2 ** retry
                                await asyncio.sleep(wait)
                                continue
                            key_exhausted = True
                            break
                        else:
                            # 4xx 非 429：key 无效，立即跳下一 provider，不重试
                            last_error = f"LLM API错误(HTTP {status}): {err_body}"
                            print(f"[LLM-FAILOVER] provider {prov_name} 失败({status} key无效)，切换下一 provider")
                            key_exhausted = True
                            break
                    except ValueError as e:
                        # JSON 解析失败：本 key 仅重试 1 次，仍失败则切 key（另一 provider 可能更听话）
                        last_error = f"LLM响应JSON解析失败: {e}"
                        print(f"[LLM] provider {prov_name} {last_error}")
                        if retry < 1:
                            await asyncio.sleep(1)
                            continue
                        key_exhausted = True
                        break
                    except Exception as e:
                        last_error = f"LLM未知错误: {e}"
                        print(f"[LLM] provider {prov_name} {last_error}")
                        key_exhausted = True
                        break
                # 本 provider 失败 → 打 failover 日志（4xx 已打过，避免重复）
                if key_exhausted and "key无效" not in (last_error or ""):
                    print(f"[LLM-FAILOVER] provider {prov_name} 失败({_mask(last_error)})，切换下一 provider")
                # 继续外层循环尝试下一 provider

            # 所有 provider 均失败
            print(f"[LLM-ALL-KEYS-FAILED] {len(self.providers)} 个 provider 均失败，进入降级")
            if fallback_response:
                duration_ms = int((time.time() - start_time) * 1000)
                return LLMResponse(
                    success=False,  # 明确标记为失败
                    content=None,
                    error=last_error or "所有 LLM provider 均失败",
                    tokens_used=0,
                    tokens_prompt=0,
                    tokens_completion=0,
                    duration_ms=duration_ms,
                    model="fallback",
                    retry_count=MAX_RETRIES,
                    fallback_used=True,
                )
            # 无降级响应
            return LLMResponse(
                success=False,
                content=None,
                error=last_error,
                retry_count=MAX_RETRIES,
            )
            
        finally:
            await rate_limiter.release()
    
    def _generate_mock_response(self, request: LLMRequest) -> Dict:
        """生成Mock响应 - 根据prompt类型返回合理结构，字段名来自request上下文"""
        prompt = request.prompt.lower()

        if "主题" in prompt or "theme" in prompt:
            return {
                "theme_tag": "通用分析",
                "confidence": 0.85,
                "reason": "基于字段命名规则推断",
                "matched_keywords": [],
                "method": "dictionary",
                "llm_called": False
            }

        if "目标" in prompt or "goal" in prompt:
            # 从prompt中提取字段名，避免硬编码业务字段
            import re
            field_matches = re.findall(r'[\u4e00-\u9fa5]{2,10}|[a-zA-Z_][a-zA-Z0-9_]{2,20}', request.prompt)
            return {
                "goals": [
                    {"goal_id": "G1", "title": f"整体数据概览", "description": "了解数据整体规模与分布", "type": "概览"},
                    {"goal_id": "G2", "title": f"趋势变化分析", "description": "观察数据随时间的变化趋势", "type": "趋势"},
                    {"goal_id": "G3", "title": f"结构对比分析", "description": "分析各维度的结构与对比关系", "type": "对比"}
                ]
            }

        if "图表" in prompt or "chart" in prompt:
            # 从prompt中提取字段名，动态生成图表
            import re
            fields = re.findall(r'"([^"]+)"', request.prompt)
            if not fields:
                fields = re.findall(r'[\u4e00-\u9fa5]{2,8}', request.prompt)
            # 取前4个作为字段
            used = list(dict.fromkeys(fields))[:4]
            charts = []
            if len(used) >= 2:
                charts.append({
                    "chart_type": "bar",
                    "title": f"{used[1]} vs {used[0]}",
                    "x_field": used[0],
                    "y_field": used[1],
                    "recommendation_score": 0.85
                })
            if len(used) >= 3:
                charts.append({
                    "chart_type": "pie",
                    "title": f"{used[2]}占比",
                    "category_field": used[2],
                    "value_field": used[1] if len(used) > 1 else used[0],
                    "recommendation_score": 0.80
                })
            charts.append({
                "chart_type": "table",
                "title": "数据明细",
                "grain": "detail",
                "recommendation_score": 0.75
            })
            return {"charts": charts}

        return {"status": "success", "message": "Mock LLM响应", "prompt_preview": request.prompt[:100] + "..." if len(request.prompt) > 100 else request.prompt}
    
    async def _record_usage(self, user_id: str, tokens: int):
        """记录token使用量（Redis不可用时忽略）"""
        if not user_id or not tokens:
            return
        
        try:
            date_key = datetime.now().strftime("%Y-%m-%d")
            key = f"quota:usage:{user_id}:{date_key}"
            
            await redis_client.incrby(key, tokens)
            await redis_client.expire(key, 86400 * 7)
        except Exception:
            pass  # Redis不可用时忽略
    
    async def get_usage(self, user_id: str) -> Dict:
        """获取用户token使用量（Redis不可用时返回默认值）"""
        try:
            date_key = datetime.now().strftime("%Y-%m-%d")
            key = f"quota:usage:{user_id}:{date_key}"
            
            usage = int(await redis_client.get(key) or 0)
            return {
                "user_id": user_id,
                "date": date_key,
                "tokens_used": usage,
                "tokens_limit": 100000,
                "remaining": max(0, 100000 - usage)
            }
        except Exception:
            return {
                "user_id": user_id,
                "date": datetime.now().strftime("%Y-%m-%d"),
                "tokens_used": 0,
                "tokens_limit": 100000,
                "remaining": 100000,
                "note": "Redis不可用，使用量统计暂不可用"
            }
    
    async def close(self):
        """关闭所有 provider 客户端连接"""
        for c in self._clients.values():
            try:
                await c.aclose()
            except Exception:
                pass


# 全局网关实例（按需使用，或每次创建新实例）
_llm_gateway: Optional[LLMGateway] = None


def get_llm_gateway() -> LLMGateway:
    """获取LLM网关实例（单例）"""
    global _llm_gateway
    if _llm_gateway is None:
        _llm_gateway = LLMGateway()
    return _llm_gateway


# ============== 便捷函数 ==============

async def llm_chat(
    prompt: str = "",
    messages: Optional[List[Dict]] = None,
    json_mode: bool = True,
    model: Optional[str] = None,
    fallback: Optional[Dict] = None,
    user_id: str = "",
    timeout: Optional[float] = None,
) -> LLMResponse:
    """
    便捷调用函数
    
    2026-09-17：新增 timeout 参数。
    沿用 InsightDesk 的经验——LLM 永远不能成为主流程的单点故障：
    调用方必须能按阶段设定硬超时（如主题识别 20s、图表推荐 45s），
    超时后由各阶段自己的确定性兜底接管，而不是无限等待把整个看板生成拖死。

    Args:
        prompt: 渲染后的提示词（messages 优先时可留空）
        messages: 完整的 messages 列表（[system, user, ...]），传入时直接下发，覆盖自动构建
        json_mode: 是否强制 JSON 输出（False 时走自然语言，系统提示不强制 JSON）
        model: 模型覆盖（默认用 settings.LLM_MODEL）
        fallback: 调用全部失败时返回的降级字典
        user_id: 用于配额统计
    
    Example:
        response = await llm_chat(
            prompt="分析这个数据集",
            json_mode=True,
            fallback={"status": "error", "message": "LLM调用失败"}
        )
    """
    gateway = get_llm_gateway()
    request = LLMRequest(
        prompt=prompt,
        json_mode=json_mode,
        model=model,
        user_id=user_id,
        timeout=timeout,
    )
    return await gateway.chat_complete(request, fallback, messages=messages)