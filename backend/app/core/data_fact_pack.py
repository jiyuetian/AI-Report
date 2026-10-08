"""数据事实包（Data Fact Pack）— night37

为两条 LLM 链路（看板图表选型 / 报表执行摘要）提供「真实数据事实」，
让 LLM 基于 分布 / 占比 / 趋势 / 集中度 / 相关性 / 异常 等聚合事实来选图与写结论，
而非仅复述字段列表或 SUM/AVG。

对应根因（教练定位）：
- s3_llm_enhancer._build_prompt 只喂「主题 + 字段列表/类型/画像 + 维度建议 + 粒度 + 目标」，
  没有任何数据事实 → LLM 只能"选图"，天花板低。
- report_generator._ch2_executive_summary 只喂「总记录数 + 每个数值字段 SUM/AVG」，
  同样没有数据事实 → LLM 只能"复述数字"，讲不出数据里的故事。

性能护栏（红线：必须有界）：
- 大表（>DUCKDB_MAX_ROWS_PROFILE）自动改用 RESERVOIR(100000) 采样子查询，避免全表扫描。
- 整体墙钟预算 FACT_PACK_BUDGET_SEC（默认 3.0s），超时即停止剩余步骤、返回已得部分。
- 每个聚合 try/except 静默降级；事实包不可用 / 异常 / 超时都绝不阻断生成（调用方回退现状）。
- 只读 SELECT，不写 / 不删 / 不建表（红线④）。

调用方：
- B1 看板选型：s3_llm_enhancer 通过 get_duckdb() 取 DuckDBManager 注入。
- B2 执行摘要：report_generator 用 self.db（DuckDBManager）注入。
"""
from __future__ import annotations

import time
import math
import itertools
from typing import Any, Dict, List, Optional

try:
    from app.core.duckdb_manager import quote_ident, DUCKDB_MAX_ROWS_PROFILE
except Exception:  # 独立自测（脱离 app 包）时退化
    def quote_ident(ident: str) -> str:
        return '"' + str(ident).replace('"', '""') + '"'

    DUCKDB_MAX_ROWS_PROFILE = 100000

# ── 性能护栏常量 ──────────────────────────────────────────────
FACT_PACK_BUDGET_SEC = 3.0      # 整体墙钟预算（秒）
CORR_PAIR_CAP = 45              # 相关性成对查询上限（≈10 个数值字段）
NUMERIC_FOR_CORR_CAP = 10       # 参与相关性的数值字段上限
CATEGORY_MAX_FIELDS = 15        # 参与 top 分布的分类字段上限
TIME_POINTS_CAP = 24            # 时间趋势月度点上限
SIG_FIGS = 6                    # 数值保留有效位数（避免 17 位裸奔）


# ── 数值/字符串格式化辅助 ────────────────────────────────────
def _round(v: Any, sig: int = SIG_FIGS) -> Any:
    """保留 sig 位有效数字；None/NaN/Inf → None；0 → 0。"""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return v
    if f == 0:
        return 0
    if math.isnan(f) or math.isinf(f):
        return None
    mag = math.floor(math.log10(abs(f)))
    nd = sig - 1 - mag
    return round(f, nd)


def _truncate(s: Any, n: int = 40) -> str:
    s = str(s)
    return s if len(s) <= n else s[: n - 1] + "…"


def _fmt_num(v: Any) -> str:
    if v is None:
        return "—"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if f == 0:
        return "0"
    a = abs(f)
    if a >= 1e8:
        return f"{f / 1e8:.2f}亿"
    if a >= 1e4:
        return f"{f / 1e4:.2f}万"
    return f"{f:.4g}"


def _pct(x: Any) -> str:
    try:
        return f"{float(x) * 100:.1f}%"
    except (TypeError, ValueError):
        return "—"


def _classify_type(col_type: str) -> str:
    t = (col_type or "").upper()
    if any(k in t for k in ("DECIMAL", "DOUBLE", "FLOAT", "REAL", "NUMERIC",
                            "INT", "BIGINT", "HUGEINT", "SMALLINT", "TINYINT")):
        return "NUMBER"
    if any(k in t for k in ("DATE", "TIMESTAMP", "TIME")):
        return "DATE"
    if "BOOL" in t:
        return "CATEGORY"
    return "TEXT"


def _describe_columns(db: Any, table_name: str) -> List[Dict[str, str]]:
    """用 DESCRIBE 取列名与类型（稳健，兼容中文/含括号列名）。"""
    rows = db.conn.execute(f"DESCRIBE {quote_ident(table_name)}").fetchall()
    cols = []
    for r in rows:
        cols.append({"name": r[0], "type": r[1]})
    return cols


def _sample_subquery(table_name: str, row_count: int) -> str:
    """大表走采样子查询；小表直接用原表。"""
    if row_count > DUCKDB_MAX_ROWS_PROFILE:
        return f"(SELECT * FROM {quote_ident(table_name)} USING SAMPLE RESERVOIR ({DUCKDB_MAX_ROWS_PROFILE}))"
    return quote_ident(table_name)


async def build_fact_pack(
    db: Any,
    table_name: str,
    field_profiles: Optional[List[Dict[str, Any]]] = None,
    derived_metrics: Optional[Dict[str, Any]] = None,
    max_cardinality: int = 30,
) -> Dict[str, Any]:
    """构建数据事实包（全部来自真实 DuckDB 聚合，确定性）。

    Args:
        db: DuckDBManager（需提供 .conn 与 .table_exists）。
        table_name: 真实业务表名（如 ds_{dataset_id}）。
        field_profiles: 可选，字段画像列表（name/distinct_count/null_rate/sample_values），
                        用于补充 distinct 等；缺失时仅靠 DuckDB 内省。
        derived_metrics: 可选，预留（当前未强制使用，避免误改口径）。
        max_cardinality: 分类字段视为"低基数可分布"的基数上限。

    Returns:
        {
          meta, numeric_facts, category_facts, time_facts,
          correlation_facts, quality_facts, _elapsed_sec, _budget_exceeded
        }
        异常 / 超时均返回已得部分（不抛），调用方据此回退。
    """
    start = time.time()
    pack: Dict[str, Any] = {
        "meta": {},
        "numeric_facts": {},
        "category_facts": {},
        "time_facts": {},
        "correlation_facts": [],
        "quality_facts": {},
        "_budget_exceeded": False,
    }

    def _over_budget() -> bool:
        return (time.time() - start) > FACT_PACK_BUDGET_SEC

    try:
        # 0) 表存在性 + 行数 + 列画像
        if not getattr(db, "table_exists", lambda t: False)(table_name):
            return pack
        row_count = db.conn.execute(f"SELECT COUNT(*) FROM {quote_ident(table_name)}").fetchone()[0] or 0
        cols = _describe_columns(db, table_name)
        pack["meta"] = {"row_count": row_count, "field_count": len(cols)}

        # 字段画像索引（可选补充 distinct / 样例）
        prof_idx: Dict[str, Dict[str, Any]] = {}
        if field_profiles:
            for fp in field_profiles:
                if isinstance(fp, dict) and fp.get("name"):
                    prof_idx[fp["name"]] = fp

        numeric_cols = [c for c in cols if _classify_type(c["type"]) == "NUMBER"]
        date_cols = [c for c in cols if _classify_type(c["type"]) == "DATE"]
        cat_cols = [c for c in cols if _classify_type(c["type"]) in ("TEXT", "CATEGORY")]

        tbl = _sample_subquery(table_name, row_count)

        # 1) 数值事实：单查询聚合 sum/avg/median/min/max/p25/p75 + null_rate
        for c in numeric_cols:
            if _over_budget():
                pack["_budget_exceeded"] = True
                break
            nm = c["name"]
            q = quote_ident(nm)
            try:
                r = db.conn.execute(
                    f"SELECT SUM({q}), AVG({q}), MEDIAN({q}), MIN({q}), MAX({q}), "
                    f"QUANTILE_CONT({q}, 0.25), QUANTILE_CONT({q}, 0.75), "
                    f"COUNT(*), COUNT({q}) FROM {tbl}"
                ).fetchone()
                if r is None:
                    continue
                total = r[7] or 0
                non_null = r[8] or 0
                null_rate = round(1 - (non_null / total), 4) if total else 0.0
                pack["numeric_facts"][nm] = {
                    "sum": _round(r[0]),
                    "avg": _round(r[1]),
                    "median": _round(r[2]),
                    "min": _round(r[3]),
                    "max": _round(r[4]),
                    "p25": _round(r[5]),
                    "p75": _round(r[6]),
                    "null_rate": null_rate,
                }
            except Exception:
                continue

        # 2) 分类事实：top 分布（≤8）+ top1 占比
        for c in cat_cols[:CATEGORY_MAX_FIELDS]:
            if _over_budget():
                pack["_budget_exceeded"] = True
                break
            nm = c["name"]
            q = quote_ident(nm)
            try:
                tot = db.conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0] or 0
                if tot == 0:
                    continue
                rows = db.conn.execute(
                    f"SELECT {q} AS v, COUNT(*) AS c FROM {tbl} WHERE {q} IS NOT NULL "
                    f"GROUP BY {q} ORDER BY c DESC LIMIT 8"
                ).fetchall()
                top = []
                top1 = 0.0
                for row in rows:
                    cnt = row[1] or 0
                    share = round(cnt / tot, 4)
                    top.append({"value": _truncate(str(row[0])), "count": cnt, "share": share})
                    if not top1:
                        top1 = share
                distinct = prof_idx.get(nm, {}).get("distinct_count")
                pack["category_facts"][nm] = {
                    "distinct": distinct,
                    "top": top,
                    "top1_share": top1,
                }
            except Exception:
                continue

        # 3) 时间事实：按月聚合（行数 + 首个数值指标 sum），≤24 点
        if date_cols and numeric_cols and not _over_budget():
            dc = date_cols[0]
            dq = quote_ident(dc["name"])
            metric = numeric_cols[0]
            mq = quote_ident(metric["name"])
            try:
                rows = db.conn.execute(
                    f"SELECT strftime({dq}, '%Y-%m') AS m, COUNT(*) AS c, SUM({mq}) AS s "
                    f"FROM {tbl} WHERE {dq} IS NOT NULL GROUP BY m ORDER BY m LIMIT {TIME_POINTS_CAP}"
                ).fetchall()
                series = [{"month": r[0], "count": r[1] or 0, "metric_sum": _round(r[2])} for r in rows]
                if series:
                    pack["time_facts"][dc["name"]] = {
                        "points": len(series),
                        "first": series[0]["month"],
                        "last": series[-1]["month"],
                        "series": series,
                    }
            except Exception:
                pass

        # 4) 相关性：数值字段两两 |corr| Top-5（成对上限 CORR_PAIR_CAP）
        if not _over_budget():
            try:
                ncands = [c["name"] for c in numeric_cols][:NUMERIC_FOR_CORR_CAP]
                pairs = []
                for a, b in itertools.combinations(ncands, 2):
                    if len(pairs) >= CORR_PAIR_CAP:
                        break
                    if _over_budget():
                        pack["_budget_exceeded"] = True
                        break
                    aq, bq = quote_ident(a), quote_ident(b)
                    try:
                        corr = db.conn.execute(f"SELECT CORR({aq}, {bq}) FROM {tbl}").fetchone()[0]
                        if corr is not None and not (isinstance(corr, float) and math.isnan(corr)):
                            pairs.append({"a": a, "b": b, "corr": round(float(corr), 3), "abs": abs(float(corr))})
                    except Exception:
                        continue
                pairs.sort(key=lambda x: x["abs"], reverse=True)
                pack["correlation_facts"] = pairs[:5]
            except Exception:
                pass

        # 5) 质量事实：空值率 Top-N + 重复行率
        try:
            null_top = []
            for nm, f in pack["numeric_facts"].items():
                if f.get("null_rate"):
                    null_top.append({"field": nm, "null_rate": f["null_rate"]})
            for nm, f in pack["category_facts"].items():
                # 分类字段空值率需单独算；此处用画像 null_rate（若有）
                nr = prof_idx.get(nm, {}).get("null_rate")
                if nr:
                    null_top.append({"field": nm, "null_rate": nr})
            null_top.sort(key=lambda x: x["null_rate"], reverse=True)
            pack["quality_facts"]["null_rate_top"] = null_top[:5]
            if not _over_budget():
                try:
                    tot = db.conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0] or 0
                    uniq = db.conn.execute(
                        f"SELECT COUNT(*) FROM (SELECT DISTINCT * FROM {tbl})"
                    ).fetchone()[0] or 0
                    dup = tot - uniq
                    pack["quality_facts"]["duplicate_row_rate"] = round(dup / tot, 4) if tot else 0.0
                except Exception:
                    pass
        except Exception:
            pass

    except Exception as e:
        pack["_error"] = _truncate(str(e), 200)

    pack["_elapsed_sec"] = round(time.time() - start, 3)
    return pack


def format_fact_section(pack: Dict[str, Any]) -> str:
    """把事实包渲染成喂给 LLM 的精简中文段（看板选型 / 执行摘要共用）。"""
    if not pack or not pack.get("meta"):
        return ""
    lines = ["【数据事实】（基于真实数据聚合，选图与写结论必须引用以下事实，严禁凭空编造）"]
    meta = pack.get("meta", {})
    lines.append(f"- 规模：{meta.get('row_count')} 行 × {meta.get('field_count')} 字段")

    nf = pack.get("numeric_facts", {}) or {}
    if nf:
        parts = []
        for k, v in list(nf.items())[:8]:
            rng = f"{_fmt_num(v['min'])}~{_fmt_num(v['max'])}"
            parts.append(f"{k}：sum={_fmt_num(v['sum'])} / 中位={_fmt_num(v['median'])} / 量级[{rng}] / 空值率{_pct(v['null_rate'])}")
        lines.append("- 数值字段量级：" + "；".join(parts))

    cf = pack.get("category_facts", {}) or {}
    if cf:
        parts = []
        for k, v in list(cf.items())[:8]:
            top = v.get("top") or []
            if top:
                t0 = top[0]
                extra = " / ".join(f"{t['value']}({_pct(t['share'])})" for t in top[:3])
                parts.append(f"{k}：top1={t0['value']}({_pct(t0['share'])})；分布[{extra}]")
            else:
                parts.append(f"{k}：无显著分布")
        lines.append("- 分类字段分布：" + "；".join(parts))

    tf = pack.get("time_facts", {}) or {}
    if tf:
        for k, v in tf.items():
            lines.append(f"- 时间趋势：{k} 覆盖 {v.get('first')}~{v.get('last')}（{v.get('points')} 个月度点）")

    corr = pack.get("correlation_facts") or []
    if corr:
        parts = [f"{c['a']}↔{c['b']} |corr|={c['corr']}" for c in corr[:3]]
        lines.append("- 强相关性：" + "；".join(parts))

    qf = pack.get("quality_facts", {}) or {}
    nr = qf.get("null_rate_top") or []
    if nr:
        parts = [f"{x['field']}({_pct(x['null_rate'])})" for x in nr[:3]]
        lines.append("- 空值率偏高：" + "、".join(parts))
    dup = qf.get("duplicate_row_rate")
    if dup is not None:
        lines.append(f"- 重复行率：{_pct(dup)}")

    if pack.get("_budget_exceeded"):
        lines.append("- ⚠️ 事实包触发性能预算，部分事实可能不完整（已降级返回）")
    return "\n".join(lines)
