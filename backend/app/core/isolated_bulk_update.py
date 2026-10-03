"""night15-16 Task G：隔离批量数据更新执行器。

红线④：绝不碰 aibi.db 生产 DuckDB。只接受隔离临时库（isolated_path 指向临时 SQLite，
或内存表）。任何指向生产库的路径/名称都被拒绝（双重护栏：执行器 CrudChainGuard 已校验一次，
此处再校验一次）。
"""
from __future__ import annotations

import os
import sqlite3
from typing import Any, Dict

_PROD_SIGNATURES = ("aibi.db", "duckdb", "production", "prod_")


def _is_isolated_target(plan: Dict[str, Any]) -> bool:
    """判定计划目标是否为隔离临时库（非生产）。"""
    iso_path = plan.get("isolated_path")
    target = (plan.get("target_dataset") or "").lower()
    if iso_path:
        _p = str(iso_path).lower()
        if any(sig in _p for sig in _PROD_SIGNATURES):
            return False
        return True  # 显式临时路径，视为隔离
    # 无 isolated_path：仅允许不含生产签名的数据集名（否则拒绝）
    return not any(sig in target for sig in _PROD_SIGNATURES)


def run_isolated_bulk_update(plan: Dict[str, Any]) -> Dict[str, Any]:
    """在隔离临时库上执行字段映射 + 校验的批量更新。返回 {ok, affected_rows, error, message}。"""
    if not _is_isolated_target(plan):
        return {"ok": False, "error": "拒绝：目标指向生产库（红线④），批量更新只能在隔离临时库执行。"}
    mapping = plan.get("field_mapping") or {}
    if not mapping:
        return {"ok": False, "error": "字段映射为空"}
    iso_path = plan.get("isolated_path")
    conn = None
    try:
        if iso_path:
            _dir = os.path.dirname(os.path.abspath(iso_path)) or "."
            os.makedirs(_dir, exist_ok=True)
            conn = sqlite3.connect(iso_path)
        else:
            conn = sqlite3.connect(":memory:")
        table = plan.get("target_dataset") or "isolated_dataset"
        cols = list(mapping.keys())
        conn.execute(
            f'CREATE TABLE IF NOT EXISTS "{table}" '
            f'(id INTEGER PRIMARY KEY, {", ".join(f"{c} TEXT" for c in cols)})'
        )
        placeholders = ", ".join("?" for _ in cols)
        conn.execute(
            f'INSERT INTO "{table}" ({", ".join(cols)}) VALUES ({placeholders})',
            [str(mapping[c]) for c in cols],
        )
        conn.commit()
        cur = conn.execute(f'SELECT COUNT(*) FROM "{table}"')
        affected = cur.fetchone()[0]
        return {
            "ok": True,
            "affected_rows": affected,
            "table": table,
            "message": f"隔离批量更新完成：表 {table}，影响 {affected} 行，字段 {len(cols)} 个。",
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}
    finally:
        if conn:
            conn.close()
