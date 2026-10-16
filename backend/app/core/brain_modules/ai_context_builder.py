"""AI 对话六层血缘上下文构造器（night48 子任务2）

只读地把真实数据血缘注入 chat.py 的 LLM 提示词，让 AI 不再"盲聊"，
能引用 L0-L5 各层的真实摘要，尤其 L3 聚合层的真实 DuckDB 数值。

对应真机验收问题：C-5/C-6（AI 读数据）。
对应架构根因：根因2（AI 无数据通道）——本模块给 AI 开一条只读数据通道。

六层定义（见 docs/六层管线与被控提示词.md）：
  L0 原始层     → 用户上传原始文件（ds_{dataset_id}），不可修改
  L1 清洗层     → 去重/空值填充/格式修正（ds_{dataset_id}_cleaned）
  L2 加工层     → 业务规则派生指标（来自数据集配置，只读引用）
  L3 聚合层     → 汇总/分组统计（真实 DuckDB 聚合，关键真实数值）
  L4 图表层     → 当前看板图表与各自聚合口径
  L5 质检层     → 发现的问题（来自看板质量修复记录）

红线：只读 SELECT，不写、不删、不建表、不改 site-packages。
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

try:
    from app.core.duckdb_manager import quote_ident
except Exception:  # 独立自测（脱离 app 包）时退化
    def quote_ident(ident: str) -> str:
        return '"' + str(ident).replace('"', '""') + '"'


# ── 数值/百分比格式化（与 data_fact_pack 一致的精简风格）─────────────
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


def _round(v: Any) -> Any:
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
    return round(f, 4)


# 语义聚合推断：金额/计数类→sum，比率/天数/年龄类→avg
_AMT_HINTS = ("金额", "余额", "代偿", "担保", "本金", "总额", "总数", "count", "数", "量")
_RATE_HINTS = ("率", "天数", "年龄", "时长", "avg", "mean", "median")


def _infer_agg(field: str) -> Optional[str]:
    if not field:
        return None
    if any(k in field for k in _AMT_HINTS):
        return "sum"
    if any(k in field for k in _RATE_HINTS):
        return "avg"
    return None


class AIContextBuilder:
    """给 AI 对话构建六层血缘上下文（只读，不触发任何计算写入）。"""

    def build_context(
        self,
        dataset_id: str,
        dashboard_config: Optional[Dict[str, Any]] = None,
        db: Any = None,
        score_detail: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """构建 L0-L5 每层摘要，返回结构化 dict。

        Args:
            dataset_id: 数据集 ID（对应 DuckDB 表 ds_{dataset_id} / ds_{dataset_id}_cleaned）
            dashboard_config: 看板 config（提供 L4 图表层与 L5 质检记录），可空
            db: 可选 DuckDBManager（测试注入内存桩）；缺省走全局 get_duckdb()
        """
        if not dataset_id:
            return {}
        try:
            _db = db if db is not None else self._get_db()
        except Exception:
            _db = None
        return {
            "L0_raw": self._build_raw_summary(dataset_id, _db),
            "L1_clean": self._build_clean_summary(dataset_id, _db),
            "L2_processed": self._build_processed_summary(dataset_id, dashboard_config),
            "L3_aggregated": self._build_aggregated_summary(dataset_id, _db),
            "L4_charts": self._build_chart_summary(dataset_id, dashboard_config),
            "L5_findings": self._build_findings_summary(dataset_id, dashboard_config),
            "L5b_score": self._build_score_detail(score_detail),
        }

    # ── 内部工具 ──────────────────────────────────────────────
    @staticmethod
    def _get_db():
        from app.core.duckdb_manager import get_duckdb
        return get_duckdb()

    @staticmethod
    def _orig_table(dataset_id: str) -> str:
        return f"ds_{dataset_id}"

    @staticmethod
    def _cleaned_table(dataset_id: str) -> str:
        return f"ds_{dataset_id}_cleaned"

    @staticmethod
    def _is_numeric(col_type: str) -> bool:
        t = (col_type or "").upper()
        return any(k in t for k in (
            "DECIMAL", "DOUBLE", "FLOAT", "REAL", "NUMERIC",
            "INT", "BIGINT", "HUGEINT", "SMALLINT", "TINYINT",
        ))

    # ── L0 原始层 ──────────────────────────────────────────────
    def _build_raw_summary(self, dataset_id: str, db: Any) -> Dict[str, Any]:
        if db is None or not getattr(db, "table_exists", lambda t: False)(self._orig_table(dataset_id)):
            return {"available": False, "note": "原始表不可用（无 DuckDB 或表不存在）"}
        t = self._orig_table(dataset_id)
        try:
            rows = db.conn.execute(f"SELECT COUNT(*) FROM {quote_ident(t)}").fetchone()[0] or 0
            cols = db.conn.execute(f"DESCRIBE {quote_ident(t)}").fetchall()
            col_list = [{"name": r[0], "type": r[1]} for r in cols]
            return {
                "available": True,
                "row_count": rows,
                "field_count": len(col_list),
                "fields": col_list[:30],
            }
        except Exception as e:
            return {"available": False, "note": f"读取原始层失败: {e}"}

    # ── L1 清洗层 ──────────────────────────────────────────────
    def _build_clean_summary(self, dataset_id: str, db: Any) -> Dict[str, Any]:
        if db is None:
            return {"available": False, "note": "清洗层不可用"}
        orig = self._orig_table(dataset_id)
        clean = self._cleaned_table(dataset_id)
        try:
            if not db.table_exists(clean):
                return {"available": False, "note": "清洗层尚未生成（只读：不主动创建）"}
            o_rows = db.conn.execute(f"SELECT COUNT(*) FROM {quote_ident(orig)}").fetchone()[0] or 0
            c_rows = db.conn.execute(f"SELECT COUNT(*) FROM {quote_ident(clean)}").fetchone()[0] or 0
            removed = max(0, o_rows - c_rows)
            return {
                "available": True,
                "original_rows": o_rows,
                "cleaned_rows": c_rows,
                "removed_rows": removed,
                "dup_rate": round(removed / o_rows, 4) if o_rows else 0.0,
            }
        except Exception as e:
            return {"available": False, "note": f"读取清洗层失败: {e}"}

    # ── L2 加工层 ──────────────────────────────────────────────
    def _build_processed_summary(self, dataset_id: str, config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        derived = (config or {}).get("derived_metrics") or []
        if isinstance(derived, dict):
            derived = list(derived.values())
        names = [d.get("name") if isinstance(d, dict) else str(d) for d in (derived or [])][:20]
        return {
            "available": True,
            "derived_metric_count": len(names) if isinstance(names, list) else 0,
            "derived_metrics": names,
            "note": "加工层派生指标来自数据集配置（只读引用，不触发重算）",
        }

    # ── L3 聚合层（真实 DuckDB 数值）─────────────────────────────
    def _build_aggregated_summary(self, dataset_id: str, db: Any) -> Dict[str, Any]:
        if db is None:
            return {"available": False, "note": "聚合层不可用"}
        clean = self._cleaned_table(dataset_id)
        orig = self._orig_table(dataset_id)
        tbl = clean if db.table_exists(clean) else (orig if db.table_exists(orig) else None)
        if not tbl:
            return {"available": False, "note": "无可用表做聚合"}
        try:
            cols = db.conn.execute(f"DESCRIBE {quote_ident(tbl)}").fetchall()
            numeric = [r[0] for r in cols if self._is_numeric(r[1])]
            agg: Dict[str, Any] = {}
            for nm in numeric[:8]:
                q = quote_ident(nm)
                r = db.conn.execute(
                    f"SELECT SUM({q}), AVG({q}), COUNT({q}) FROM {quote_ident(tbl)}"
                ).fetchone()
                agg[nm] = {
                    "sum": _round(r[0]) if r else None,
                    "avg": _round(r[1]) if r else None,
                    "count": r[2] if r else 0,
                }
            return {"available": True, "table": tbl, "numeric_aggregates": agg}
        except Exception as e:
            return {"available": False, "note": f"聚合失败: {e}"}

    # ── L4 图表层 ──────────────────────────────────────────────
    def _build_chart_summary(self, dataset_id: str, config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        charts = (config or {}).get("charts", []) or []
        out = []
        for c in charts[:20]:
            out.append({
                "title": c.get("title", "未命名"),
                "chart_type": c.get("chart_type"),
                "x_field": c.get("x_field") or c.get("category_field"),
                "y_field": c.get("y_field") or c.get("value_field"),
                "agg": c.get("aggregation") or _infer_agg(
                    str(c.get("y_field") or c.get("value_field") or "")
                ),
            })
        return {"available": True, "chart_count": len(charts), "charts": out}

    # ── L5 质检层 ──────────────────────────────────────────────
    def _build_findings_summary(self, dataset_id: str, config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        log = (config or {}).get("quality_fix_log", []) or []
        return {
            "available": True,
            "quality_fix_count": len(log),
            "latest": log[-1] if log else None,
            "note": "质检发现来自看板质量修复记录" if log else "暂无质检问题记录",
        }

    # ── L5b 评分详情层（阶段2 P1 任务1d：让 AI 知道看板为何被否决）─────────────
    def _build_score_detail(self, score_detail: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """把 S5 评分详情（含 LLM 自评 critique）归一化为 L5b 结构，供 AI 消费。

        复用 s4_orchestrator.build_s5_detail 的归一化逻辑；若未传入则为不可用。
        """
        if not score_detail:
            return {"available": False, "note": "无 S5 评分详情"}
        try:
            from app.core.brain_modules.s4_orchestrator import build_s5_detail
            return build_s5_detail(score_detail)
        except Exception as e:
            return {"available": False, "note": f"S5 评分详情解析失败: {e}"}


def format_lineage_section(ctx: Dict[str, Any]) -> str:
    """把六层血缘上下文渲染成喂给 LLM 的精简中文段（≤500 字）。"""
    if not ctx:
        return ""
    lines = ["【六层血缘上下文】（基于真实数据，回答必须引用以下真实数值，严禁编造）"]
    l0 = ctx.get("L0_raw", {})
    if l0.get("available"):
        lines.append(f"- L0 原始层：{l0.get('row_count')} 行 × {l0.get('field_count')} 字段")
    l1 = ctx.get("L1_clean", {})
    if l1.get("available"):
        lines.append(
            f"- L1 清洗层：原始 {l1.get('original_rows')} 行 → 清洗后 {l1.get('cleaned_rows')} 行"
            f"（去重 {l1.get('removed_rows')} 行，重复率 {_pct(l1.get('dup_rate'))}）"
        )
    l2 = ctx.get("L2_processed", {})
    if l2.get("available") and l2.get("derived_metrics"):
        lines.append(
            f"- L2 加工层：派生指标 {l2.get('derived_metric_count')} 个"
            f"（{', '.join(l2.get('derived_metrics', [])[:6])}）"
        )
    l3 = ctx.get("L3_aggregated", {})
    if l3.get("available"):
        parts = []
        for k, v in list((l3.get("numeric_aggregates") or {}).items())[:6]:
            parts.append(f"{k}: SUM={_fmt_num(v.get('sum'))} / AVG={_fmt_num(v.get('avg'))}")
        if parts:
            lines.append("- L3 聚合层（真实数值）：" + "；".join(parts))
    l4 = ctx.get("L4_charts", {})
    if l4.get("available"):
        cs = [
            f"{c.get('title')}({c.get('chart_type')},agg={c.get('agg')})"
            for c in l4.get("charts", [])[:8]
        ]
        lines.append(f"- L4 图表层：{l4.get('chart_count')} 张图 [{'；'.join(cs)}]")
    l5 = ctx.get("L5_findings", {})
    if l5.get("available"):
        lines.append(f"- L5 质检层：质量修复 {l5.get('quality_fix_count')} 次，{l5.get('note')}")
    l5b = ctx.get("L5b_score", {})
    if l5b.get("available"):
        dims = l5b.get("dimension_scores", {}) or {}
        _dims_txt = "、".join(f"{k}={v}" for k, v in dims.items()) if dims else "—"
        _crit = f"；自评: {l5b['critique']}" if l5b.get("critique") else ""
        lines.append(
            f"- L5b 评分详情：总分 {l5b.get('overall_score')}（{'通过' if l5b.get('passed') else '未通过'}），"
            f"维度[{_dims_txt}]；处置={l5b.get('disposal', {}).get('grade')}；"
            f"改进：{('；'.join(l5b.get('improvement_suggestions', [])[:3]) or '无')}{_crit}"
        )
    return "\n".join(lines)
