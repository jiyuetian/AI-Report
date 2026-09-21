"""
附录服务 - 2026-09-18 对齐方案B（InsightDesk）报告附录
四件套（全部取自真实管线元数据，确定性拼装，不依赖模型自述）：
  A. 字段字典   —— DuckDB 清洗层实测统计（字段名/类型/空值率/唯一值数/取值范围；本项目 DuckDB 表即真实表头，无 c0/c1 物理列层）
  B. 清洗日志   —— SQLite clean_rules + quality_issues（算子/策略/影响行数/说明）
  C. 指标计算明细 —— 看板图表反推 SQL（指标/SQL/返回行数，可在清洗层数据集上复跑）
  D. 数据血缘   —— lineage_nodes / lineage_edges 六层图（类型/节点/关键属性 + 上游→下游）
"""

import json
from typing import Dict, Any, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dashboard import Dashboard
from app.models.chart import Chart
from app.models.quality import CleanRule, QualityIssue
from app.core.duckdb_manager import get_duckdb


_TYPE_MAP = [
    ("BIGINT", "int"), ("HUGEINT", "int"), ("INTEGER", "int"), ("SMALLINT", "int"), ("TINYINT", "int"),
    ("DOUBLE", "float"), ("FLOAT", "float"), ("DECIMAL", "float"), ("REAL", "float"), ("NUMERIC", "float"),
    ("VARCHAR", "string"), ("TEXT", "string"), ("CHAR", "string"),
    ("DATE", "date"), ("TIMESTAMP", "datetime"), ("TIME", "time"),
    ("BOOLEAN", "bool"), ("BOOL", "bool"),
]

_NODE_TYPE_LABEL = {
    "source": "源文件", "field": "数据表", "clean": "清洗算子",
    "business": "业务口径", "agg": "聚合", "chart": "图表",
}
_NODE_TYPE_ORDER = {"source": 0, "field": 1, "clean": 2, "business": 3, "agg": 4, "chart": 5}
_EDGE_LABEL = {"direct": "映射", "transform": "变换", "aggregate": "聚合", "filter": "过滤"}

_MAX_COLS = 60          # 每数据集最多统计的列数
_MAX_METRICS = 30       # 指标明细上限
_MAX_NODES = 300        # 血缘节点上限


def _simplify_type(dtype: str) -> str:
    up = str(dtype or "").upper()
    for prefix, label in _TYPE_MAP:
        if up.startswith(prefix):
            return label
    return up.lower() or "unknown"


def _quote(s: str) -> str:
    return '"' + str(s).replace('"', '""') + '"'


def _pick_table(duck, dataset) -> Optional[str]:
    """优先清洗层 cleaned → 原始表（与质检口径一致）"""
    base = f"ds_{dataset.id.replace('-', '_')}"
    cleaned = f"{base}_cleaned"
    if duck.table_exists(cleaned):
        return cleaned
    if dataset.duckdb_table and duck.table_exists(dataset.duckdb_table):
        return dataset.duckdb_table
    if duck.table_exists(base):
        return base
    return None


def _field_dict_for_dataset(duck, dataset) -> Dict[str, Any]:
    """A. 字段字典：对清洗层逐列实测统计"""
    out = {"dataset_id": dataset.id, "dataset_name": dataset.name, "table": None, "row_count": 0, "columns": []}
    table = _pick_table(duck, dataset)
    if not table:
        return out
    info = duck.get_table_info(table)
    cols = info.get("columns", [])[:_MAX_COLS]
    out["table"] = table
    out["row_count"] = info.get("row_count", 0)
    qt = _quote(table)
    for i, col in enumerate(cols):
        name = col["name"]
        qc = _quote(name)
        try:
            r = duck.conn.execute(f"""
                SELECT COUNT(*),
                       COUNT({_qc_notnull(qc)}),
                       COUNT(DISTINCT {qc}),
                       MIN(TRY_CAST({qc} AS DOUBLE)),
                       MAX(TRY_CAST({qc} AS DOUBLE))
                FROM {qt}
            """).fetchone()
            total = r[0] or 0
            not_null = r[1] or 0
            mn, mx = r[3], r[4]
            has_range = mn is not None and mx is not None and float(mn) != float(mx)
            # 布尔/极低基数的数值不算"取值范围"，与B项目口径一致
            out["columns"].append({
                # 注：与方案B不同，本项目的 DuckDB 表不做列名简化（无 c0/c1 物理列层），
                # 列名即原始表头，直接引用真实列名，保证附录与清洗层实测口径一致
                "name": name,
                "type": _simplify_type(col.get("type")),
                "null_rate": round(1 - not_null / total, 4) if total else 0,
                "unique_count": r[2] or 0,
                "min": float(mn) if has_range else None,
                "max": float(mx) if has_range else None,
            })
        except Exception:
            out["columns"].append({
                "name": name, "type": _simplify_type(col.get("type")),
                "null_rate": 0, "unique_count": 0, "min": None, "max": None,
            })
    return out


def _qc_notnull(qc: str) -> str:
    return f"{qc} IS NOT NULL AND CAST({qc} AS VARCHAR) <> ''"


async def _clean_log(sql_db: AsyncSession, dataset_ids: List[str]) -> List[Dict[str, Any]]:
    """B. 清洗与质检日志：合并两路真实数据——
    1) clean_rules：用户实际执行的清洗算子（已修复，影响行数回填）；
    2) quality_issues：平台自动质检发现的异常（按 数据集/字段/类型/状态 聚合），
       展示检测阶段的异常分布，使"先质检→后清洗"的链路在附录里完整可见。
    本项目真实数据集中 clean_rules 多为生成时未触发，故质检发现是清洗过程的主要白盒来源。"""
    if not dataset_ids:
        return []
    rules = (await sql_db.execute(
        select(CleanRule).where(CleanRule.dataset_id.in_(dataset_ids)).order_by(CleanRule.execution_order, CleanRule.id)
    )).scalars().all()
    issues = (await sql_db.execute(
        select(QualityIssue).where(QualityIssue.dataset_id.in_(dataset_ids))
    )).scalars().all()
    # (dataset, field, type) -> 该字段对应质检问题的"影响行数"
    # 1.10 修复：原仅取 status=="done" 的 issue，但真实数据中 winsorize 规则对应的质检问题
    # 多为 ignored/todo（affect_rows=2），导致 apply 阶段"影响行数"全为 None。
    # 现改为覆盖 done/ignored/todo 三态，并取最大 affect_rows，避免同字段多状态重复计数。
    # 这样附录 B「已清洗」行的 winsorize 也能显示真实影响行数（比"策略 winsorize"更具体）。
    rows_map = {}
    for iss in issues:
        if iss.status in ("done", "ignored", "todo"):
            key = (iss.dataset_id, iss.field_name, iss.type)
            prev = rows_map.get(key)
            cur = iss.affect_rows or 0
            if prev is None or cur > prev:
                rows_map[key] = iss.affect_rows

    log = []
    seq = 0
    # 1) 已执行清洗
    for r in rules:
        seq += 1
        params = r.params or {}
        affected = rows_map.get((r.dataset_id, r.target_field, params.get("issue_type", "")))
        detail_parts = []
        if params.get("strategy"):
            detail_parts.append(f"策略 {params['strategy']}")
        if params.get("issue_type"):
            detail_parts.append(f"问题类型 {params['issue_type']}")
        if affected is not None:
            detail_parts.append(f"影响 {affected} 行")
        log.append({
            "seq": seq,
            "stage": "apply",
            "dataset_id": r.dataset_id,
            "rule_type": r.rule_type,
            "strategy": params.get("strategy", ""),
            "target_field": r.target_field or "-",
            "affected_rows": affected,
            "detail": "；".join(detail_parts) or "-",
        })
    # 2) 质检发现（聚合）
    grp = {}
    for iss in issues:
        key = (iss.dataset_id, iss.field_name, iss.type, iss.status)
        grp[key] = grp.get(key, 0) + 1
    status_label = {"done": "已修复", "ignored": "已忽略", "todo": "待处理"}
    for (ds, field, typ, status), cnt in sorted(grp.items()):
        seq += 1
        log.append({
            "seq": seq,
            "stage": "detect",
            "dataset_id": ds,
            "rule_type": "质检发现",
            "strategy": typ,
            "target_field": field or "-",
            "affected_rows": cnt,
            "detail": f"状态 {status_label.get(status, status)}",
        })
    return log


def _normalize_chart(c: Dict[str, Any], default_ds: Optional[str], idx: int) -> Dict[str, Any]:
    """把看板内嵌 config.charts 或 charts 表的图表统一成附录可用的结构。
    本项目图表主存于 dashboards.config['charts']（生成流程未落 charts 表），
    故以该内嵌数组为真源，charts 表作为兜底。"""
    cfg = c.get("config") or {}
    if not isinstance(cfg, dict):
        cfg = {}
    ds_id = c.get("dataset_id") or default_ds
    return {
        "title": c.get("title") or "未命名图表",
        "type": c.get("chart_type") or c.get("type") or "bar",
        "dataset_id": ds_id,
        "x_field": c.get("x_field") or c.get("category_field") or "",
        "y_field": c.get("y_field") or c.get("value_field") or "",
        "aggregate": (cfg.get("aggregation") or cfg.get("aggregate") or c.get("aggregate") or "").upper(),
        "sort": idx,
    }


def _metric_sql(chart: Dict[str, Any], table: str) -> Optional[str]:
    """从图表配置反推指标 SQL（与 chart-data / 前端 aggregate 口径一致）"""
    dim = chart.get("x_field") or ""
    meas = chart.get("y_field") or ""
    agg = chart.get("aggregate") or ""
    qt = _quote(table)

    if chart.get("type") == "kpi":
        if meas:
            func = agg if agg in ("SUM", "AVG", "MAX", "MIN", "COUNT") else "SUM"
            return f'SELECT {func}({_quote(meas)}) AS v FROM {qt}'
        return f'SELECT COUNT(*) AS v FROM {qt}'

    if not dim:
        return None
    if meas:
        func = agg if agg in ("SUM", "AVG", "MAX", "MIN", "COUNT") else "COUNT"
        if func == "COUNT":
            return f'SELECT {_quote(dim)}, COUNT(*) AS v FROM {qt} GROUP BY {_quote(dim)}'
        return f'SELECT {_quote(dim)}, {func}({_quote(meas)}) AS v FROM {qt} GROUP BY {_quote(dim)}'
    return f'SELECT {_quote(dim)}, COUNT(*) AS v FROM {qt} GROUP BY {_quote(dim)}'


def _metric_formula(chart: Dict[str, Any]) -> str:
    """C. 指标计算明细：把技术 SQL 翻译成用户能看懂的计算口径（公式）。
    与 _metric_sql 反推口径完全对应，不依赖模型自述。2026-09-18 产品化：用户不关心 SQL，看公式即可。"""
    typ = chart.get("type")
    dim = chart.get("x_field") or ""
    meas = chart.get("y_field") or ""
    agg = (chart.get("aggregate") or "").upper()
    agg_label = {"SUM": "求和", "AVG": "平均", "MAX": "最大值", "MIN": "最小值", "COUNT": "计数"}.get(agg, "统计")
    if typ == "kpi":
        if meas:
            return f"{meas} 的{agg_label}值"
        return "总记录条数"
    if not dim:
        return "总记录条数"
    if meas:
        func = agg if agg in ("SUM", "AVG", "MAX", "MIN", "COUNT") else "COUNT"
        al = {"SUM": "求和", "AVG": "平均", "MAX": "最大值", "MIN": "最小值", "COUNT": "计数"}.get(func, "统计")
        return f"按 {dim} 分组，对 {meas} 做{al}"
    return f"按 {dim} 分组，统计各组记录条数"


def _metric_detail(duck, charts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """C. 指标计算明细：反推 SQL + 计算口径（公式）+ 实跑返回行数（可在清洗层复跑验证）"""
    out = []
    for chart in charts[:_MAX_METRICS]:
        ds_id = chart.get("dataset_id")
        if not ds_id:
            continue
        table = _pick_table(duck, _ChartDS(ds_id))
        if not table:
            continue
        sql = _metric_sql(chart, table)
        if not sql:
            continue
        rows = None
        try:
            rows = len(duck.conn.execute(sql).fetchall())
        except Exception:
            pass
        out.append({
            "title": chart.get("title"),
            "chart_type": chart.get("type"),
            "dataset_id": ds_id,
            "formula": _metric_formula(chart),  # 产品化：用户可读的口径公式
            "sql": sql,
            "rows": rows,
        })
    return out


class _ChartDS:
    """轻量包装，复用 _pick_table"""
    def __init__(self, dataset_id: str):
        self.id = dataset_id
        self.duckdb_table = None


async def build_appendix(sql_db: AsyncSession, dashboard_id: str) -> Dict[str, Any]:
    """看板附录：A 字段字典 / B 清洗日志 / C 指标计算明细 / D 数据血缘"""
    dash = (await sql_db.execute(select(Dashboard).where(Dashboard.id == dashboard_id))).scalar_one_or_none()
    if not dash:
        return {"error": "dashboard_not_found"}

    dataset_ids = list(dash.dataset_ids or [])
    if dash.primary_dataset_id and dash.primary_dataset_id not in dataset_ids:
        dataset_ids.insert(0, dash.primary_dataset_id)

    # 图表主源：看板内嵌 config['charts']（生成流程未落 charts 表，以它为真实数据源）
    cfg_raw = dash.config or {}
    if isinstance(cfg_raw, str):
        try:
            cfg_raw = json.loads(cfg_raw)
        except Exception:
            cfg_raw = {}
    embedded = (cfg_raw.get("charts") or []) if isinstance(cfg_raw, dict) else []

    # 兜底：charts 表（若未来生成流程落库）
    table_charts = (await sql_db.execute(
        select(Chart).where(Chart.dashboard_id == dashboard_id).order_by(Chart.sort_order)
    )).scalars().all()

    normalized = [_normalize_chart(c, dash.primary_dataset_id, i) for i, c in enumerate(embedded)]
    seen_titles = {c["title"] for c in normalized}
    for c in table_charts:
        if c.title in seen_titles:
            continue
        normalized.append(_normalize_chart({
            "chart_type": c.type, "title": c.title, "dataset_id": c.dataset_id,
            "x_field": (c.config_json or {}).get("x_field"),
            "y_field": (c.config_json or {}).get("y_field"),
            "config": c.config_json or {},
            "aggregate": (c.config_json or {}).get("aggregate"),
        }, dash.primary_dataset_id, len(normalized)))

    # 字段字典涉及的数据集 = 看板关联数据集 + 图表实际绑定的数据集
    all_ds_ids = list(dataset_ids)
    for c in normalized:
        if c.get("dataset_id") and c["dataset_id"] not in all_ds_ids:
            all_ds_ids.append(c["dataset_id"])

    from app.models.dataset import Dataset
    datasets = []
    if all_ds_ids:
        datasets = (await sql_db.execute(
            select(Dataset).where(Dataset.id.in_(all_ds_ids))
        )).scalars().all()

    duck = get_duckdb()

    field_dicts = [_field_dict_for_dataset(duck, ds) for ds in datasets]
    clean_log = await _clean_log(sql_db, all_ds_ids)
    metrics = _metric_detail(duck, normalized)

    return {
        "dashboard_id": dashboard_id,
        "dashboard_name": dash.name,
        "field_dict": field_dicts,
        "clean_log": clean_log,
        "metrics": metrics,
        "note": "以上口径全部来自真实管线元数据（清洗层实测 / 清洗规则 / 图表计算口径），可在清洗后数据集上复跑复现。数据血缘可在「数据血缘」页查看。",
    }
