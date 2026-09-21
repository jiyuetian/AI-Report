"""
LLM 网关 API - M2-02a/b/c
提供LLM调用、模板渲染、限流状态查询等接口
"""
from fastapi import APIRouter, HTTPException, status, Depends, Request
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_admin
from app.core.llm_gateway import (
    LLMGateway, LLMRequest, LLMResponse,
    LLMConfigManager, RateLimiter, rate_limiter,
    get_llm_gateway, llm_chat
)
from app.core.brain_config_manager import BrainConfigManager

router = APIRouter(prefix="/llm", tags=["LLM"])


# ============== 请求/响应模型 ==============

class ChatRequest(BaseModel):
    """聊天完成请求"""
    prompt: str = Field(..., description="直接输入的prompt")
    template_key: Optional[str] = Field(None, description="使用模板（如goal_prompt_v1）")
    template_context: Optional[Dict[str, Any]] = Field(None, description="模板上下文变量")
    json_mode: bool = Field(True, description="强制JSON输出")
    max_tokens: int = Field(2000)
    temperature: float = Field(0.7)
    user_id: str = Field("anonymous")


class ChatResponse(BaseModel):
    """聊天完成响应"""
    success: bool
    content: Optional[str]
    response_json: Optional[Dict]
    tokens_used: int
    tokens_prompt: int
    tokens_completion: int
    duration_ms: int
    model: str
    retry_count: int
    fallback_used: bool
    error: Optional[str]


class TemplateRenderRequest(BaseModel):
    """模板渲染请求"""
    template_key: str = Field(..., description="模板key，如goal_prompt_v1")
    context: Dict[str, Any] = Field(..., description="模板上下文")


class RateLimitStatus(BaseModel):
    """限流状态"""
    running: int
    max_concurrent: int
    queued: int
    available_slots: int


class UsageResponse(BaseModel):
    """用量响应"""
    user_id: str
    date: str
    tokens_used: int
    tokens_limit: int
    remaining: int


# ============== API端点 ==============

@router.post("/chat", response_model=ChatResponse)
async def chat_complete(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    LLM聊天完成
    
    支持两种方式：
    1. 直接传prompt
    2. 传template_key + template_context（从DB读取模板并渲染）
    
    特性：
    - 自动限流排队
    - 超时重试≤3次
    - JSON模式强制输出
    - Token计量
    """
    # 处理模板
    final_prompt = request.prompt
    if request.template_key:
        template_str = await LLMConfigManager.load_template(db, request.template_key)
        final_prompt = LLMConfigManager.render_template(
            template_str, 
            request.template_context or {}
        )
    
    # 调用LLM
    gateway = get_llm_gateway()
    llm_request = LLMRequest(
        prompt=final_prompt,
        json_mode=request.json_mode,
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        user_id=request.user_id
    )
    
    response = await gateway.chat_complete(llm_request)
    
    return ChatResponse(
        success=response.success,
        content=response.content,
        response_json=response.response_json,
        tokens_used=response.tokens_used,
        tokens_prompt=response.tokens_prompt,
        tokens_completion=response.tokens_completion,
        duration_ms=response.duration_ms,
        model=response.model,
        retry_count=response.retry_count,
        fallback_used=response.fallback_used,
        error=response.error
    )


@router.post("/chat/completions", response_model=ChatResponse)
async def openai_compatible_chat(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    OpenAI兼容接口
    
    支持标准OpenAI请求格式：
    ```json
    {
      "model": "gpt-4",
      "messages": [{"role": "user", "content": "Hello"}]
    }
    ```
    """
    body = await request.json()
    
    # 提取messages中的content
    messages = body.get("messages", [])
    prompt = "\n".join([m.get("content", "") for m in messages if m.get("role") == "user"])
    
    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "NO_PROMPT", "message": "请求中未找到user角色的prompt"}
        )
    
    # 调用
    response = await llm_chat(
        prompt=prompt,
        json_mode=body.get("response_format", {}).get("type") == "json_object",
        user_id=body.get("user", "anonymous")
    )
    
    return ChatResponse(
        success=response.success,
        content=response.content,
        response_json=response.response_json,
        tokens_used=response.tokens_used,
        tokens_prompt=response.tokens_prompt,
        tokens_completion=response.tokens_completion,
        duration_ms=response.duration_ms,
        model=response.model,
        retry_count=response.retry_count,
        fallback_used=response.fallback_used,
        error=response.error
    )


@router.post("/template/render")
async def render_template(
    request: TemplateRenderRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    渲染Jinja2模板
    
    从brain_configs读取模板，使用context渲染
    
    Example:
    ```json
    {
      "template_key": "goal_prompt_v1",
      "context": {
        "theme": "担保风控",
        "grain": "detail",
        "fields": ["担保金额", "抵押率"]
      }
    }
    ```
    """
    try:
        template_str = await LLMConfigManager.load_template(db, request.template_key)
        rendered = LLMConfigManager.render_template(template_str, request.context)
        
        return {
            "success": True,
            "template_key": request.template_key,
            "rendered": rendered,
            "template_version": "v1"  # 可从config中获取
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "TEMPLATE_NOT_FOUND", "message": str(e)}
        )


@router.get("/rate-limit/status", response_model=RateLimitStatus)
async def get_rate_limit_status():
    """
    获取限流队列状态
    
    显示：
    - 当前运行数
    - 最大并发数
    - 队列等待数
    - 可用槽位数
    """
    status = await rate_limiter.get_queue_status()
    return RateLimitStatus(**status)


@router.get("/usage/{user_id}", response_model=UsageResponse)
async def get_usage(user_id: str):
    """
    获取用户Token使用量
    
    日限额：100,000 tokens
    """
    gateway = get_llm_gateway()
    usage = await gateway.get_usage(user_id)
    return UsageResponse(**usage)


@router.get("/config")
async def get_llm_config(current_user: Dict = Depends(require_admin)):
    """
    获取LLM配置信息（G3：仅管理员，避免泄露内网地址/密钥状态）
    """
    from app.core.config import settings
    from app.core.llm_gateway import MAX_RETRIES, TIMEOUT_SECONDS, CONCURRENCY_LIMIT
    return {
        "base_url": settings.LLM_BASE_URL,
        "model": settings.LLM_MODEL or "glm-5.2",
        "max_retries": MAX_RETRIES,
        "timeout_seconds": TIMEOUT_SECONDS,
        "concurrency_limit": CONCURRENCY_LIMIT,
        "mock_mode": settings.LLM_API_KEY == "" or settings.LLM_API_KEY == "mock-key-for-dev",
        "key_configured": bool(settings.LLM_API_KEY)
    }


@router.post("/_internal/test-retry")
async def test_retry_mechanism(
    fail_count: int = 2,
    user_id: str = "test"
):
    """
    测试重试机制（内部接口）
    
    模拟指定次数失败后成功
    """
    # 这里可以实现一个模拟的LLM调用，故意失败指定次数
    # 实际测试可以使用断网等真实场景
    
    return {
        "message": "重试测试",
        "fail_count": fail_count,
        "expected_retries": min(fail_count, 3),
        "test_method": "请手动测试：1) 断网 2) 发起请求 3) 观察日志中的重试"
    }


# ============== R3返工: Mock字段测试 ==============

@router.get("/_internal/test-mock-response")
async def test_mock_response_fields():
    """
    测试Mock响应字段名 (R3返工)
    
    验证字段名对齐Schema:
    - chart_type (不是type)
    - x_field (不是x)
    - y_field (不是y)
    - value_field (不是value)
    - category_field (不是category)
    """
    from app.core.llm_gateway import LLMGateway, LLMRequest
    
    gateway = LLMGateway()
    request = LLMRequest(
        prompt="推荐图表",
        json_mode=True
    )
    
    mock_response = gateway._generate_mock_response(request)
    
    # 检查图表字段名
    charts = mock_response.get("charts", [])
    field_check = {
        "has_chart_type": all("chart_type" in c for c in charts),
        "has_x_field": any("x_field" in c for c in charts),
        "has_y_field": any("y_field" in c for c in charts),
        "has_value_field": any("value_field" in c for c in charts),
        "has_category_field": any("category_field" in c for c in charts),
        "no_old_type_field": not any("type" in c and "chart_type" not in c for c in charts),
        "no_old_x_field": not any("x" in c and "x_field" not in c for c in charts if "x" in c),
    }
    
    return {
        "success": True,
        "mock_response": mock_response,
        "field_check": field_check,
        "all_passed": all(field_check.values()),
        "r3_rework": "Mock字段名对齐Schema"
    }


@router.get("/_internal/test-mock-s1")
async def test_mock_s1_fields():
    """
    测试S1 Mock字段 (R3返工)
    
    验证返回字段:
    - method: "dictionary"
    - llm_called: false
    """
    from app.core.llm_gateway import LLMGateway, LLMRequest
    
    gateway = LLMGateway()
    request = LLMRequest(
        prompt="主题识别",
        json_mode=True
    )
    
    mock_response = gateway._generate_mock_response(request)
    
    field_check = {
        "has_method": "method" in mock_response,
        "method_is_dictionary": mock_response.get("method") == "dictionary",
        "has_llm_called": "llm_called" in mock_response,
        "llm_called_is_false": mock_response.get("llm_called") == False,
    }
    
    return {
        "success": True,
        "mock_response": mock_response,
        "field_check": field_check,
        "all_passed": all(field_check.values()),
        "r3_rework": "S1 Mock返回method和llm_called字段"
    }


# ============== 错误码规范 ==============

"""
LLM网关错误码：

- LLM_001: 请求超时
- LLM_002: 网络错误
- LLM_003: API密钥无效
- LLM_004: 请求频率超限
- LLM_005: 内容审核不通过
- LLM_006: 服务不可用
- LLM_007: 格式错误（非JSON）
- LLM_008: 模板不存在
- LLM_009: 模板渲染错误
- LLM_010: 降级响应（LLM失败但使用fallback）
"""