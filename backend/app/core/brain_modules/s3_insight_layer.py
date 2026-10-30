# -*- coding: utf-8 -*-
"""洞察层（A1 · 质量最大杠杆）— 规则事实底座。

设计取向（《AI-Report改造方案》G2/G3/G4，2026-10-29）：
  本模块只做**确定性事实计算**，零 LLM 依赖、零 DB 依赖，因此在线（AI 主执行）
  与离线（K1+K2 离线生成器）共用，且可由白盒脚本直接单测。
  AI 解读层见 insight_ai_enhancer.py（规则结果作为不可删改的事实底座交给 AI 深化）。

洞察卡七类（原四类 + G2 新增三类）：
  1. top_contributor  集中度（Top 分组占比偏高）
  2. mom_yoy_delta    环比/同比突变
  3. threshold_breach 阈值/基准突破
  4. outliers         离群值（mean + kσ）
  5. attribution      归因（有 drill 时做真实增量分解；否则结构 CR2 + 可验证假设）
  6. forecast         趋势外推（序列≥N 点走线性回归；否则朴素 mom 外推，低置信）
  7. recommendation   行动建议（由前六类事实卡推导，带证据引用）

输入 data_summary 结构（由管线从 DuckDB 产出，本模块仅消费）：
  {
    "metrics":  { "在保余额": {"latest":..,"mom":..,"yoy":..,"series":[..]} },
    "groups":   { "渠道": {"渠道A": 5000000, "渠道B": 3000000} },
    "benchmarks": { "逾期率": 0.05 },
    "raw_stats": { "逾期率": {"mean":..,"std":..,"max":..} },
    "drill":    { "在保余额": {"渠道": {"渠道A": {"prev":..,"curr":..}, ...} } }  # 可选，G2 真实归因
  }
输出：上述七组洞察卡 dict，每组为一个 list[dict]。

所有阈值一律取自 threshold_config（键：insight_*），不再内联硬编码。
"""
from typing import Any, Dict, List, Optional

try:  # 正常包内导入
    from app.core.brain_modules.threshold_config import DEFAULT_THRESHOLDS as _DEFAULT_THRESHOLDS
except Exception:  # 离线/扁平导入（sys.path 直接指向 brain_modules）时回退本地默认
    _DEFAULT_THRESHOLDS = {
        "insight_top_share": 0.30,
        "insight_delta": 0.20,
        "insight_outlier_sigma": 3.0,
        "insight_concentration_hhi": 0.25,
        "insight_forecast_min_points": 3,
        "insight_max_cards": 8,
    }

__all__ = ["compute_insights", "INSIGHT_GROUPS"]

INSIGHT_GROUPS = (
    "top_contributor",
    "mom_yoy_delta",
    "threshold_breach",
    "outliers",
    "attribution",
    "forecast",
    "recommendation",
)


def _f(x: Any, default: Optional[float] = None) -> Optional[float]:
    return float(x) if isinstance(x, (int, float)) else default


def _pct(x: float) -> str:
    return f"{x:.2%}" if abs(x) < 1 else f"{x:.2f}"


def compute_insights(
    data_summary: Dict[str, Any],
    playbook: Dict[str, Any] = None,
    thresholds: Optional[Dict[str, Any]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """从数据摘要计算七类洞察卡（纯规则，确定性）。

    Args:
        data_summary: 见模块 docstring
        playbook: 行业剧本（提供 benchmark 基准）
        thresholds: 阈值覆盖（None 时用 threshold_config 默认值；管理员可在
                    brain_configs.thresholds 调整，实现白盒可改）
    """
    t = dict(_DEFAULT_THRESHOLDS)
    if thresholds:
        t.update({k: v for k, v in thresholds.items() if k in t})

    top_share_min = _f(t.get("insight_top_share"), 0.30)
    delta_min = abs(_f(t.get("insight_delta"), 0.20))
    sigma_k = _f(t.get("insight_outlier_sigma"), 3.0)
    cr2_min = _f(t.get("insight_concentration_hhi"), 0.25)
    min_points = int(_f(t.get("insight_forecast_min_points"), 3) or 3)
    max_cards = int(_f(t.get("insight_max_cards"), 8) or 8)

    insights: Dict[str, List[Dict[str, Any]]] = {g: [] for g in INSIGHT_GROUPS}
    ds = data_summary or {}
    metrics = ds.get("metrics") or {}
    groups = ds.get("groups") or {}

    # 1) Top 贡献度：某维度下最大分组占比偏高 → 集中度提示
    for dim, mapping in groups.items():
        if not (isinstance(mapping, dict) and mapping):
            continue
        nums = {k: v for k, v in mapping.items() if isinstance(v, (int, float))}
        total = sum(nums.values())
        if total <= 0:
            continue
        ranked = sorted(nums.items(), key=lambda kv: kv[1], reverse=True)
        top_key, top_val = ranked[0]
        share = top_val / total
        if share >= top_share_min:
            cr2 = sum(v for _, v in ranked[:2]) / total if len(ranked) >= 2 else share
            insights["top_contributor"].append({
                "dimension": dim, "top": top_key, "value": top_val,
                "share": round(share, 3), "cr2": round(cr2, 3),
                "source": "rule",
                "note": (f"{top_key} 占 {dim} 的 {share:.0%}（前二合计 {cr2:.0%}），"
                         f"集中度{'高' if cr2 >= cr2_min else '偏高'}，需关注单一依赖风险"),
            })

    # 2) 环比/同比突变（|Δ| ≥ delta_min 视为显著）
    for metric, st in metrics.items():
        if not isinstance(st, dict):
            continue
        mom, yoy = st.get("mom"), st.get("yoy")
        if isinstance(mom, (int, float)) and abs(mom) >= delta_min:
            insights["mom_yoy_delta"].append({
                "metric": metric, "type": "mom", "delta": mom, "source": "rule",
                "note": f"{metric} 环比{'上升' if mom > 0 else '下降'} {abs(mom):.0%}",
            })
        if isinstance(yoy, (int, float)) and abs(yoy) >= delta_min:
            insights["mom_yoy_delta"].append({
                "metric": metric, "type": "yoy", "delta": yoy, "source": "rule",
                "note": f"{metric} 同比{'上升' if yoy > 0 else '下降'} {abs(yoy):.0%}",
            })

    # 3) 阈值突破：指标 latest 超 playbook/基准
    benchmarks = dict((playbook or {}).get("benchmark", {}) if playbook else {})
    benchmarks.update(ds.get("benchmarks", {}) or {})
    for metric, bench in benchmarks.items():
        st = metrics.get(metric)
        if not isinstance(st, dict) or not isinstance(bench, (int, float)):
            continue
        val = st.get("latest")
        if isinstance(val, (int, float)) and val > bench:
            over = (val - bench) / abs(bench) if bench else None
            insights["threshold_breach"].append({
                "metric": metric, "value": val, "benchmark": bench,
                "over_ratio": round(over, 3) if isinstance(over, float) else None,
                "source": "rule",
                "note": (f"{metric} {_pct(val)} 突破基准 {_pct(bench)}"
                         + (f"，超出 {over:.0%}" if isinstance(over, float) else "")),
            })

    # 4) 离群值：max > mean + kσ
    for metric, st in (ds.get("raw_stats") or {}).items():
        if not isinstance(st, dict):
            continue
        mean, std, mx = st.get("mean"), st.get("std"), st.get("max")
        if not all(isinstance(x, (int, float)) for x in (mean, std, mx)) or std <= 0:
            continue
        if mx > mean + sigma_k * std:
            insights["outliers"].append({
                "metric": metric, "value": mx, "mean": mean, "std": std,
                "sigma_k": sigma_k, "source": "rule",
                "note": f"{metric} 最大值 {mx} 超均值+{sigma_k:g}σ，疑似离群，建议核查",
            })

    # 5) 归因（G2）：有 drill → 真实增量分解；无 drill → 结构 CR2 + 可验证假设
    insights["attribution"] = _build_attribution(ds, metrics, delta_min, cr2_min, max_cards)

    # 6) 趋势外推（G2）：序列≥min_points 走线性回归；否则朴素 mom，低置信
    insights["forecast"] = _build_forecast(ds, metrics, min_points, benchmarks, max_cards)

    # 7) 行动建议（G2）：由前六类事实卡推导，每条必带 evidence 引用，禁止臆造动作
    insights["recommendation"] = _build_recommendation(insights, max_cards)

    # 统一截断：单组卡片数量上限（防信息过载）
    for g in INSIGHT_GROUPS:
        insights[g] = insights[g][:max_cards]
    return insights


# ────────────────────────── G2：归因 ──────────────────────────

def _build_attribution(ds, metrics, delta_min, cr2_min, max_cards) -> List[Dict[str, Any]]:
    cards: List[Dict[str, Any]] = []
    drill = ds.get("drill") or {}
    groups = ds.get("groups") or {}

    for metric, st in metrics.items():
        if not isinstance(st, dict):
            continue
        moved = False
        for kind in ("mom", "yoy"):
            v = st.get(kind)
            if isinstance(v, (int, float)) and abs(v) >= delta_min:
                moved = True
                break
        if not moved:
            continue

        # A) 真实增量分解：drill 提供了各分组的 prev/curr
        node = drill.get(metric) if isinstance(drill, dict) else None
        if isinstance(node, dict) and node:
            for dim, keymap in node.items():
                if not isinstance(keymap, dict):
                    continue
                deltas = {}
                for key, pv in keymap.items():
                    if not isinstance(pv, dict):
                        continue
                    prev, curr = _f(pv.get("prev")), _f(pv.get("curr"))
                    if prev is None or curr is None:
                        continue
                    deltas[key] = curr - prev
                total_delta = sum(deltas.values())
                if not deltas or abs(total_delta) <= 0:
                    continue
                ranked = sorted(deltas.items(), key=lambda kv: abs(kv[1]), reverse=True)
                contribs = [(k, d, (d / total_delta if total_delta else 0.0)) for k, d in ranked]
                lead_key, _lead_delta, lead_share = contribs[0]
                cards.append({
                    "metric": metric, "dimension": dim, "method": "delta_decomposition",
                    "driver": lead_key,
                    "driver_share": round(lead_share, 3),
                    "total_delta": round(total_delta, 4),
                    "top_drivers": [
                        {"key": k, "delta": round(d, 4), "contribution": round(c, 3)}
                        for k, d, c in contribs[:3]
                    ],
                    "source": "rule",
                    "note": (f"{metric} 的变化中，{lead_key} 贡献 {lead_share:.0%}"
                             f"（按 {dim} 做增量分解），是主要驱动因子"),
                    "verify_by": f"下钻 {dim} 复核 {lead_key} 的明细口径与业务动作",
                })
            continue

        # B) 无 drill：结构性归因（当前占比）+ 待验证假设
        for dim, mapping in groups.items():
            if not (isinstance(mapping, dict) and mapping):
                continue
            nums = {k: v for k, v in mapping.items() if isinstance(v, (int, float))}
            total = sum(nums.values())
            if total <= 0:
                continue
            ranked = sorted(nums.items(), key=lambda kv: kv[1], reverse=True)
            cr2 = sum(v for _, v in ranked[:2]) / total if len(ranked) >= 2 else 1.0
            if cr2 < cr2_min:
                continue
            lead_key = ranked[0][0]
            cards.append({
                "metric": metric, "dimension": dim, "method": "structural_cr2",
                "driver": lead_key, "cr2": round(cr2, 3),
                "source": "rule",
                "note": (f"{metric} 发生变化，结构上由 {dim} 的 {lead_key} 等头部承载"
                         f"（前二合计 {cr2:.0%}）——结构性归因，待下钻验证"),
                "verify_by": f"补充 {dim} 维度的 prev/curr 明细后可做真实增量分解",
                "hypotheses": [
                    f"假设1：{lead_key} 的投放/放款节奏变化是主要贡献（用 {dim} 分组的时间序列验证）",
                    f"假设2：个别 {dim} 存在口径调整或数据补录（比对去年同期口径）",
                    f"假设3：头部集中度本身放大了波动（{cr2:.0%} 集中度下单体波动=整体波动）",
                ],
            })
    return cards[:max_cards]


# ────────────────────────── G2：趋势外推 ──────────────────────────

def _build_forecast(ds, metrics, min_points, benchmarks, max_cards) -> List[Dict[str, Any]]:
    cards: List[Dict[str, Any]] = []
    for metric, st in metrics.items():
        if not isinstance(st, dict):
            continue
        series = st.get("series")
        bench = benchmarks.get(metric)
        if isinstance(series, (list, tuple)) and len(series) >= min_points:
            pts = [_f(x) for x in series]
            pts = [p for p in pts if p is not None]
            if len(pts) >= min_points:
                n = len(pts)
                xs = list(range(n))
                mx_ = sum(xs) / n
                my_ = sum(pts) / n
                sxx = sum((x - mx_) ** 2 for x in xs)
                sxy = sum((x - mx_) * (y - my_) for x, y in zip(xs, pts))
                slope = sxy / sxx if sxx > 0 else 0.0
                intercept = my_ - slope * mx_
                nxt = intercept + slope * n
                last = pts[-1]
                growth = (nxt - last) / last if last else None
                # 拟合优度 R²（作为置信度依据，低 R² 明确提示不确定）
                ss_tot = sum((y - my_) ** 2 for y in pts)
                ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, pts))
                r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
                conf = "高" if r2 >= 0.8 else ("中" if r2 >= 0.5 else "低")
                note = (f"{metric} 按近 {n} 期线性趋势，下期约 {_pct(nxt)}"
                        + (f"({growth:+.0%})" if isinstance(growth, float) else "")
                        + f"；拟合度 R²={r2:.2f}（置信{conf}）")
                will_breach = isinstance(bench, (int, float)) and nxt > bench
                if will_breach:
                    note += f" ⚠ 预计突破基准 {_pct(bench)}"
                cards.append({
                    "metric": metric, "method": "linear_regression", "next": round(nxt, 4),
                    "growth": round(growth, 4) if isinstance(growth, float) else None,
                    "r2": round(r2, 3), "confidence": conf, "points": n,
                    "benchmark": bench if isinstance(bench, (int, float)) else None,
                    "will_breach": bool(will_breach),
                    "source": "rule", "note": note,
                    "verify_by": "下期实际值入库后回测误差，误差>20% 需改用季节性/移动平均模型",
                })
                continue
        # 朴素外推：仅有 mom 时用最新值×(1+mom)，明确低置信
        mom = st.get("mom")
        latest = _f(st.get("latest"))
        if isinstance(mom, (int, float)) and latest is not None:
            nxt = latest * (1 + mom)
            will_breach = isinstance(bench, (int, float)) and nxt > bench
            cards.append({
                "metric": metric, "method": "naive_mom", "next": round(nxt, 4),
                "growth": round(mom, 4), "confidence": "低",
                "benchmark": bench if isinstance(bench, (int, float)) else None,
                "will_breach": bool(will_breach), "source": "rule",
                "note": (f"{metric} 按当前环比 {mom:+.0%} 朴素外推，下期约 {_pct(nxt)}"
                         f"（单点推断，置信低，仅供参考）"),
                "verify_by": "补充不少于 3 期序列后可切换线性趋势模型",
            })
    return cards[:max_cards]


# ────────────────────────── G2：行动建议 ──────────────────────────

def _build_recommendation(insights: Dict[str, List[Dict[str, Any]]], max_cards) -> List[Dict[str, Any]]:
    recs: List[Dict[str, Any]] = []

    for c in insights.get("threshold_breach", []):
        recs.append({
            "priority": "高", "action": f"立即核查 {c['metric']} 超基准原因：拆分时间/业务维度定位责任主体",
            "why": c["note"], "evidence": [f"threshold_breach:{c['metric']}"], "source": "rule",
        })

    for c in insights.get("mom_yoy_delta", []):
        if c.get("delta") is not None and c["delta"] < 0:
            recs.append({
                "priority": "高" if abs(c["delta"]) >= 0.3 else "中",
                "action": f"定位 {c['metric']} {c['type'].upper()} 下降 {abs(c['delta']):.0%} 的驱动因子，形成止血动作",
                "why": c["note"], "evidence": [f"mom_yoy_delta:{c['metric']}:{c['type']}"], "source": "rule",
            })

    for c in insights.get("attribution", []):
        recs.append({
            "priority": "中",
            "action": f"验证归因结论：{c.get('verify_by') or '下钻复核驱动因子'}",
            "why": c["note"], "evidence": [f"attribution:{c.get('metric')}:{c.get('dimension')}"], "source": "rule",
        })

    for c in insights.get("top_contributor", []):
        recs.append({
            "priority": "中",
            "action": f"集中度风险：下钻 {c['dimension']} 复核 {c['top']} 的口径与单一依赖应急预案",
            "why": c["note"], "evidence": [f"top_contributor:{c['dimension']}"], "source": "rule",
        })

    for c in insights.get("forecast", []):
        if c.get("will_breach"):
            recs.append({
                "priority": "高",
                "action": f"提前介入：{c['metric']} 按趋势下期将突破基准 {_pct(c['benchmark'])}，需在本期启动压降",
                "why": c["note"], "evidence": [f"forecast:{c['metric']}"], "source": "rule",
            })
        elif c.get("confidence") == "低":
            recs.append({
                "priority": "低",
                "action": f"数据补齐：为 {c['metric']} 建立不少于 3 期的稳定序列，提升预测可用度",
                "why": c["note"], "evidence": [f"forecast:{c['metric']}"], "source": "rule",
            })

    for c in insights.get("outliers", []):
        recs.append({
            "priority": "中",
            "action": f"核查 {c['metric']} 极值样本是否为录入错误/口径异常，必要时单独标注",
            "why": c["note"], "evidence": [f"outliers:{c['metric']}"], "source": "rule",
        })

    if not recs:
        recs.append({
            "priority": "低", "action": "本轮无显著异常，维持例行监控；建议按周复核基准适用性",
            "why": "七类事实卡均无命中", "evidence": [], "source": "rule",
        })
    return recs[:max_cards]
