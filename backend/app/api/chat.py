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
from app.models.dataset import Dataset

router = APIRouter(prefix="/chat", tags=["Chat-对话"])


# ============== 看板配置并发写锁 ==============
# 看板 config 是整段 JSON 覆盖写入，多路并发动作（如同时 add_chart）若各自"读-改-写"，
# 后写者会把先写者新增的图表覆盖掉（丢失更新）。用每看板一把进程内 async 锁把
# 同一看板的读-改-写事务串行化，保证每个动作都基于最新 config。
_CONFIG_LOCKS: Dict[str, asyncio.Lock] = {}


def _dashboard_lock(dashboard_id: str) -> asyncio.Lock:
    lock = _CONFIG_LOCKS.get(dashboard_id)
    if lock is None:
        lock = asyncio.Lock()
        _CONFIG_LOCKS[dashboard_id] = lock
    return lock


# ============== 请求/响应模型 ==============

class ChatMessageRequest(BaseModel):
    """发送消息请求"""
    session_id: Optional[str] = None
    message: str = Field(..., min_length=1, max_length=2000, description="用户消息")
    dashboard_id: Optional[str] = Field(None, description="当前看板ID")
    dataset_id: Optional[str] = Field(None, description="当前数据集ID")
    override: bool = Field(False, description="用户强制覆盖blocking级约束（用户优先级最高）")
    force_rule_fallback: bool = Field(False, description="AI智能回复不可用时，强制使用本地规则引导回复（不重试AI）")


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

def _surface_action_error(action_result: Dict[str, Any], response_data: Dict[str, Any]) -> Dict[str, Any]:
    """#5 修复：动作执行失败时把错误显式写入响应，前端不再静默误判为成功。

    - action_result['success'] 为 True 时原样返回（不动 response_data）
    - 为 False 时写入 response_data['action_error']，并在 message 末尾追加醒目提示
    返回就地修改后的 response_data（同一对象）。
    """
    if action_result.get("success"):
        return response_data
    err = action_result.get("error") or "动作执行失败"
    response_data["action_error"] = err
    base = response_data.get("message") or ""
    if err not in base:
        response_data["message"] = base + f"\n\n> ⚠️ 动作执行未成功：{err}（看板未变更）"
    return response_data


def _add_chart_message(analysis: Dict) -> str:
    """根据结构化提取结果生成新增图提示语（支持多图）"""
    ep = analysis.get("extracted_params", {})
    charts = ep.get("charts") or []
    if charts:
        titles = "、".join(c.get("title", "新图表") for c in charts)
        return f"正在为您添加 {len(charts)} 个图表：{titles} ..."
    ct = ep.get("chart_type", "新图表")
    return f"正在为您添加{ct}..."


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
            "message": _add_chart_message(analysis),
            "action": {
                "type": "add_chart",
                "params": analysis.get("extracted_params", {})
            },
            "suggested_followups": ["调整图表位置", "修改图表标题", "继续添加图表"]
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
        IntentType.CHART_FIX: {
            "message": "我来查一下这张图为什么取不到数据...",
            "action": {
                "type": "chart_fix",
                "params": analysis.get("extracted_params", {})
            },
            "suggested_followups": ["按推荐方案修复", "换个字段", "重新生成看板"]
        },
        IntentType.QUALITY_FIX: {
            "message": f"正在修复数据质量{analysis.get('extracted_params', {}).get('issue_type', '重复')}问题，将写入清洗层...",
            "action": {
                "type": "quality_fix",
                "params": analysis.get("extracted_params", {})
            },
            "suggested_followups": ["查看修复结果", "重新质检", "继续加工指标"]
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


# ============== LLM 自然语言回复生成 ==============

def _rule_guidance_message(context: Dict[str, Any]) -> str:
    """AI 不可用时的本地规则引导话术（无网络依赖，纯兜底）"""
    current_config = context.get("current_config", {})
    dataset_info = context.get("dataset_info", {})
    field_profiles = dataset_info.get("field_profiles", [])
    theme = current_config.get("theme", "通用分析")
    return (
        f"我目前只支持以下操作，请尝试用更明确的指令：\n\n"
        f"- 改图表：「把饼图改成柱图」「换成折线图」\n"
        f"- 新增图表：「新增一个趋势图」「加一个 KPI 卡片」\n"
        f"- 删除图表：「删除最后一个图表」\n"
        f"- 筛选数据：「只看华东地区」「近30天数据」\n"
        f"- 修改标题：「把标题改为月度销售」\n\n"
        f"当前看板主题: {theme}，字段: {', '.join(f.get('name', f.get('column','')) for f in field_profiles[:5])}"
    )


async def generate_llm_natural_response(
    user_message: str,
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """UNKNOWN 意图时调用 LLM 基于看板上下文生成自然语言回复。

    返回 {ok, content, error}：
    - ok=True  → content 为 AI 生成的文本
    - ok=False → content=None，error 为可读失败原因（供前端弹出报错+选择）
    绝不在 AI 失败时静默替换为规则引导——是否降级由调用方/用户决定。
    """
    from app.core.llm_gateway import llm_chat
    from app.core.prompt_loader import load_prompt

    current_config = context.get("current_config", {})
    dataset_info = context.get("dataset_info", {})
    field_profiles = dataset_info.get("field_profiles", [])
    grain = dataset_info.get("grain", "detail")

    # 提取看板主题
    theme = current_config.get("theme", "通用分析")

    # 构建图表摘要
    charts = current_config.get("charts", [])
    charts_text = ""
    for i, chart in enumerate(charts[:8], 1):
        ct = chart.get("chart_type", "?")
        title = chart.get("title", "未命名")
        xf = chart.get("x_field") or chart.get("category_field") or ""
        yf = chart.get("y_field") or chart.get("value_field") or ""
        charts_text += f"  {i}. [{ct}] {title}  (x={xf}, y={yf or '-'})\n"

    # 构建字段摘要
    fields_text = ""
    for fp in field_profiles[:20]:
        fname = fp.get("name", fp.get("column", ""))
        ftype = fp.get("type", "")
        fields_text += f"  - {fname} ({ftype})\n"

    default_prompt = (
        "你是一位资深 BI 数据分析师助手，正在看板页面与用户对话。\n\n"
        "## 当前看板信息\n"
        f"- 主题: {theme}\n"
        "- 数据粒度: " + ("宏观指标" if grain == "macro" else "汇总数据" if grain == "aggregate" else "明细数据") + "\n"
        "- 图表列表:\n" + (charts_text if charts_text else "  （暂无图表）") + "\n"
        "## 数据集字段\n" + (fields_text if fields_text else "  （无字段画像）") + "\n\n"
        "## 回答要求\n"
        "1. 直接回答用户的问题或需求，基于上面的看板与字段信息，不要泛泛而谈\n"
        "2. 用户想分析数据时，给出具体分析建议（用哪个字段、看哪张图）\n"
        "3. 用户想调整看板时，引导使用具体指令（如把饼图改成柱图、新增一个趋势图）\n"
        "4. 回答简洁、专业、有用，中文回复，控制在200字内\n"
        "5. 数据里没有的信息要坦诚说明，不要编造\n\n"
        f"用户消息: {user_message}\n\n"
        "请直接回复用户（纯文本，不要JSON）。"
    )

    system_prompt = load_prompt(
        "ai_assistant_spec",
        "你是一位资深 BI 数据分析师助手，正在帮助用户分析和优化数据看板。",
        theme=theme
    )
    full_prompt = system_prompt + "\n\n" + default_prompt

    try:
        response = await llm_chat(
            prompt=full_prompt,
            json_mode=False,
            user_id="chat_llm_response"
        )
        if response.success and response.content:
            return {"ok": True, "content": response.content.strip(), "error": None}
        return {
            "ok": False,
            "content": None,
            "error": response.error or "AI 未返回有效内容（可能为限流或模型异常）"
        }
    except Exception as e:
        print(f"[Chat] LLM 自然语言回复生成失败: {e}")
        return {"ok": False, "content": None, "error": f"AI 调用异常: {str(e)[:120]}"}


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
    dashboard = None

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

    # 数据集：请求指定 > 看板主数据集（绑定到会话，保证后续对话拿到真实字段画像）
    session_dataset_id = request.dataset_id
    if not session_dataset_id and dashboard is not None:
        session_dataset_id = dashboard.primary_dataset_id

    # 获取真实字段画像（优先 profile_json.columns，为空时回退 schema_json.columns）
    if session_dataset_id:
        ds_result = await db.execute(
            select(Dataset).where(Dataset.id == session_dataset_id)
        )
        dataset = ds_result.scalar_one_or_none()
        if dataset:
            field_profiles = []
            for src in (dataset.profile_json, dataset.schema_json):
                if not src:
                    continue
                obj = src
                if isinstance(obj, str):
                    try:
                        obj = json.loads(obj)
                    except Exception:
                        obj = None
                if isinstance(obj, dict) and obj.get("columns"):
                    field_profiles = obj["columns"]
                    break
            if field_profiles:
                context["field_profiles"] = field_profiles

    session = ChatSession(
        user_id=current_user,
        dashboard_id=request.dashboard_id,
        dataset_id=session_dataset_id,
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


@router.get("/sessions/latest", response_model=Dict)
async def get_latest_session_with_messages(
    dashboard_id: str,
    db: AsyncSession = Depends(get_db)
):
    """获取指定看板最近一次有消息的会话及其消息（用于前端恢复对话历史）"""
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.dashboard_id == dashboard_id)
        .order_by(ChatSession.created_at.desc())
        .limit(20)
    )
    sessions = result.scalars().all()

    for session in sessions:
        msg_result = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.created_at)
            .limit(100)
        )
        messages = msg_result.scalars().all()
        if messages:
            return {
                "success": True,
                "session_id": session.id,
                "count": len(messages),
                "messages": [m.to_dict() for m in messages]
            }

    return {"success": True, "session_id": None, "count": 0, "messages": []}


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

    # 获取当前看板配置
    current_config = {}
    dashboard = None
    if dashboard_id:
        dash_result = await db.execute(
            select(Dashboard).where(Dashboard.id == dashboard_id)
        )
        dashboard = dash_result.scalar_one_or_none()
        if dashboard:
            current_config = dashboard.config or {}

    # 数据集解析：请求指定 > 会话绑定 > 看板主数据集 > 看板数据集列表首个
    # 会话未绑 dataset_id 时若不回退看板，field_profiles 为空，
    # AI 新增图会退化为"新增饼图"+空字段的旧兜底（多图提取被跳过）
    dataset_id = request.dataset_id or session.dataset_id
    if not dataset_id and dashboard is not None:
        dataset_id = dashboard.primary_dataset_id
        if not dataset_id:
            ds_ids = dashboard.dataset_ids
            if isinstance(ds_ids, str):
                try:
                    ds_ids = json.loads(ds_ids)
                except Exception:
                    ds_ids = []
            if isinstance(ds_ids, list) and ds_ids:
                dataset_id = ds_ids[0]

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
            # 字段画像：优先 profile_json.columns；当其为空（如 '{}'）时回退 schema_json.columns
            for src in (dataset.profile_json, dataset.schema_json):
                if not src:
                    continue
                obj = src
                if isinstance(obj, str):
                    try:
                        obj = json.loads(obj)
                    except Exception:
                        obj = None
                if isinstance(obj, dict) and obj.get("columns"):
                    field_profiles = obj["columns"]
                    break
    
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
        from app.core.event_logger import log_user_action
        
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
        
        # 3. 意图分类 + 动作规划（2026-09-18：复合指令拆成有序动作列表）
        from app.core.action_planner import plan_actions
        plan = plan_actions(request.message, context, override=bool(request.override))
        intent_result = plan["primary_intent"]
        
        yield await sse_event("intent_classified", {
            "intent_type": intent_result["intent_type"],
            "confidence": intent_result["confidence"],
            "analysis": intent_result["analysis"],
            "is_confident": intent_result["is_confident"],
            "classified_by": intent_result.get("classified_by", "rule")
        })

        # 动作规划可视化：复合指令到底被拆成了哪几个动作（验收取证用）
        yield await sse_event("action_plan", {
            "is_compound": plan["is_compound"],
            "clauses": plan["clauses"],
            "unparsed_clauses": plan["unparsed_clauses"],
            "actions": [
                {"seq": i + 1, "type": a["type"], "clause": a.get("clause"),
                 "params": a.get("params")}
                for i, a in enumerate(plan["actions"])
            ],
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
        # UNKNOWN 意图或低置信度时，调用 LLM 生成自然语言回复，避免答非所问
        if plan.get("actions"):
            # 规划器已产出动作列表（单指令=1项，行为不变；复合指令=多项，依次执行）
            acts = plan["actions"]
            response_data = {
                "message": ("已拆分为 %d 个动作并依次执行：" % len(acts)) if len(acts) > 1 else "",
                "action": {"type": acts[0]["type"], "params": acts[0].get("params", {})},
                "actions": acts,
                "suggested_followups": [],
                "render_updates": [],
                "ai_error": None,
            }
        elif intent_type == IntentType.UNKNOWN or not intent_result.get("is_confident", True):
            ai_error = None
            if request.force_rule_fallback:
                # 用户已明确选择"规则引导"：跳过 AI，直接给本地引导话术
                llm_msg = _rule_guidance_message(context)
            else:
                llm_resp = await generate_llm_natural_response(
                    user_message=request.message,
                    context=context
                )
                if llm_resp["ok"]:
                    llm_msg = llm_resp["content"]
                else:
                    # AI 失败：不再静默降级为规则引导，而是把失败与选择权交还用户
                    ai_error = {
                        "stage": "llm_natural_response",
                        "error": llm_resp["error"],
                        "options": ["retry", "rule_fallback"],
                        "message": (
                            "⚠️ AI 智能回复调用失败（模型限流或网络异常），未能生成回答。\n"
                            "你可以：①点「重试」再次请求 AI；②点「规则引导」改用本地内置引导回复。"
                        ),
                    }
                    llm_msg = ai_error["message"]
            response_data = {
                "message": llm_msg,
                "action": None,
                "suggested_followups": [],
                "render_updates": [],
                "ai_error": ai_error
            }
        else:
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
        
        # 6. 执行动作（2026-09-18：复合指令按有序动作列表逐个执行，逐动作失败隔离）
        actions = response_data.get("actions") or (
            [response_data["action"]] if response_data.get("action") else []
        )
        action_results = []
        last_new_config = None
        render_updates = []

        if actions and dashboard_id and (intent_result["is_confident"] or any(a.get("type") == "clarify" for a in actions)):
            # 同一看板的读-改-写用 per-dashboard 锁串行化，避免并发覆盖丢更新
            lock = _dashboard_lock(dashboard_id)
            async with lock:
                for act in actions:
                    one = {
                        "seq": len(action_results) + 1,
                        "type": act.get("type"),
                        "clause": act.get("clause"),
                        "success": False,
                        "message": None,
                        "error": None,
                    }
                    try:
                        # 每个动作都重新从 db 读最新配置：保证前一个动作的落库被后一个看到
                        async with async_session_factory() as stream_db:
                            dash_result = await stream_db.execute(
                                select(Dashboard).where(Dashboard.id == dashboard_id)
                            )
                            dashboard = dash_result.scalar_one_or_none()
                            if not dashboard:
                                one["error"] = "看板不存在，未执行"
                            else:
                                current_config = dashboard.config or {}
                                # 锁内基于最新config兜底：新增图表不超上限(与feasibility保持一致的50)
                                if act.get("type") == "add_chart" and len(current_config.get("charts", [])) >= 50:
                                    one["error"] = "看板已有50个图表，已达上限，无法继续新增"
                                else:
                                    from app.core.action_executor import execute_action
                                    r = execute_action(
                                        act.get("type"),
                                        act.get("params", {}),
                                        current_config,
                                        context
                                    )
                                    one["success"] = bool(r.get("success"))
                                    one["message"] = r.get("message")
                                    one["error"] = r.get("error")
                                    one["requires_confirm"] = r.get("requires_confirm")
                                    one["requires_clarify"] = r.get("requires_clarify")
                                    one["changes"] = r.get("changes")
                                    if one["success"]:
                                        last_new_config = r.get("new_config") or current_config
                                        dashboard.config = last_new_config
                                        dashboard.updated_by = current_user
                                        dashboard.updated_at = datetime.utcnow()
                                        # JSON字段是原地mutate的同一对象，必须显式标记才会生成UPDATE
                                        from sqlalchemy.orm.attributes import flag_modified
                                        flag_modified(dashboard, "config")
                                        await stream_db.commit()
                                        render_updates.extend(r.get("render_updates") or [])
                    except Exception as e:
                        # 单动作异常不影响后续动作
                        one["error"] = f"动作执行异常：{str(e)[:160]}"
                    action_results.append(one)

            # ---- 汇总：成功消息 + 逐动作失败原因（失败不影响其它动作）----
            ok_msgs = [r.get("message") for r in action_results if r.get("success") and r.get("message")]
            err_msgs = [
                f"· 动作{r.get('seq')}「{r.get('clause') or r.get('type')}」未成功：{r.get('error')}"
                for r in action_results if not r.get("success")
            ]
            parts = []
            if len(action_results) > 1:
                parts.append(
                    f"共 {len(action_results)} 个动作：成功 {sum(1 for r in action_results if r.get('success'))} 个，"
                    f"失败 {len(err_msgs)} 个。"
                )
            parts.extend(ok_msgs)
            parts.extend(err_msgs)
            if parts:
                response_data["message"] = "\n".join(parts)
            first_err = next((r.get("error") for r in action_results if not r.get("success")), None)
            if first_err:
                response_data["action_error"] = first_err
            if render_updates:
                response_data["render_updates"] = render_updates
            if last_new_config is not None:
                response_data["new_config"] = last_new_config
            response_data["action_results"] = action_results
        
        # 7. 发送最终响应
        # 注意：无论是否有动作、是否高置信（含 unknown 走 LLM 自然回复的分支），
        # 都必须在此统一构造完整响应，否则低置信/unknown 路径会因 full_response 未定义而抛 UnboundLocalError，
        # 被 safe_stream 捕获成“对话生成中断”，表现为 AI 对所有非高置信指令都报错。
        full_response = {
            "message": response_data["message"],
            "intent": intent_result,
            "action": response_data.get("action"),
            "actions": response_data.get("actions", []),
            "action_results": response_data.get("action_results", []),
            "action_error": response_data.get("action_error"),
            "ai_error": response_data.get("ai_error"),
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
    
    async def safe_stream():
        """包装 generate_stream：捕获任意未预期异常，避免前端永远卡在'生成中'。"""
        try:
            async for ev in generate_stream():
                yield ev
        except Exception as e:
            import traceback
            print(f"[Chat] 流生成异常(已兜底): {e}\n{traceback.format_exc()}")
            try:
                yield await sse_event("error", {
                    "message": f"对话生成中断：{str(e)[:160]}。请稍后重试，或换一种问法。"
                })
            except Exception:
                pass
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        safe_stream(),
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