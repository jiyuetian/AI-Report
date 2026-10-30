"""离线专业看板规划（A0-3 集成辅助）。

把 K1 行业建议库(offline_board_planner) + 洞察层(s3_insight_layer) 组装成
规则兜底分支可用的"离线专业规划"。纯增量、对主链路零侵入：
- 读取 domain playbook → 规划 KPI(L1)/叙事(L2)
- 从派生指标/字段画像尽力抽取摘要 → 算洞察/预警卡
- 任何抽取失败都优雅跳过，绝不阻断主链路

由 brain_run_sse.py 在 generated_by=="rule_engine" 分支调用。
"""
from typing import Any, Dict, List, Optional

try:  # 包内导入（生产主链路：app.core.brain_modules.offline_pro_board）
    from .domain_playbook_loader import get_playbook
    from .offline_board_planner import plan_board
    from .s3_insight_layer import compute_insights
    from .experience_store import retrieve_experience
except ImportError:  # 扁平导入（离线自测脚本把本目录塞进 sys.path）
    from domain_playbook_loader import get_playbook
    from offline_board_planner import plan_board
    from s3_insight_layer import compute_insights
    from experience_store import retrieve_experience


def _fields_to_profile(fields) -> List[Dict[str, Any]]:
    out = []
    for f in fields or []:
        if isinstance(f, dict):
            out.append({
                "name": f.get("name"),
                "type": f.get("type") or f.get("dtype"),
                "role": f.get("business_role") or f.get("role"),
                "cardinality": f.get("cardinality") or f.get("distinct_count"),
            })
    return out


def _build_data_summary(derived_metrics, field_profiles) -> Dict[str, Any]:
    """尽力从派生指标 / 字段画像抽取洞察层所需摘要；缺项优雅跳过。"""
    summary: Dict[str, Any] = {"metrics": {}, "groups": {}, "raw_stats": {}, "benchmarks": {}}
    dm = derived_metrics or {}
    if isinstance(dm, dict):
        for v in dm.values():
            if isinstance(v, dict) and v.get("name"):
                name = v["name"]
                m = {}
                for key in ("latest", "mom", "yoy", "mean", "std", "max", "sum", "value"):
                    if key in v and isinstance(v[key], (int, float)):
                        m[key] = v[key]
                if m:
                    summary["metrics"][name] = m
    for fp in field_profiles or []:
        if not isinstance(fp, dict):
            continue
        dist = fp.get("distribution") or fp.get("distinct") or fp.get("value_counts")
        if isinstance(dist, dict):
            summary["groups"][fp.get("name")] = {
                str(k): (v if isinstance(v, (int, float)) else 1) for k, v in dist.items()
            }
    return summary


def build_data_summary(derived_metrics, field_profiles) -> Dict[str, Any]:
    """对外暴露的摘要构造函数（G2/G4：洞察层需要可独立获得 data_summary）。

    与 `_build_data_summary` 同实现，供 brain_run_sse 在「AI 主链路」也构造同样的
    事实底座——保证 AI 分支与规则兜底分支的洞察口径完全一致。
    """
    return _build_data_summary(derived_metrics, field_profiles or [])


def _build_signature(domain: str, fields, derived_metrics) -> str:
    """从 (字段形态, 指标名集合) 生成稳定的数据形态签名，供经验库检索相似历史。

    白盒可解释：仅用字段名与指标名拼接，不含具体数值，
    因此"同样结构的数据"会命中同一经验簇，实现 K2 经验的形态级复用。
    """
    field_names = sorted(
        f.get("name") for f in (fields or []) if isinstance(f, dict) and f.get("name")
    )
    metric_names = sorted(
        v.get("name") for v in (derived_metrics or {}).values()
        if isinstance(v, dict) and v.get("name")
    )
    return f"{domain}|" + ",".join(field_names) + "|" + ",".join(metric_names)


def build_offline_pro_plan(
    domain: str,
    fields,
    field_profiles=None,
    derived_metrics=None,
) -> Dict[str, Any]:
    pb = get_playbook(domain)
    fp = _fields_to_profile(fields) if not field_profiles else field_profiles
    data_summary = _build_data_summary(derived_metrics, field_profiles or [])
    # plan_board 需要扁平数值聚合 {指标名: 数值}；从 metrics 摘要抽取 latest/value
    flat_agg = {
        name: (m.get("latest") if m.get("latest") is not None else m.get("value"))
        for name, m in data_summary.get("metrics", {}).items()
        if isinstance(m, dict)
    }
    plan = plan_board(domain, fp, flat_agg)
    insights = compute_insights(data_summary, playbook=pb)
    # K2 经验引擎：检索相似数据形态下的历史有效决策，作为离线规划的经验提示
    experience_hints: List[Dict[str, Any]] = []
    try:
        sig = _build_signature(domain, fields, derived_metrics)
        experience_hints = retrieve_experience(domain, sig, top_n=3)
    except Exception as e:  # 经验检索失败绝不影响主链路/离线规划
        print(f"[Brain] A0-2 经验检索失败(忽略): {e}")
    return {
        "domain": domain,
        "playbook_domain": pb.get("domain"),
        "board_plan": plan,
        "insights": insights,
        "experience_hints": experience_hints,
    }
