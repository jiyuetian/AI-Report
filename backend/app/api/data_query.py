"""DuckDB 受控查询 API（#652）。

为 AI 提供一条受控、只读的数据获取通道，只能查询调用者自己拥有的数据集 DuckDB 表。
安全要点：
- 标识符一律用 quote_ident 引用；所有字面量走参数化 `?` 占位符，绝不拼接用户输入。
- 单条只读语句：归一化 SQL 含写关键字（INSERT/UPDATE/DELETE/DROP/...）一律 400 拒绝。
- 数据集归属校验：仅 dataset.created_by == 当前用户 或 超管可见。
表名以 Dataset.duckdb_table 为准（仓库实际命名为 ds_<id>），缺失时回退 ds_<id>。
"""
import re
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.duckdb_manager import get_duckdb, quote_ident
from app.core.ai_action_log import log_ai_action
from app.models.dataset import Dataset

router = APIRouter(prefix="/data", tags=["DataQuery"])

# 单条只读语句白名单之外的高危写关键字（词边界匹配，避免误伤 created_at 等列名）
_WRITE_KW_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|ATTACH|DETACH|COPY|"
    r"TRUNCATE|RENAME|GRANT|REVOKE|BEGIN|COMMIT|ROLLBACK)\b",
    re.IGNORECASE,
)
_VALID_AGGS = {"sum", "avg", "count", "min", "max"}
_VALID_OPS = {"eq", "neq", "gt", "ge", "lt", "le", "in", "like"}
_VALID_DIRS = {"asc", "desc"}
_MAX_LIMIT = 1000


class MeasureSpec(BaseModel):
    field: str
    agg: str  # sum/avg/count/min/max


class FilterSpec(BaseModel):
    field: str
    op: str  # eq/neq/gt/ge/lt/le/in/like
    value: Any = None


class DataQueryRequest(BaseModel):
    dataset_id: str
    query_type: str  # aggregate / top_n / filter / distinct / raw
    dimensions: List[str] = []
    measures: List[MeasureSpec] = []
    filters: List[FilterSpec] = []
    order_by: Optional[Dict[str, Any]] = None
    limit: int = 100
    raw_sql: Optional[str] = None


class DatasetTableInfo(BaseModel):
    dataset_id: str
    name: Optional[str] = None
    table_name: Optional[str] = None


# --------------------------------------------------------------------------- #
# SQL 构建（全部参数化）
# --------------------------------------------------------------------------- #
def _contains_write(sql: str) -> bool:
    return bool(_WRITE_KW_RE.search(sql or ""))


def _is_single_statement(sql: str) -> bool:
    s = (sql or "").strip().rstrip(";")
    return ";" not in s


def _duckdb_execute(mgr, sql: str, params: List[Any]):
    """兼容真实 DuckDBManager（无 execute，走 .conn）与测试用 fake（有 execute）。"""
    if hasattr(mgr, "execute"):
        return mgr.execute(sql, params)
    return mgr.conn.execute(sql, params)


def _build_where(filters: List[FilterSpec]):
    parts: List[str] = []
    params: List[Any] = []
    for f in filters:
        field = f.field
        op = (f.op or "").lower()
        value = f.value
        qf = quote_ident(field)
        if op == "eq":
            parts.append(f"{qf} = ?"); params.append(value)
        elif op == "neq":
            parts.append(f"{qf} <> ?"); params.append(value)
        elif op == "gt":
            parts.append(f"{qf} > ?"); params.append(value)
        elif op == "ge":
            parts.append(f"{qf} >= ?"); params.append(value)
        elif op == "lt":
            parts.append(f"{qf} < ?"); params.append(value)
        elif op == "le":
            parts.append(f"{qf} <= ?"); params.append(value)
        elif op == "like":
            parts.append(f"{qf} LIKE ?"); params.append(value)
        elif op == "in":
            vals = value if isinstance(value, list) else [value]
            placeholders = ",".join(["?"] * max(1, len(vals)))
            parts.append(f"{qf} IN ({placeholders})")
            params.extend(vals)
        else:
            raise ValueError(f"不支持的过滤操作符: {op}")
    return parts, params


def _build_order(order_by: Optional[Dict[str, Any]], qtype: str,
                 measures: List[MeasureSpec]) -> str:
    if order_by and order_by.get("field"):
        f = order_by["field"]
        direction = (order_by.get("direction") or "asc").lower()
        if direction not in _VALID_DIRS:
            direction = "asc"
        return f"{quote_ident(f)} {direction.upper()}"
    if qtype == "top_n" and measures:
        alias = f"{measures[0].field}_{measures[0].agg.lower()}"
        return f"{quote_ident(alias)} DESC"
    return ""


def build_data_sql(table_name: str, req: DataQueryRequest):
    """根据请求构建参数化只读 SQL，返回 (sql, params)。"""
    qt = quote_ident(table_name)
    params: List[Any] = []
    select_parts: List[str] = []
    group_cols: List[str] = []
    distinct = ""

    if req.query_type in ("aggregate", "top_n"):
        for d in req.dimensions:
            select_parts.append(quote_ident(d))
            group_cols.append(quote_ident(d))
        for m in req.measures:
            agg = m.agg.lower()
            select_parts.append(
                f"{agg}({quote_ident(m.field)}) AS {quote_ident(m.field + '_' + agg)}"
            )
    else:  # filter / distinct
        cols = list(req.dimensions) + [m.field for m in req.measures]
        if not cols:
            cols = ["*"]
        for c in cols:
            select_parts.append(quote_ident(c))
        if req.query_type == "distinct":
            distinct = "DISTINCT "

    if not select_parts:
        select_parts = ["*"]

    sql = f"SELECT {distinct}{', '.join(select_parts)} FROM {qt}"

    where, wparams = _build_where(req.filters)
    if where:
        sql += " WHERE " + " AND ".join(where)
        params.extend(wparams)
    if group_cols:
        sql += " GROUP BY " + ", ".join(group_cols)

    order_sql = _build_order(req.order_by, req.query_type, req.measures)
    if order_sql:
        sql += " ORDER BY " + order_sql

    limit = max(1, min(int(req.limit), _MAX_LIMIT))
    sql += " LIMIT ?"
    params.append(limit)
    return sql, params


# --------------------------------------------------------------------------- #
# 归属校验
# --------------------------------------------------------------------------- #
async def _get_owned_dataset(db: AsyncSession, dataset_id: str,
                             current_user: Dict) -> Optional[Dataset]:
    res = await db.execute(select(Dataset).where(Dataset.id == dataset_id))
    ds = res.scalar_one_or_none()
    if not ds:
        return None
    if current_user.get("is_superuser"):
        return ds
    if ds.created_by == current_user.get("user_id"):
        return ds
    return None


def _resolve_table_name(ds: Dataset, dataset_id: str) -> str:
    if getattr(ds, "duckdb_table", None):
        return ds.duckdb_table
    return f"ds_{dataset_id.replace('-', '_')}"


# --------------------------------------------------------------------------- #
# 端点
# --------------------------------------------------------------------------- #
@router.get("/tables")
async def list_my_tables(
    db: AsyncSession = Depends(get_db),
    current_user: Dict = Depends(get_current_user),
):
    """列出调用者自己拥有的数据集对应的 DuckDB 表。"""
    if current_user.get("is_superuser"):
        res = await db.execute(select(Dataset))
    else:
        res = await db.execute(
            select(Dataset).where(Dataset.created_by == current_user["user_id"])
        )
    datasets = res.scalars().all()
    tables = [
        {
            "dataset_id": d.id,
            "name": d.name,
            "table_name": _resolve_table_name(d, d.id),
        }
        for d in datasets
    ]
    return {"tables": tables}


@router.post("/query")
async def query_data(
    req: DataQueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Dict = Depends(get_current_user),
):
    """受控只读查询（参数化，拒绝写操作）。"""
    # raw 模式：仅超管 + 必须提供 raw_sql，仍做单条只读校验
    if req.query_type == "raw":
        if not current_user.get("is_superuser"):
            raise HTTPException(status_code=400, detail="raw SQL 仅限超管使用")
        if not req.raw_sql:
            raise HTTPException(status_code=400, detail="raw 模式必须提供 raw_sql")
        sql = req.raw_sql
        params: List[Any] = []
        if not _is_single_statement(sql) or _contains_write(sql):
            raise HTTPException(status_code=400, detail="拒绝：仅允许单条只读 SQL")
    else:
        # 校验枚举
        for m in req.measures:
            if m.agg.lower() not in _VALID_AGGS:
                raise HTTPException(status_code=422, detail=f"非法聚合函数: {m.agg}")
        for f in req.filters:
            if f.op.lower() not in _VALID_OPS:
                raise HTTPException(status_code=422, detail=f"非法过滤操作符: {f.op}")
        # 归属校验
        ds = await _get_owned_dataset(db, req.dataset_id, current_user)
        if not ds:
            raise HTTPException(status_code=404, detail="数据集不存在或无权限")
        table_name = _resolve_table_name(ds, req.dataset_id)
        sql, params = build_data_sql(table_name, req)

    start = time.monotonic()
    try:
        mgr = get_duckdb()
        rel = _duckdb_execute(mgr, sql, params)
        columns = [d[0] for d in (rel.description or [])]
        rows = rel.fetchall() or []
        row_count = len(rows)
    except Exception as e:
        latency = int((time.monotonic() - start) * 1000)
        await log_ai_action(
            dashboard_id=None,
            user_id=current_user["user_id"],
            intent="data_query",
            action_type="read",
            params_summary={"dataset_id": req.dataset_id,
                            "query_type": req.query_type, "limit": req.limit},
            result_status="failed",
            error_msg=str(e)[:500],
            llm_layer="rule",
            latency_ms=latency,
        )
        raise HTTPException(status_code=500, detail=f"查询执行失败: {str(e)[:200]}")

    latency = int((time.monotonic() - start) * 1000)
    await log_ai_action(
        dashboard_id=None,
        user_id=current_user["user_id"],
        intent="data_query",
        action_type="read",
        params_summary={"dataset_id": req.dataset_id,
                        "query_type": req.query_type, "limit": req.limit},
        result_status="success",
        llm_layer="rule",
        latency_ms=latency,
    )
    return {
        "columns": columns,
        "rows": rows,
        "row_count": row_count,
        "sql": sql,
    }
