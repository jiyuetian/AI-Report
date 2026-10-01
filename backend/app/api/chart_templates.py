"""图表模板库 API - night14 Task B。

提供图表模板的浏览（按业务域/标签/关键词）+ 一键套用能力：
- GET  /list          分页 + 多维过滤浏览
- GET  /{id}          详情
- POST /              自建模板（source=user）
- PUT  /{id}          更新（仅作者或超管）
- DELETE /{id}        删除（仅作者或超管）
- POST /{id}/apply    一键套用到目标看板：复用 executor._execute_add_chart 既有渲染链，
                      按目标数据集真实字段画像映射模板候选字段，命不中则跳过（不臆造垃圾图）。

权限：列表/详情/套用 需登录；增删改 仅作者或超管。套用要求目标看板归属当前用户或超管。
"""
from __future__ import annotations

from typing import List, Optional
import json

from fastapi import APIRouter, Depends, Query, HTTPException, Body
from pydantic import BaseModel, Field
from sqlalchemy import select, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.chart_template import ChartTemplate
from app.models.dashboard import Dashboard
from app.models.dataset import Dataset

router = APIRouter(prefix="/chart-templates", tags=["ChartTemplate"])


# ---------------------------------------------------------------------------
# 请求/响应模型
# ---------------------------------------------------------------------------
class ChartSpec(BaseModel):
    chart_type: str = "bar"
    title: str = ""
    metric_field: Optional[str] = None
    dimension_field: Optional[str] = None
    aggregation: Optional[str] = None


class ChartTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    category: str = Field(..., min_length=1, max_length=40)
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    config_json: dict = Field(..., description="{'charts':[ChartSpec,...]}")


class ChartTemplateUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    config_json: Optional[dict] = None


class ApplyRequest(BaseModel):
    dashboard_id: str = Field(..., description="目标看板ID")


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------
def _item(t: ChartTemplate) -> dict:
    return t.to_dict()


def _extract_field_profiles(dataset: Optional[Dataset]) -> List[dict]:
    """从 dataset.profile_json/schema_json 提取 columns 作为字段画像（与 chat.py 同逻辑）。"""
    if dataset is None:
        return []
    profiles: List[dict] = []
    for src in (getattr(dataset, "profile_json", None), getattr(dataset, "schema_json", None)):
        if not src:
            continue
        try:
            obj = src if isinstance(src, dict) else json.loads(src)
        except Exception:
            continue
        cols = obj.get("columns") if isinstance(obj, dict) else None
        if cols:
            profiles = cols
            break
    return profiles


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------
@router.get("/list", response_model=dict)
async def list_templates(
    category: Optional[str] = Query(None, description="业务域精确过滤"),
    tag: Optional[str] = Query(None, description="标签过滤（命中任一即返回）"),
    keyword: Optional[str] = Query(None, description="模糊匹配 name/description/tags"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """分页 + 多维过滤浏览图表模板。"""
    filters = []
    if category:
        filters.append(ChartTemplate.category == category)
    if keyword:
        kw = f"%{keyword}%"
        filters.append(
            or_(
                ChartTemplate.name.like(kw),
                ChartTemplate.description.like(kw),
                ChartTemplate.category.like(kw),
            )
        )
    where = and_(*filters) if filters else True

    total_res = await db.execute(select(func.count()).select_from(ChartTemplate).where(where))
    total = int(total_res.scalar() or 0)

    offset = (page - 1) * page_size
    rows_res = await db.execute(
        select(ChartTemplate).where(where).order_by(ChartTemplate.created_at.desc()).offset(offset).limit(page_size)
    )
    rows = rows_res.scalars().all()

    items = [_item(r) for r in rows]
    # 标签过滤（JSON 内做，DB 无关）：tag 命中 tags 任一即保留
    if tag:
        items = [it for it in items if tag in (it.get("tags") or [])]

    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/{tpl_id}", response_model=dict)
async def get_template(
    tpl_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    t = await db.get(ChartTemplate, tpl_id)
    if not t:
        raise HTTPException(status_code=404, detail="模板不存在")
    return _item(t)


@router.post("/", response_model=dict)
async def create_template(
    body: ChartTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    uid = current_user.get("user_id")
    is_super = bool(current_user.get("is_superuser"))
    if not is_super and not uid:
        raise HTTPException(status_code=403, detail="无权限")
    t = ChartTemplate(
        name=body.name,
        category=body.category,
        description=body.description,
        tags=body.tags,
        config_json=body.config_json,
        source="user",
        created_by=uid,
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return _item(t)


@router.put("/{tpl_id}", response_model=dict)
async def update_template(
    tpl_id: str,
    body: ChartTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    t = await db.get(ChartTemplate, tpl_id)
    if not t:
        raise HTTPException(status_code=404, detail="模板不存在")
    uid = current_user.get("user_id")
    is_super = bool(current_user.get("is_superuser"))
    if not (is_super or t.created_by == uid):
        raise HTTPException(status_code=403, detail="仅作者或超管可修改")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(t, k, v)
    await db.commit()
    await db.refresh(t)
    return _item(t)


@router.delete("/{tpl_id}", response_model=dict)
async def delete_template(
    tpl_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    t = await db.get(ChartTemplate, tpl_id)
    if not t:
        raise HTTPException(status_code=404, detail="模板不存在")
    uid = current_user.get("user_id")
    is_super = bool(current_user.get("is_superuser"))
    if not (is_super or t.created_by == uid):
        raise HTTPException(status_code=403, detail="仅作者或超管可删除")
    await db.delete(t)
    await db.commit()
    return {"deleted": True, "id": tpl_id}


@router.post("/{tpl_id}/apply", response_model=dict)
async def apply_template(
    tpl_id: str,
    body: ApplyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """一键套用模板到目标看板：复用 executor._execute_add_chart 既有渲染链。"""
    t = await db.get(ChartTemplate, tpl_id)
    if not t:
        raise HTTPException(status_code=404, detail="模板不存在")

    dash = await db.get(Dashboard, body.dashboard_id)
    if not dash:
        raise HTTPException(status_code=404, detail="看板不存在")
    uid = current_user.get("user_id")
    is_super = bool(current_user.get("is_superuser"))
    if not (is_super or dash.created_by == uid):
        raise HTTPException(status_code=403, detail="仅看板作者或超管可套用")

    # 目标数据集：优先主数据集，否则取第一个挂载数据集
    ds_id = dash.primary_dataset_id or (dash.dataset_ids or [None])[0] if dash.dataset_ids else None
    dataset = await db.get(Dataset, ds_id) if ds_id else None
    field_profiles = _extract_field_profiles(dataset)

    # 复用既有渲染链（无 LLM、无臆造：executor 严格匹配真实字段，命不中跳过）
    from app.core.action_executor import ActionExecutor
    specs = (t.config_json or {}).get("charts") or []
    cfg = dict(dash.config or {})
    ctx = {"dataset_id": ds_id or "", "dataset_info": {"field_profiles": field_profiles}}
    result = ActionExecutor._execute_add_chart(
        params={"charts": specs},
        current_config=cfg,
        context=ctx,
    )
    if not result.get("success"):
        return {
            "success": False,
            "applied": 0,
            "message": result.get("error", "套用失败"),
            "render_updates": [],
        }

    dash.config = cfg
    from datetime import datetime
    dash.updated_at = datetime.utcnow()
    t.usage_count = (t.usage_count or 0) + 1
    await db.commit()

    return {
        "success": True,
        "applied": len(result.get("render_updates", [])),
        "message": result.get("message", "套用完成"),
        "render_updates": result.get("render_updates", []),
    }
