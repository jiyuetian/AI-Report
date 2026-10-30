"""离线 board 规划器（K1 行业成熟建议 + K2 经验占位）。

职责：在 LLM 离线时，依据领域 playbook 把"字段画像 + 聚合值"规划成
一屏**专业分析师水准**的看板结构：KPI(L1) + 叙事图表(L2) + 洞察卡 + 预警卡。
这是"离线专业分析师"的核心（见《白盒规则说明》§2.5.5）。

输入：
  domain      领域标签（风控/财务/通用…）
  fields      字段画像列表，每项 {name,type,role/business_role,cardinality,...}
  aggregates  预计算聚合值 dict，如 {"逾期率":0.07,"在保余额":1234567,"渠道分布":{...}}
输出：
  {domain, playbook_domain, kpis, narrative_charts, insight_cards, warning_cards}
仅依赖 stdlib + 同目录 loader。
"""
from typing import Any, Dict, List, Optional

try:  # 包内导入（生产主链路）
    from .domain_playbook_loader import get_playbook
except ImportError:  # 扁平导入（离线自测脚本）
    from domain_playbook_loader import get_playbook


def _kw_hit(text: str, keywords: List[str]) -> bool:
    t = (text or "").lower()
    return any(k.lower() in t for k in keywords)


def _match_field(metric_keywords: List[str], fields: List[Dict]) -> Optional[Dict]:
    for f in fields:
        name = f.get("name", "") or ""
        role = f.get("role", "") or f.get("business_role", "") or ""
        if _kw_hit(name, metric_keywords) or _kw_hit(role, metric_keywords):
            return f
    return None


def plan_board(
    domain: str,
    fields: List[Dict[str, Any]],
    aggregates: Dict[str, Any],
) -> Dict[str, Any]:
    pb = get_playbook(domain)
    result: Dict[str, Any] = {
        "domain": domain,
        "playbook_domain": pb.get("domain", "general"),
        "kpis": [],
        "narrative_charts": [],
        "insight_cards": [],
        "warning_cards": [],
    }

    # 1) KPI(L1)：playbook 必看指标 → 命中字段
    for m in pb.get("must_have_metrics", []):
        fld = _match_field(m.get("keywords", []), fields)
        result["kpis"].append({
            "key": m["key"],
            "kind": m.get("kind"),
            "field": fld.get("name") if fld else None,
            "benchmark": m.get("benchmark"),
            "matched": fld is not None,
        })

    # 2) 叙事图表(L2)：依 playbook 叙事顺序生成骨架
    date_field = next(
        (f for f in fields if f.get("type") == "date"
         or "date" in str(f.get("name", "")).lower()
         or "时间" in (str(f.get("name", "")) + str(f.get("role", "")))),
        None,
    )
    num_fields = [f for f in fields if f.get("type") == "number"]
    cat_field = next(
        (f for f in fields if f.get("type") in ("text", "category")
         or (isinstance(f.get("cardinality"), int) and 1 < f.get("cardinality", 0) < 50)),
        None,
    )
    for step in pb.get("narrative", []):
        spec: Dict[str, Any] = {"step": step, "charts": []}
        if step in ("趋势", "结构"):
            if date_field and num_fields:
                spec["charts"] = [
                    {"type": "line", "x": date_field["name"], "y": nf["name"]}
                    for nf in num_fields[:2]
                ]
        elif step in ("对比", "分布"):
            if cat_field and num_fields:
                spec["charts"] = [
                    {"type": "bar", "category": cat_field["name"], "value": nf["name"]}
                    for nf in num_fields[:2]
                ]
        elif step in ("明细",):
            spec["charts"] = [{"type": "table"}]
        elif step in ("结论", "结论预警", "概览"):
            spec["charts"] = [{"type": "summary"}]
        result["narrative_charts"].append(spec)

    # 3) 预警卡：anomaly_rules 命中聚合值
    for rule in pb.get("anomaly_rules", []):
        metric = rule.get("metric")
        val = aggregates.get(metric)
        if val is None:
            continue
        op, thr = rule.get("op"), rule.get("threshold")
        hit = (
            (op == ">" and val > thr) or (op == "<" and val < thr)
            or (op == ">=" and val >= thr) or (op == "<=" and val <= thr)
        )
        if hit:
            result["warning_cards"].append({
                "metric": metric, "value": val, "threshold": thr,
                "action": rule.get("action"), "message": rule.get("message"),
            })

    # 4) 洞察卡：insight_patterns 占位（真实值由调用方注入 aggregates，如 top_contributor/环比）
    for pat in pb.get("insight_patterns", []):
        result["insight_cards"].append({
            "pattern": pat,
            "available": pat in aggregates
            or any(pat in str(k) for k in aggregates.keys()),
        })

    return result
