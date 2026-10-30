"""L1-L4 掌权 CRUD API + R8 护栏（#651）。

把既有 ActionExecutor 的 CRUD/权限/指标动作暴露为 AI（以当前登录用户身份）可调的真实 REST 端点，
并对每个变更端点施加 R8 四道护栏：
- R8-4 改前回退点：变更前对受影响看板打 VersionManager 快照。
- R8-1 规则引擎 API：一律经 ActionExecutor.execute 路由（fail-fast，失败 422）。
- R8-3 十项留痕：成功/失败都写一条 AiActionLog（llm_layer="rule"）。
- R8-2 血缘白盒：图表变更成功后刷新血缘（见下方 hook 注释，不臆造不存在的函数）。
"""
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, require_admin
from app.core.action_executor import ActionExecutor, ActionType
from app.core.version_manager import VersionManager
from app.core.ai_action_log import log_ai_action
from app.models.dashboard import Dashboard

router = APIRouter(prefix="/ai/crud", tags=["AICrud"])


def _model_dict(m) -> Dict[str, Any]:
    """兼容 pydantic v1(.dict)/v2(model_dump)。"""
    if hasattr(m, "model_dump"):
        return m.model_dump()
    return m.dict()


def _sid() -> str:
    return uuid.uuid4().hex


def _safe_summary(params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return {
            k: (v if not isinstance(v, (dict, list)) else f"<{type(v).__name__}>")
            for k, v in (params or {}).items()
        }
    except Exception:
        return {}


# --------------------------------------------------------------------------- #
# R8 护栏核心：派发到 ActionExecutor + 快照 + 留痕
# --------------------------------------------------------------------------- #
async def _dispatch(
    action_type: ActionType,
    params: Dict[str, Any],
    *,
    dashboard_id: Optional[str],
    current_user: Dict,
    db: AsyncSession,
    session_id: Optional[str] = None,
):
    session_id = session_id or _sid()

    # R8-4 改前回退点：变更前对看板打快照（无 dashboard_id 或看板不存在则优雅跳过）
    if dashboard_id and action_type != ActionType.CALCULATE_METRIC:
        try:
            await VersionManager.create_version(
                db,
                dashboard_id,
                name="R8-4 改前回退点",
                description=f"{action_type.value} 前自动快照",
                created_by=current_user.get("user_id", "anonymous"),
                is_auto_save=True,
            )
        except Exception as e:
            print(f"[AICRUD] R8-4 快照跳过(忽略): {e}")

    # 载入看板当前配置作为 current_config 输入
    current_config: Dict[str, Any] = {}
    primary_dataset_id = None
    if dashboard_id:
        res = await db.execute(select(Dashboard).where(Dashboard.id == dashboard_id))
        dash = res.scalar_one_or_none()
        if dash:
            current_config = dash.config or {}
            primary_dataset_id = getattr(dash, "primary_dataset_id", None)

    # R8-1 规则引擎 API：统一经 ActionExecutor 路由
    context = {
        "db": db,
        "user": current_user,
        "dashboard_id": dashboard_id,
        "session_id": session_id,
        "version_manager": VersionManager,
        "dataset_id": primary_dataset_id,
    }
    start = time.monotonic()
    result = ActionExecutor.execute(action_type, params, current_config, context)
    latency = int((time.monotonic() - start) * 1000)

    # R8-3 十项留痕：成功与失败都写一条
    ok = bool(result.get("success"))
    await log_ai_action(
        session_id=session_id,
        dashboard_id=dashboard_id,
        user_id=current_user.get("user_id"),
        intent="ai_crud",
        action_type=action_type.value,
        params_summary={"dashboard_id": dashboard_id, **_safe_summary(params)},
        result_status="success" if ok else "failed",
        error_msg=None if ok else result.get("error"),
        llm_layer="rule",
        latency_ms=latency,
    )

    if not ok:
        # fail-fast：返回 422 并透传错误
        raise HTTPException(status_code=422, detail=result.get("error") or "执行失败")

    # R8-2 血缘白盒：图表变更成功后刷新血缘。
    # 注意：app.core.lineage_service 并未提供 update_lineage(dashboard_id, ...) 函数；
    # 真实可用的是 LineageService.build_lineage_for_dataset(...) / save_lineage_to_db(...)
    # （见 app/core/lineage_service.py）。此处不臆造不存在的函数，仅留钩子。
    # TODO(R8-2): 在此调用 lineage_service 刷新血缘，例如
    #   await LineageService.build_lineage_for_dataset(db, primary_dataset_id, ...)
    _ = (ActionType.ADD_CHART, ActionType.CHANGE_CHART, ActionType.DELETE_CHART)

    return result


# --------------------------------------------------------------------------- #
# 请求模型
# --------------------------------------------------------------------------- #
class ConfigCreateRequest(BaseModel):
    key: str
    value: Any = None
    layer: Optional[str] = None
    dashboard_id: Optional[str] = None


class ConfigUpdateRequest(BaseModel):
    key: str
    value: Any = None
    dashboard_id: Optional[str] = None


class AddChartRequest(BaseModel):
    dashboard_id: Optional[str] = None
    chart_type: Optional[str] = None
    title: Optional[str] = None
    x_field: Optional[str] = None
    y_field: Optional[str] = None
    category_field: Optional[str] = None
    value_field: Optional[str] = None
    aggregation: Optional[str] = None
    extra: Dict[str, Any] = {}


class ChangeChartRequest(BaseModel):
    dashboard_id: Optional[str] = None
    chart_id: Optional[str] = None
    title_keyword: Optional[str] = None
    target_type: Optional[str] = None
    target_field: Optional[str] = None
    target_axis: Optional[str] = None
    time_grain: Optional[str] = None
    extra: Dict[str, Any] = {}


class MetricCalcRequest(BaseModel):
    metric: str
    operation: str = "query"
    data: Dict[str, Any] = {}


class PermissionRequest(BaseModel):
    target_user_id: str
    role: str
    operation: str = "grant"
    dashboard_id: Optional[str] = None


# --------------------------------------------------------------------------- #
# 端点
# --------------------------------------------------------------------------- #
@router.post("/config")
async def create_config(
    req: ConfigCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Dict = Depends(get_current_user),
):
    params: Dict[str, Any] = {"key": req.key, "value": req.value}
    if req.layer is not None:
        params["layer"] = req.layer
    return await _dispatch(
        ActionType.CREATE_CONFIG, params,
        dashboard_id=req.dashboard_id, current_user=current_user, db=db,
    )


@router.put("/config")
async def update_config(
    req: ConfigUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Dict = Depends(get_current_user),
):
    params = {"key": req.key, "value": req.value}
    return await _dispatch(
        ActionType.UPDATE_CONFIG, params,
        dashboard_id=req.dashboard_id, current_user=current_user, db=db,
    )


@router.delete("/config/{key}")
async def delete_config(
    key: str,
    dashboard_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: Dict = Depends(get_current_user),
):
    params = {"key": key}
    return await _dispatch(
        ActionType.DELETE_CONFIG, params,
        dashboard_id=dashboard_id, current_user=current_user, db=db,
    )


@router.post("/chart")
async def add_chart(
    req: AddChartRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Dict = Depends(get_current_user),
):
    spec = {
        k: v for k, v in _model_dict(req).items()
        if k not in ("dashboard_id", "extra") and v is not None
    }
    spec.update(req.extra or {})
    params = {"dashboard_id": req.dashboard_id, "charts": [spec]}
    return await _dispatch(
        ActionType.ADD_CHART, params,
        dashboard_id=req.dashboard_id, current_user=current_user, db=db,
    )


@router.put("/chart/{chart_id}")
async def change_chart(
    chart_id: str,
    req: ChangeChartRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Dict = Depends(get_current_user),
):
    params = {
        k: v for k, v in _model_dict(req).items()
        if k not in ("dashboard_id", "extra") and v is not None
    }
    params["chart_id"] = chart_id
    params.update(req.extra or {})
    return await _dispatch(
        ActionType.CHANGE_CHART, params,
        dashboard_id=req.dashboard_id, current_user=current_user, db=db,
    )


@router.delete("/chart/{chart_id}")
async def delete_chart(
    chart_id: str,
    dashboard_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: Dict = Depends(get_current_user),
):
    params = {"chart_id": chart_id}
    return await _dispatch(
        ActionType.DELETE_CHART, params,
        dashboard_id=dashboard_id, current_user=current_user, db=db,
    )


@router.post("/metric/calc")
async def calc_metric(
    req: MetricCalcRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Dict = Depends(get_current_user),
):
    """指标计算（纯计算、只读，红线④不碰生产 DB）。无需 R8-4 快照。"""
    params = {"metric": req.metric, "operation": req.operation, "data": req.data}
    session_id = _sid()
    start = time.monotonic()
    result = ActionExecutor.execute(
        ActionType.CALCULATE_METRIC, params, {}, {"user": current_user, "db": db}
    )
    latency = int((time.monotonic() - start) * 1000)
    ok = bool(result.get("success"))
    await log_ai_action(
        session_id=session_id,
        user_id=current_user.get("user_id"),
        intent="ai_crud",
        action_type=ActionType.CALCULATE_METRIC.value,
        params_summary=_safe_summary(params),
        result_status="success" if ok else "failed",
        error_msg=None if ok else result.get("error"),
        llm_layer="rule",
        latency_ms=latency,
    )
    if not ok:
        raise HTTPException(status_code=422, detail=result.get("error") or "执行失败")
    return result


@router.post("/permission")
async def manage_permission(
    req: PermissionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Dict = Depends(require_admin),
):
    """权限变更（硬护栏：仅超管）。"""
    params = {
        "target_user_id": req.target_user_id,
        "role": req.role,
        "operation": req.operation,
    }
    return await _dispatch(
        ActionType.MANAGE_PERMISSIONS, params,
        dashboard_id=req.dashboard_id, current_user=current_user, db=db,
    )
