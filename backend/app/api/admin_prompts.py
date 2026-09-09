"""管理中心 · Prompt 中心 API
仅管理员/超级管理员可访问。提供九大提示词板块的：
- GET  /admin/prompts           列表（含生效内容、版本、启停、是否自定义）
- PUT  /admin/prompts/:key      保存编辑（content+enabled+remark，version+1）
- POST /admin/prompts/:key/reset 恢复内置默认
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_roles
from app.core import prompt_manager
from app.models.prompt import Prompt

router = APIRouter(prefix="/admin/prompts", tags=["Admin"])


async def init_prompt_records(session: AsyncSession) -> None:
    """启动时：为未入库的板块补默认行，并把 DB 中的覆盖内容载入内存缓存。"""
    rows = (await session.execute(select(Prompt))).scalars().all()
    row_map = {r.group_key: r for r in rows}
    # 1. 补默认行
    changed = False
    for meta in prompt_manager.all_groups():
        key = meta["key"]
        if key not in row_map:
            session.add(Prompt(
                group_key=key,
                title=meta["title"],
                description=meta.get("description", ""),
                category=meta.get("category", ""),
                content=None,
                enabled=True,
                version=1,
                is_builtin=True,
                remark="系统内置默认",
                updated_by="system",
            ))
            changed = True
    if changed:
        await session.flush()
        rows = (await session.execute(select(Prompt))).scalars().all()
        row_map = {r.group_key: r for r in rows}
    # 2. 载入缓存
    for key, row in row_map.items():
        if row.content:
            prompt_manager.set_override(
                key, row.content, bool(row.enabled), row.version,
                bool(row.is_builtin), row.remark or "", row.updated_by or "",
            )
        else:
            prompt_manager.clear_override(key)


def _serialize(key: str, row: Optional[Prompt]) -> dict:
    meta = prompt_manager.get_group_meta(key)
    seed = prompt_manager.seed_content(key)
    o = prompt_manager.get_override(key)
    if o and o.get("content") and o.get("enabled"):
        content, enabled, version, is_builtin = (
            o["content"], o["enabled"], o["version"], o["is_builtin"],
        )
    else:
        content, enabled, version = seed, (row.enabled if row else True), (row.version if row else 1)
        is_builtin = True
    return {
        "key": key,
        "title": meta["title"],
        "description": meta.get("description", ""),
        "category": meta.get("category", ""),
        "content": content,
        "enabled": bool(enabled),
        "version": version,
        "is_builtin": bool(is_builtin),
        "remark": row.remark if row else "",
        "updated_by": row.updated_by if row else "",
        "updated_at": str(row.updated_at) if row else "",
    }


class SavePromptRequest(BaseModel):
    content: str = Field(..., description="提示词正文")
    enabled: bool = True
    remark: str = ""
    updated_by: str = ""


def _get_row(rows_map: dict, key: str):
    return rows_map.get(key)


@router.get("")
async def list_prompts(
    current_user: dict = Depends(require_roles(["admin"])),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(select(Prompt))).scalars().all()
    row_map = {r.group_key: r for r in rows}
    items = [_serialize(m["key"], row_map.get(m["key"])) for m in prompt_manager.all_groups()]
    return {"success": True, "total": len(items), "groups": items}


@router.put("/{key}")
async def save_prompt(
    key: str,
    body: SavePromptRequest,
    current_user: dict = Depends(require_roles(["admin"])),
    db: AsyncSession = Depends(get_db),
):
    if not prompt_manager.is_valid_key(key):
        raise HTTPException(status_code=404, detail=f"未知的提示词板块: {key}")

    row = (await db.execute(select(Prompt).where(Prompt.group_key == key))).scalars().first()
    if row is None:
        meta = prompt_manager.get_group_meta(key)
        row = Prompt(group_key=key, title=meta["title"], description=meta.get("description", ""),
                     category=meta.get("category", ""))
        db.add(row)

    actor = body.updated_by or current_user.get("username") or "admin"
    seed = prompt_manager.seed_content(key)
    is_builtin = (body.content == seed)
    row.content = body.content
    row.enabled = body.enabled
    row.version = (row.version or 1) + 1
    row.is_builtin = is_builtin
    row.remark = body.remark
    row.updated_by = actor
    await db.flush()

    prompt_manager.set_override(key, body.content, body.enabled, row.version,
                                is_builtin, body.remark, actor)
    await db.commit()
    # onupdate 的 updated_at 为服务端生成值，commit 后显式 refresh 再序列化，避免在同步 _serialize 内触发惰性加载
    await db.refresh(row)
    return {"success": True, "prompt": _serialize(key, row)}


@router.post("/{key}/reset")
async def reset_prompt(
    key: str,
    current_user: dict = Depends(require_roles(["admin"])),
    db: AsyncSession = Depends(get_db),
):
    if not prompt_manager.is_valid_key(key):
        raise HTTPException(status_code=404, detail=f"未知的提示词板块: {key}")

    row = (await db.execute(select(Prompt).where(Prompt.group_key == key))).scalars().first()
    if row is None:
        meta = prompt_manager.get_group_meta(key)
        row = Prompt(group_key=key, title=meta["title"], description=meta.get("description", ""),
                     category=meta.get("category", ""))
        db.add(row)

    actor = current_user.get("username") or "admin"
    row.content = None
    row.enabled = True
    row.version = (row.version or 1) + 1
    row.is_builtin = True
    row.remark = "恢复内置默认"
    row.updated_by = actor
    await db.flush()

    prompt_manager.clear_override(key)
    await db.commit()
    await db.refresh(row)
    return {"success": True, "prompt": _serialize(key, row)}