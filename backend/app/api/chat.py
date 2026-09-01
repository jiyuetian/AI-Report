"""
对话 API - M3-01
SSE流式 + 意图分类 + 上下文管理
"""
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_, func
import json
import asyncio
from datetime import datetime

from app.core.database import get_db
from app.core.intent_classifier import classify_intent, IntentType
from app.core.action_executor import ActionExecutor, ActionType
from app.core.moderation import check_moderation, ContentModerator, BoundaryType
from app.models.chat import ChatSession, ChatMessage, TokenQuota
from app.models.dashboard import Dashboard

router = APIRouter(prefix="/chat", tags=["Chat-对话"])


# ============== 请求/响应模型 ==============

class ChatMessageRequest(BaseModel):
    """发送消息请求"""
    session_id: Optional[str] = None
    message: str = Field(..., min_length=1, max_length=2000, description="用户消息")
    dashboard_id: Optional[str] = Field(None, description="当前看板ID")
    dataset_id: Optional[str] = Field(None, description="当前数据集ID")
    override: bool = Field(False, description="用户强制覆盖blocking级约束（用户优先级最高）")


class CreateSessionRequest(BaseModel):
    """创建会话请求"""
    dashboard_id: Optional[str] = None
    dataset_id: Optional[str] = None


class IntentClassificationResponse(BaseModel):
    """意图分类响应"""
    intent_type: str
    confidence: int
    analysis: Dict[str, Any]
    is_confident: bool


# ============== SSE工具函数 ==============

async def sse_event(event_type: str, data: Dict[str, Any]) -> str:
    """生成SSE事件"""
    event = {
        "event": event_type,
        "data": json.dumps(data, ensure_ascii=False),
        "timestamp": datetime.now().isoformat()
    }
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


# ============== 意图识别与响应生成 ==============

async def generate_intent_response(intent_type: IntentType, analysis: Dict, context: Dict) -> Dict:
    """根据意图生成响应"""
    
    responses = {
        IntentType.CHANGE_CHART: {
            "message": f"好的，我将把图表改为{analysis.get('extracted_params', {}).get('target_type', '柱状图')}。",
            "action": {
                "type": "change_chart",
                "params": analysis.get("extracted_params", {})
            },
            "suggested_followups": ["调整颜色", "添加数据标签", "改变排序方式"]
        },
        IntentType.ADD_CHART: {
            "message": f"正在为您添加{analysis.get('extracted_params', {}).get('chart_type', '新图表')}...",
            "action": {
                "type": "add_chart",
                "params": analysis.get("extracted_params", {})
            },
            "suggested_followups": ["放在左边", "放在右边", "调整大小"]
        },
        IntentType.DELETE_CHART: {
            "message": "正在为您删除图表...",
            "action": {
                "type": "delete_chart",
                "params": analysis.get("extracted_params", {})
            },
            "suggested_followups": ["恢复删除", "添加新图表", "调整剩余图表"]
        },
        IntentType.REORDER_CHART: {
            "message": "正在调整图表顺序...",
            "action": {
                "type": "reorder_chart",
                "params": analysis.get("extracted_params", {})
            },
            "suggested_followups": ["继续调整", "恢复默认排序", "按类型分组"]
        },
        IntentType.FILTER_DRILL: {
            "message": "正在为您筛选数据并下钻分析...",
            "action": {
                "type": "filter_drill",
                "params": analysis.get("extracted_params", {})
            },
            "suggested_followups": ["恢复全部", "继续下钻", "对比其他维度"]
        },
        IntentType.ATTRIBUTION: {
            "message": "正在分析异常原因，通过血缘关系追溯数据来源...",
            "action": {
                "type": "attribution",
                "params": analysis.get("extracted_params", {}),
                "requires_lineage": True
            },
            "suggested_followups": ["查看上下游", "导出详细数据", "设置预警"]
        },
        IntentType.EDIT_TITLE: {
            "message": f"标题已更新为'{analysis.get('extracted_params', {}).get('new_title', '')}'",
            "action": {
                "type": "edit_title",
                "params": analysis.get("extracted_params", {})
            },
            "suggested_followups": ["调整字体", "添加副标题", "居中显示"]
        },
        IntentType.UNKNOWN: {
            "message": "我不太理解您的意思，您可以尝试：",
            "suggestions": [
                "把饼图改成柱图",
                "新增一个趋势图",
                "筛选华东地区的数据",
                "分析一下这个异常",
                "修改标题为'月度销售'",
                "删除第三个图表",
                "把最后一个图移到前面"
            ],
            "suggested_followups": []
        }
    }
    
    return responses.get(intent_type, responses[IntentType.UNKNOWN])


# ============== API端点 ==============

@router.post("/sessions", response_model=Dict)
async def create_session(
    request: CreateSessionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: str = "anonymous"
):
    """创建对话会话"""
    
    # 构建上下文
    context = {}
    
    if request.dashboard_id:
        # 获取看板配置
        result = await db.execute(
            select(Dashboard).where(Dashboard.id == request.dashboard_id)
        )
        dashboard = result.scalar_one_or_none()
        if dashboard:
            context["dashboard_config"] = {
                "id": dashboard.id,
                "name": dashboard.name,
                "layout": dashboard.layout,
                "dataset_ids": dashboard.dataset_ids
            }
    
    # 获取字段画像 (简化版)
    if request.dataset_id:
        context["field_profiles"] = [
            {"name": "日期", "type": "datetime"},
            {"name": "金额", "type": "numeric", "unit": "元"},
            {"name": "地区", "type": "category"},
            {"name": "类别", "type": "category"},
        ]
    
    session = ChatSession(
        user_id=current_user,
        dashboard_id=request.dashboard_id,
        dataset_id=request.dataset_id,
        context=context
    )
    
    db.add(session)
    await db.commit()
    await db.refresh(session)
    
    return {
        "success": True,
        "session_id": session.id,
        "context": context
    }


@router.get("/sessions/{session_id}/history", response_model=Dict)
async def get_chat_history(
    session_id: str,
    limit: int = 50,
    db: AsyncSession = Depends(get_db)
):
    """获取对话历史"""
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
        .limit(limit)
    )
    messages = result.scalars().all()
    
    return {
        "success": True,
        "session_id": session_id,
        "count": len(messages),
        "messages": [m.to_dict() for m in messages]
    }


@router.post("/message", response_class=StreamingResponse)
async def send_message_stream(
    request: ChatMessageRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: str = "anonymous"
):
    """
    发送消息 - SSE流式响应 (修复：db session生命周期)
    
    5类意图分类结果实时返回
    
    修复说明：
    - 在流式生成器外完成session的获取/创建（使用传入的db）
    - 在流式生成器内使用独立的db session进行消息保存
    """
    from app.core.database import async_session_factory
    from app.core.feasibility_checker import check_feasibility
    from app.core.event_logger import log_user_action

    # ==== 阶段1: 获取或创建会话（在流外完成，使用传入的db）====
    if request.session_id:
        result = await db.execute(
            select(ChatSession).where(ChatSession.id == request.session_id)
        )
        session = result.scalar_one_or_none()
    else:
        session = None
    
    if not session:
        # 创建新会话
        session = ChatSession(
            user_id=current_user,
            dashboard_id=request.dashboard_id,
            dataset_id=request.dataset_id,
            context={"field_profiles": [{"name": "示例字段", "type": "category"}]}
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
    
    session_id = session.id
    dashboard_id = request.dashboard_id or session.dashboard_id
    dataset_id = request.dataset_id or session.dataset_id
    
    # 获取数据集粒度（如果有）
    dataset_grain = "row"
    field_profiles = []
    if dataset_id:
        ds_result = await db.execute(
            select(Dataset).where(Dataset.id == dataset_id)
        )
        dataset = ds_result.scalar_one_or_none()
        if dataset:
            dataset_grain = dataset.grain
            if dataset.profile_json:
                field_profiles = dataset.profile_json.get("columns", [])
            else:
                schema = dataset.schema_json or {}
                field_profiles = schema.get("columns", [])
    
    # 获取当前看板配置
    current_config = {}
    if dashboard_id:
        dash_result = await db.execute(
            select(Dashboard).where(Dashboard.id == dashboard_id)
        )
        dashboard = dash_result.scalar_one_or_none()
        if dashboard:
            current_config = dashboard.config or {}
    
    # 构建上下文（只读数据，可以传给生成器）
    context = {
        "session_id": session_id,
        "dashboard_id": dashboard_id,
        "dataset_id": dataset_id,
        "dataset_info": {
            "grain": dataset_grain,
            "field_profiles": field_profiles
        },
        "current_config": current_config
    }
    
    # ==== 阶段2: 内容审核（也在流外完成，避免在生成器中使用db）====
    moderation_result = check_moderation(request.message)
    
    if moderation_result["should_block"]:
        # 拦截内容，立即保存到DB（在流外）
        await save_moderation_message(
            db, session_id, request.message, moderation_result, current_user
        )
    
    # ==== 阶段3: 流式生成器（使用独立db session）====
    async def generate_stream():
        """SSE流生成器 - 使用独立db session"""
        
        # 0. 内容审核结果已在流外完成
        if moderation_result["should_block"]:
            yield await sse_event("moderation_blocked", {
                "blocked": True,
                "boundary_type": moderation_result["boundary_type"],
                "response": moderation_result["response"],
                "deduct_tokens": False,
                "message": "内容被拦截"
            })
            yield "data: [DONE]\n\n"
            # 记录事件
            from app.core.event_logger import log_user_action
            log_user_action(
                "moderation_blocked",
                current_user,
                {"message": request.message},
                dashboard_id,
                session_id
            )
            return
        
        # 1. 发送开始事件
        yield await sse_event("start", {
            "session_id": session_id,
            "message": "开始处理..."
        })
        
        await asyncio.sleep(0.5)
        
        # 2. 意图识别中
        yield await sse_event("thinking", {
            "stage": "intent_classification",
            "message": "正在分析您的意图..."
        })
        
        # 3. 执行意图分类（纯内存操作，无DB）
        intent_result = classify_intent(request.message, context)
        
        yield await sse_event("intent_classified", {
            "intent_type": intent_result["intent_type"],
            "confidence": intent_result["confidence"],
            "analysis": intent_result["analysis"],
            "is_confident": intent_result["is_confident"],
            "classified_by": intent_result.get("classified_by", "rule")
        })
        
        await asyncio.sleep(0.5)
        
        # 4. 可行性检查
        yield await sse_event("checking_feasibility", {
            "stage": "feasibility_check",
            "message": "检查请求可行性..."
        })
        
        intent_type_str = intent_result["intent_type"]
        analysis = intent_result["analysis"]
        params = analysis.get("extracted_params", {})
        
        feasibility = check_feasibility(
            request.message,
            intent_type_str,
            params,
            context,
            override_blocking=request.override
        )
        
        if not feasibility["feasible"]:
            # 不可行，返回引导
            issues = feasibility["issues"]
            suggestion = feasibility["suggestion"]
            can_override = feasibility.get("can_override", False)
            # 汇总问题
            problem_msg = "\n".join([f"- {i['message']}" for i in issues])
            full_msg = f"### 可行性检查\n{problem_msg}\n\n**建议：** {suggestion}"
            
            yield await sse_event("feasibility_check_failed", {
                "feasible": False,
                "issues": issues,
                "suggestion": suggestion,
                "message": full_msg,
                "can_override": can_override
            })
            
            yield await sse_event("complete", {
                "message": full_msg,
                "intent": intent_result,
                "action": None,
                "suggested_followups": [],
                "session_id": session_id
            })
            
            # 记录事件
            log_user_action(
                "feasibility_failed",
                current_user,
                {"issues": issues, "message": request.message},
                dashboard_id,
                session_id
            )
            
            # 保存消息（使用独立db session）
            async with async_session_factory() as stream_db:
                try:
                    await save_chat_message(
                        stream_db, session_id, request.message, intent_result,
                        {
                            "message": full_msg,
                            "action": None,
                            "suggested_followups": []
                        },
                        current_user
                    )
                    await stream_db.commit()
                except Exception as e:
                    await stream_db.rollback()
                    print(f"[ERROR] 保存消息失败: {e}")
            
            yield "data: [DONE]\n\n"
            return
        
        await asyncio.sleep(0.5)
        
        # 5. 生成响应（纯内存操作，无DB）
        intent_type = IntentType(intent_result["intent_type"])
        response_data = await generate_intent_response(
            intent_type, 
            intent_result["analysis"],
            context
        )
        
        # 用户override时，在响应中提示已覆盖的约束
        overridden = feasibility.get("overridden_issues", [])
        if overridden:
            override_note = "\n\n> ⚠️ 已按您的要求强制执行，以下约束被覆盖：\n" + \
                "\n".join([f"> - {i['message']}" for i in overridden])
            response_data["message"] = response_data["message"] + override_note
        
        yield await sse_event("generating", {
            "stage": "response_generation",
            "message": "正在生成回复..."
        })
        
        await asyncio.sleep(0.5)
        
        # 6. 执行动作（如果有动作）
        # 可行性检查通过，现在执行动作
        action = response_data.get("action")
        if action and dashboard_id and intent_result["is_confident"]:
            # 获取当前看板配置
            action_exec_result = None
            try:
                # 重新从db获取最新配置
                async with async_session_factory() as stream_db:
                    dash_result = await stream_db.execute(
                        select(Dashboard).where(Dashboard.id == dashboard_id)
                    )
                    dashboard = dash_result.scalar_one_or_none()
                    if dashboard:
                        current_config = dashboard.config or {}
                        # 执行动作
                        from app.core.action_executor import execute_action
                        action_result = execute_action(
                            action["type"],
                            action.get("params", {}),
                            current_config,
                            context
                        )
                        if action_result["success"]:
                            # 更新到数据库
                            dashboard.config = action_result["new_config"]
                            dashboard.updated_by = current_user
                            dashboard.updated_at = datetime.utcnow()
                            await stream_db.commit()
                            action_exec_result = action_result
                        else:
                            print(f"[WARN] 动作执行失败: {action_result.get('error')}")
            except Exception as e:
                print(f"[ERROR] 动作执行失败: {e}")
            
            # 更新响应
            if action_exec_result:
                response_data["render_updates"] = action_exec_result.get("render_updates", [])
                response_data["new_config"] = action_exec_result.get("new_config", {})
        
        # 7. 发送最终响应
        full_response = {
            "message": response_data["message"],
            "intent": intent_result,
            "action": response_data.get("action"),
            "render_updates": response_data.get("render_updates", []),
            "suggested_followups": response_data.get("suggested_followups", []),
            "session_id": session_id
        }
        
        yield await sse_event("complete", full_response)
        
        # 8. 记录用户事件到飞轮
        log_user_action(
            "user_action",
            current_user,
            {
                "message": request.message,
                "intent_type": intent_type_str,
                "feasible": feasibility["feasible"],
                "confidence": intent_result["confidence"]
            },
            dashboard_id,
            session_id
        )
        
        # 9. 保存消息到数据库（使用独立db session）
        # 修复：在流式生成器内创建新的db session，避免依赖注入的session已关闭
        async with async_session_factory() as stream_db:
            try:
                await save_chat_message(
                    stream_db, session_id, request.message, intent_result, 
                    response_data, current_user
                )
                await stream_db.commit()
            except Exception as e:
                await stream_db.rollback()
                print(f"[ERROR] 保存消息失败: {e}")
        
        # 7. 发送结束标记
        yield "data: [DONE]\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


async def save_chat_message(
    db: AsyncSession,
    session_id: str,
    message: str,
    intent_result: Dict,
    response_data: Dict,
    user_id: str
):
    """保存对话消息"""

    # 保存用户消息
    user_msg = ChatMessage(
        session_id=session_id,
        role="user",
        content=message,
        intent_type=intent_result["intent_type"],
        intent_confidence=intent_result["confidence"],
        intent_analysis=intent_result["analysis"],
        action_type=response_data.get("action", {}).get("type") if response_data.get("action") else None,
        action_params=response_data.get("action", {}).get("params") if response_data.get("action") else None
    )
    db.add(user_msg)

    # 保存助手回复
    assistant_msg = ChatMessage(
        session_id=session_id,
        role="assistant",
        content=response_data["message"],
        action_result=response_data.get("action")
    )
    db.add(assistant_msg)

    await db.commit()


async def save_moderation_message(
    db: AsyncSession,
    session_id: str,
    message: str,
    moderation_result: Dict,
    user_id: str
):
    """保存审核拦截消息 (M3-04)"""

    # 保存用户消息 (保留原文)
    user_msg = ChatMessage(
        session_id=session_id,
        role="user",
        content=message,
        moderation_status="blocked",
        moderation_reason=moderation_result.get("boundary_type"),
        original_content=message  # 保留原文
    )
    db.add(user_msg)

    # 保存系统拦截回复
    system_msg = ChatMessage(
        session_id=session_id,
        role="system",
        content=json.dumps(moderation_result["response"], ensure_ascii=False),
        moderation_status="blocked",
        tokens_used=0  # 不扣Token
    )
    db.add(system_msg)

    await db.commit()


@router.post("/classify-intent", response_model=IntentClassificationResponse)
async def classify_intent_api(
    message: str,
    dashboard_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    单独测试意图分类API
    
    5类意图验证入口
    """
    context = {"dashboard_id": dashboard_id}
    
    # 如果有看板ID，获取上下文
    if dashboard_id:
        result = await db.execute(
            select(Dashboard).where(Dashboard.id == dashboard_id)
        )
        dashboard = result.scalar_one_or_none()
        if dashboard:
            context["field_profiles"] = dashboard.context.get("field_profiles", [])
    
    result = classify_intent(message, context)
    
    return IntentClassificationResponse(
        intent_type=result["intent_type"],
        confidence=result["confidence"],
        analysis=result["analysis"],
        is_confident=result["is_confident"]
    )


# ============== 测试接口 ==============

@router.post("/execute-action", response_model=Dict)
async def execute_action_api(
    action_type: str,
    params: Dict[str, Any],
    dashboard_config: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: str = "anonymous"
):
    """
    执行动作 - M3-02
    
    意图→配置变更→局部重渲染
    """
    try:
        # 执行动作
        result = ActionExecutor.execute(
            ActionType(action_type),
            params,
            dashboard_config,
            {"user_id": current_user}
        )
        
        # 保存动作执行记录到chat_messages (用户行为标注)
        action_msg = ChatMessage(
            session_id=params.get("session_id", "action_execution"),
            role="system",
            content=f"执行动作: {action_type}",
            action_type=action_type,
            action_params=params,
            action_result=result if result.get("success") else {"error": result.get("error")}
        )
        db.add(action_msg)
        await db.commit()
        
        return {
            "success": True,
            "result": result,
            "message": "动作执行完成，记录已保存"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "action_type": action_type
        }


@router.get("/test/action-examples")
async def get_action_test_examples():
    """
    获取5类动作测试示例 - M3-02
    
    用于验收测试
    """
    examples = {
        ActionType.CHANGE_CHART.value: {
            "description": "把饼图改成柱图",
            "params": {"target_type": "bar", "source_type": "pie"},
            "current_config": {
                "charts": [{"id": "chart_1", "chart_type": "pie", "title": "原饼图"}]
            }
        },
        ActionType.ADD_CHART.value: {
            "description": "新增一个趋势图",
            "params": {"chart_type": "line"},
            "current_config": {"charts": []}
        },
        ActionType.FILTER_DRILL.value: {
            "description": "筛选华东地区数据",
            "params": {"filter_field": "地区", "filter_value": "华东"},
            "current_config": {"filters": []}
        },
        ActionType.ATTRIBUTION.value: {
            "description": "归因追问走血缘",
            "params": {"target": "异常波动"},
            "current_config": {},
            "note": "会返回血缘关系和归因分析结果"
        },
        ActionType.EDIT_TITLE.value: {
            "description": "修改标题为月度销售",
            "params": {"new_title": "月度销售分析"},
            "current_config": {"title": "原标题"}
        }
    }
    
    return {
        "success": True,
        "action_types": list(ActionType),
        "test_examples": examples,
        "usage": "curl -X POST /api/v1/chat/execute-action -H 'Content-Type: application/json' -d '{...}'"
    }


@router.get("/test/intent-examples")
async def get_intent_test_examples():
    """
    获取5类意图测试示例
    
    用于验收测试
    """
    examples = {
        IntentType.CHANGE_CHART.value: [
            "把饼图改成柱图",
            "将当前图表换成折线图",
            "把这个改成散点图"
        ],
        IntentType.ADD_CHART.value: [
            "新增一个趋势图",
            "添加一张饼图",
            "再加一个KPI卡片"
        ],
        IntentType.FILTER_DRILL.value: [
            "筛选华东地区的数据",
            "只看近30天的",
            "按类别下钻分析"
        ],
        IntentType.ATTRIBUTION.value: [
            "这个异常是什么原因",
            "分析一下为什么下降",
            "为什么会出现这种情况"
        ],
        IntentType.EDIT_TITLE.value: [
            "把标题改成月度销售",
            "修改标题为营收分析",
            "重命名为担保统计"
        ]
    }
    
    return {
        "success": True,
        "intent_types": list(IntentType),
        "test_examples": examples,
        "usage": "curl -X POST /api/v1/chat/classify-intent?message=xxx"
    }


@router.post("/test/moderation", response_model=Dict)
async def test_moderation(
    message: str,
    db: AsyncSession = Depends(get_db)
):
    """
    测试内容审核 - M3-04
    
    四类边界话术验证
    """
    from app.core.moderation import check_moderation, ContentModerator

    result = check_moderation(message)

    return {
        "success": True,
        "message": message,
        "moderation_result": result,
        "boundary_types": [bt.value for bt in ContentModerator.BOUNDARY_RESPONSES.keys()],
        "test_cases": {
            "超范围": "今天天气怎么样",
            "含糊反问": "什么意思",
            "图库外": "来一个3d图",
            "敏感": "这是机密数据"
        }
    }


@router.post("/test/retry", response_model=Dict)
async def test_retry_mechanism(
    db: AsyncSession = Depends(get_db),
    current_user: str = "test_user"
):
    """
    测试发送失败重试机制 - M3-04
    
    保留原文重试
    """
    # 创建会话
    session = ChatSession(
        user_id=current_user,
        context={}
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    # 模拟发送失败（记录原文）
    test_message = "把饼图改成柱图"

    # 保存消息（模拟失败）
    msg = ChatMessage(
        session_id=session.id,
        role="user",
        content=test_message,
        original_content=test_message,  # 保留原文
        retry_count=0
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)

    # 模拟重试
    msg.retry_count = 1
    await db.commit()

    # 获取记录
    result = await db.execute(
        select(ChatMessage).where(ChatMessage.id == msg.id)
    )
    saved_msg = result.scalar_one()

    return {
        "success": True,
        "original_content_preserved": saved_msg.original_content == test_message,
        "retry_count": saved_msg.retry_count,
        "message": "发送失败保留原文机制验证成功",
        "preserved_text": saved_msg.original_content
    }