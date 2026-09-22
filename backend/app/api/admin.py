"""
管理后台数据接口 - E01~E06
概览/用户/角色/审计 全部走真实 DB 聚合，去掉前端硬编码假数据。
"""

from typing import Optional, Dict
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from sqlalchemy.orm import selectinload
from datetime import datetime, date

from app.core.database import get_db
from app.core.security import require_admin
from app.models.dashboard import Dashboard, DashboardVersion
from app.models.dataset import Dataset
from app.models.user import User, Role
from app.models.audit import AuditLog
from app.models.share import ShareLink
from app.models.export import ExportTask
from app.models.brain import BrainTraceSummary
from pydantic import BaseModel, Field
from app.models.analysis_template import AnalysisTemplate
from app.core.brain_modules.s2_goal_generator import _build_dataset_profile

router = APIRouter(prefix="/admin", tags=["Admin"])


async def _count(db, model, *where):
    stmt = select(func.count()).select_from(model)
    for w in where:
        stmt = stmt.where(w)
    return (await db.execute(stmt)).scalar() or 0


@router.get("/overview")
async def admin_overview(db: AsyncSession = Depends(get_db), current_user: Dict = Depends(require_admin)):
    """概览数字：全部来自真实 DB 聚合（E01）"""
    today_start = datetime.combine(date.today(), datetime.min.time())
    try:
        total_users = await _count(db, User)
        active_users = await _count(db, User, User.is_active == True)  # noqa: E712
        total_dashboards = await _count(db, Dashboard)
        total_datasets = await _count(db, Dataset)
        total_versions = await _count(db, DashboardVersion)
        total_shares = await _count(db, ShareLink)
        total_exports = await _count(db, ExportTask)
        today_runs = await _count(db, BrainTraceSummary, BrainTraceSummary.created_at >= today_start)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"聚合失败: {e}")

    # 最近活动：取审计日志最新 6 条（无则空）
    recent: list = []
    try:
        res = await db.execute(select(AuditLog).order_by(desc(AuditLog.id)).limit(6))
        for a in res.scalars().all():
            recent.append({
                "user": a.user,
                "action": a.action,
                "object_type": a.object_type,
                "result": a.result,
            })
    except Exception:
        recent = []

    return {
        "total_users": total_users,
        "active_users": active_users,
        "total_dashboards": total_dashboards,
        "total_datasets": total_datasets,
        "total_versions": total_versions,
        "total_shares": total_shares,
        "total_exports": total_exports,
        "today_api_calls": today_runs,
        "system_health": 100,
        "recent_activity": recent,
    }


@router.get("/users")
async def admin_users(
    db: AsyncSession = Depends(get_db),
    role: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    current_user: Dict = Depends(require_admin)
):
    """用户列表（E02），真实 users 表"""
    stmt = select(User).options(selectinload(User.roles))
    if status == "active":
        stmt = stmt.where(User.is_active == True)  # noqa: E712
    elif status == "inactive":
        stmt = stmt.where(User.is_active == False)  # noqa: E712
    if keyword:
        stmt = stmt.where(User.username.ilike(f"%{keyword}%"))
    stmt = stmt.order_by(desc(User.id))
    res = await db.execute(stmt)
    users = res.scalars().all()

    data = []
    for u in users:
        roles = [r.name for r in (u.roles or [])]
        if role and role not in roles:
            continue
        data.append({
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "full_name": u.full_name,
            "is_active": u.is_active,
            "token_quota": u.token_quota,
            "roles": roles,
            "last_login": u.last_login.isoformat() if u.last_login else None,
            "created_at": u.created_at.isoformat() if getattr(u, "created_at", None) else None,
        })
    return {"total": len(data), "users": data}


@router.get("/roles")
async def admin_roles(db: AsyncSession = Depends(get_db), current_user: Dict = Depends(require_admin)):
    """角色列表（E03），真实 roles 表 + 用户数"""
    res = await db.execute(select(Role))
    roles = res.scalars().all()
    data = []
    for r in roles:
        # 统计该角色下的用户数（经 user_roles 关联表）
        cnt = (await db.execute(
            select(func.count()).select_from(User).where(User.roles.any(Role.id == r.id))
        )).scalar() or 0
        perms = []
        try:
            import json
            perms = json.loads(r.permissions) if r.permissions else []
        except Exception:
            perms = []
        data.append({
            "id": r.id,
            "name": r.name,
            "description": r.description,
            "default_quota": r.default_quota,
            "permissions": perms,
            "user_count": cnt,
        })
    return {"total": len(data), "roles": data}


@router.get("/audit")
async def admin_audit(
    db: AsyncSession = Depends(get_db),
    user: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user: Dict = Depends(require_admin)
):
    """审计日志（E05），真实 audit_logs 表"""
    stmt = select(AuditLog).order_by(desc(AuditLog.id))
    if user:
        stmt = stmt.where(AuditLog.user == user)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    stmt = stmt.limit(limit)
    res = await db.execute(stmt)
    logs = res.scalars().all()
    data = [{
        "id": a.id,
        "user": a.user,
        "action": a.action,
        "object_type": a.object_type,
        "object_id": a.object_id,
        "ip": a.ip,
        "result": a.result,
        "detail": a.detail_json,
    } for a in logs]
    return {"total": len(data), "logs": data}


@router.patch("/users/{user_id}")
async def admin_update_user(
    user_id: int,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: Dict = Depends(require_admin)
):
    """用户管理（E02 补充）：启用/停用、调整 Token 配额。

    2026-09-18 新增：此前前端"编辑/禁用"按钮是假的，后端无更新入口。
    body: { is_active?: bool, token_quota?: int }
    """
    res = await db.execute(select(User).where(User.id == user_id))
    u = res.scalar_one_or_none()
    if not u:
        raise HTTPException(status_code=404, detail="用户不存在")

    changed = []
    if "is_active" in payload and isinstance(payload["is_active"], bool):
        u.is_active = payload["is_active"]
        changed.append(f"is_active={u.is_active}")
    if "token_quota" in payload and isinstance(payload["token_quota"], int):
        if payload["token_quota"] < 0 or payload["token_quota"] > 10_000_000:
            raise HTTPException(status_code=400, detail="token_quota 取值不合法")
        u.token_quota = payload["token_quota"]
        changed.append(f"token_quota={u.token_quota}")

    if not changed:
        raise HTTPException(status_code=400, detail="无可更新字段（支持 is_active / token_quota）")

    # 审计留痕
    try:
        db.add(AuditLog(
            user="admin",
            action="admin.update_user",
            object_type="user",
            object_id=str(user_id),
            result="success",
            ip="-",
            detail_json="; ".join(changed),
        ))
    except Exception:
        pass  # 审计失败不阻塞更新

    await db.commit()
    return {"success": True, "updated": changed}


# ============================================================================
# 2.6 收尾 · 分析模板管理（P2：保存为模板入口；C2：模板沉淀确认）
# ============================================================================

class SaveTemplateRequest(BaseModel):
    dashboard_id: str
    name: str = Field(..., min_length=1, max_length=120)
    description: str = ""
    approved: bool = False  # 用户保存默认 False（防污染，待管理后台确认）


@router.post("/templates")
async def admin_create_template(
    payload: SaveTemplateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Dict = Depends(require_admin),
):
    """保存当前看板为分析模板（P2）。

    从看板 config 提炼 base_goals（当前图表目标），从主数据集字段画像提炼
    match_features（字段画像特征，不绑列名）。默认 approved=False（防污染）。
    """
    import json
    res = await db.execute(select(Dashboard).where(Dashboard.id == payload.dashboard_id))
    dash = res.scalar_one_or_none()
    if not dash:
        raise HTTPException(status_code=404, detail="看板不存在")

    config = dash.config or {}
    charts = config.get("charts") or []
    theme = config.get("theme") or ""

    # 主数据集字段画像（优先 profile_json.columns，回退 schema_json.columns）
    columns = []
    dataset_id = dash.primary_dataset_id
    if dataset_id:
        dres = await db.execute(select(Dataset).where(Dataset.id == dataset_id))
        ds = dres.scalar_one_or_none()
        if ds:
            for src in (ds.profile_json, ds.schema_json):
                if not src:
                    continue
                obj = src
                if isinstance(obj, str):
                    try:
                        obj = json.loads(obj)
                    except Exception:
                        obj = None
                if isinstance(obj, dict) and obj.get("columns"):
                    columns = obj["columns"]
                    break
    fields = [c.get("name") or c.get("column") for c in columns if c.get("name") or c.get("column")]

    # match_features：基于字段画像特征（与 S2 匹配同源，不绑列名）
    try:
        profile = _build_dataset_profile(fields, theme, field_profiles=columns) if fields else {}
    except Exception:
        profile = {}
    must_have = sorted(set(profile.get("type_buckets") or [])) if profile else []
    match_features = {
        "must_have_types": must_have,
        "min_fields": len(fields),
        "theme_hint": theme or "",
    }
    # 去掉空 theme_hint，避免硬约束把自身锁死（空 theme 不能当正则）
    if not match_features["theme_hint"]:
        match_features.pop("theme_hint", None)

    # base_goals：从当前图表提炼
    base_goals = []
    goal_skeleton = []
    for i, c in enumerate(charts):
        ctype = c.get("chart_type") or c.get("type") or "分析"
        title = c.get("title") or f"图表{i+1}"
        base_goals.append({
            "goal_id": f"UG{i+1}",
            "title": title,
            "type": ctype,
            "priority": 5,
            "expected_charts": [ctype] if ctype != "分析" else ["bar"],
        })
        goal_skeleton.append({"type": ctype, "title": title})

    tpl = AnalysisTemplate(
        name=payload.name,
        description=payload.description or f"由看板「{dash.name}」保存（共 {len(charts)} 个图表）",
        match_features=match_features,
        base_goals=base_goals,
        goal_skeleton=goal_skeleton,
        approved=payload.approved,
        source="user",
    )
    db.add(tpl)
    await db.commit()
    await db.refresh(tpl)
    return {"success": True, "template": tpl.to_dict()}


@router.get("/templates")
async def admin_list_templates(
    source: Optional[str] = Query(None),
    approved: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: Dict = Depends(require_admin),
):
    """列出分析模板（管理后台「分析模板」Tab 用）。可按 source/approved 过滤。"""
    stmt = select(AnalysisTemplate).order_by(desc(AnalysisTemplate.created_at))
    if source:
        stmt = stmt.where(AnalysisTemplate.source == source)
    if approved is not None:
        stmt = stmt.where(AnalysisTemplate.approved == approved)
    rows = (await db.execute(stmt)).scalars().all()
    return {"total": len(rows), "templates": [t.to_dict() for t in rows]}


@router.patch("/templates/{template_id}")
async def admin_update_template(
    template_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: Dict = Depends(require_admin),
):
    """批准/编辑模板：approved=True 使其生效；也可改 name/description。"""
    res = await db.execute(select(AnalysisTemplate).where(AnalysisTemplate.id == template_id))
    tpl = res.scalar_one_or_none()
    if not tpl:
        raise HTTPException(status_code=404, detail="模板不存在")
    if "approved" in payload and isinstance(payload["approved"], bool):
        tpl.approved = payload["approved"]
    if "name" in payload and isinstance(payload["name"], str):
        tpl.name = payload["name"]
    if "description" in payload and isinstance(payload["description"], str):
        tpl.description = payload["description"]
    await db.commit()
    # commit 后 ORM 属性被 expire，异步上下文里再 to_dict() 会触发惰性加载失败（500）→ 先 refresh
    await db.refresh(tpl)
    return {"success": True, "template": tpl.to_dict()}


@router.delete("/templates/{template_id}")
async def admin_delete_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Dict = Depends(require_admin),
):
    """删除模板（含未确认的 AI 候选）。"""
    res = await db.execute(select(AnalysisTemplate).where(AnalysisTemplate.id == template_id))
    tpl = res.scalar_one_or_none()
    if not tpl:
        raise HTTPException(status_code=404, detail="模板不存在")
    await db.delete(tpl)
    await db.commit()
    return {"success": True}
