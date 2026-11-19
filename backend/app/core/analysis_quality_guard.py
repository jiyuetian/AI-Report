# -*- coding: utf-8 -*-
"""分析质量通用闸门（#44-#47，取证于 2026-11-17 v2_03 业务月度总览表审计）。

背景：该看板在 AI 全链缺席（7897 代理未开）时由规则兜底生成，暴露四类通用短板：
  G2/#44 存量指标（累计/余额/期末）被跨期 sum 成 2511 亿，业务无意义；
  G3/#45 S2 模板目标点名不存在的字段（逾期天数/地区/不良率/放款金额/借据类型）；
  G4/#46 兜底叙事是套话，事实闸门 numbers.checked=0 仍报「一致通过」；
  G5/#47 全链规则兜底与 AI 全链版同分同绿，违背「兜底只是地基」设计真意。

本模块提供与数据集无关的通用纯函数（零 LLM / 零网络 / 零写库），任何链路可复用：
  semantic_aggregation(field, role)  -> 聚合口径判定（存量禁 sum）
  filter_hallucinated_goals(goals, fields) -> 目标字段存在性闸门
  check_information_density(text, pack) -> 叙事最低信息量闸门
  apply_delivery_policy(passed, result_kind, info_ok) -> 交付分级（地基版 vs AI 全链版）

设计原则：只输出「事实 + 建议 + 分级」，不擅自改写用户可见文案；调用方异常一律可降级，
绝不阻断主链路。所有判定基于字段字面与真实事实包，不臆造数据。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# ── #44 存量口径 ──────────────────────────────────────────────────────────
# 存量/时点类：跨期相加没有业务意义（12 月 × 4 类型把时点余额累加成 2511 亿）
_STOCK_KEYWORDS = (
    "累计", "余额", "存量", "期末", "结余", "库存", "结存", "账面", "在保", "在贷",
    "cumulative", "balance", "stock", "ending", "outstanding", "closing",
)
# 流量/期间发生额：可以 sum
_FLOW_KEYWORDS = (
    "发生额", "新增", "流入", "流出", "收入", "支出", "放款额", "回收额", "核销额",
    "flow", "inflow", "outflow", "new_", "increment",
)
# 比率/占比：一律 avg，禁止 sum
_RATE_KEYWORDS = ("率", "占比", "比例", "percent", "ratio", "rate", "pct")


def _kw_hit(name: str, keywords: Tuple[str, ...]) -> bool:
    low = str(name or "").lower()
    return any(k in low for k in keywords)


def semantic_aggregation(field_name: str, role: Optional[str] = None) -> Dict[str, Any]:
    """按字段语义判定安全聚合口径（#44 通用能力）。

    返回 dict：
      aggregation   : 建议算子（sum / avg）
      basis         : 判定依据（白盒）
      must_not_sum  : 是否禁止跨期 sum
      title_prefix  : 建议标题前缀（避免「总累计担保总额」误导）
    """
    low = str(field_name or "").lower()
    # 比率优先（如「逾期率」即使含"累计"也按比率处理）
    if _kw_hit(low, _RATE_KEYWORDS) or role == "rate":
        return {"aggregation": "avg", "basis": "比率/占比类按均值，禁止求和",
                "must_not_sum": True, "title_prefix": "平均"}
    # 存量/时点类：禁止 sum
    if _kw_hit(low, _STOCK_KEYWORDS):
        return {"aggregation": "avg", "basis": "存量/时点类字段跨期相加无业务意义，取期间均值",
                "must_not_sum": True, "title_prefix": "平均"}
    # 流量类：可 sum
    if _kw_hit(low, _FLOW_KEYWORDS):
        return {"aggregation": "sum", "basis": "期间发生额/流量类可汇总",
                "must_not_sum": False, "title_prefix": "总"}
    # 回退到既有语义角色（amount/count→sum，duration/rate/age→avg）
    if role in ("duration", "rate", "age"):
        return {"aggregation": "avg", "basis": "语义角色 %s 按均值" % role,
                "must_not_sum": True, "title_prefix": "平均"}
    if role in ("amount", "count"):
        return {"aggregation": "sum", "basis": "语义角色 %s 按求和" % role,
                "must_not_sum": False, "title_prefix": "总"}
    return {"aggregation": "sum", "basis": "未识别语义，沿用默认求和",
            "must_not_sum": False, "title_prefix": "总"}


# ── #45 目标字段存在性闸门 ───────────────────────────────────────────────
# 通用分析词：这些词本身不是"点名字段"，不要求在数据里出现
_GENERIC_TOKENS = (
    "趋势", "分析", "监控", "对比", "分布", "预警", "识别", "占比", "结构", "变化",
    "情况", "水平", "风险", "总体", "整体", "重点", "客户", "产品", "业务", "月度",
    "关联", "画像", "排名", "矩阵", "热力", "交叉", "复盘", "归因", "建议", "辅助",
    "决策", "及时", "发现", "掌握", "了解", "追踪", "评估", "优化", "指导", "配置",
    "采取", "防范", "优先", "关注", "各类", "不同", "之间", "演变", "构成", "集中",
)


def _candidate_objects(title: str) -> List[str]:
    """从目标标题提取具体业务对象词：剔除通用分析词后剩余的 2-8 字中文短语。"""
    text = str(title or "")
    for g in sorted(_GENERIC_TOKENS, key=len, reverse=True):
        text = text.replace(g, " ")
    return [w for w in re.findall(r"[\u4e00-\u9fff]{2,8}", text)]


def _object_anchored(obj: str, fields: List[str]) -> bool:
    """具体对象词必须作为完整子串出现在某真实字段名中（不做 2-gram 泛化匹配）。"""
    if not obj:
        return True
    low = str(obj).lower()
    return any(low in str(f).lower() or str(f).lower() in low
               for f in (fields or []) if str(f).strip())


def filter_hallucinated_goals(goals: List[Dict[str, Any]],
                              fields: List[str]) -> Dict[str, Any]:
    """目标字段存在性闸门（#45 通用能力）。

    判定：目标标题点名的具体业务对象（如「逾期天数」「借据类型」）必须在真实字段
    集合里有完整字面锚点；纯泛化目标（如「整体风险趋势」）不误删；字段集合为空时
    保守放行（交由上游/AI 判定，不臆断）。返回 kept / dropped / 判定依据。
    """
    kept: List[Dict[str, Any]] = []
    dropped: List[Dict[str, Any]] = []
    flds = [str(f) for f in (fields or []) if str(f).strip()]
    for g in (goals or []):
        if not isinstance(g, dict):
            continue
        title = str(g.get("title") or "")
        objects = _candidate_objects(title)
        if not objects or not flds:
            kept.append(g)
            continue
        unanchored = [o for o in objects if not _object_anchored(o, flds)]
        if unanchored:
            dropped.append({
                "goal_id": g.get("goal_id"), "title": title,
                "unanchored_objects": unanchored[:6],
                "reason": "目标点名对象 %s 在真实字段中无完整字面锚点，判为幻觉目标并丢弃"
                          % "、".join(unanchored[:3]),
            })
        else:
            kept.append(g)
    return {"kept": kept, "dropped": dropped,
            "field_count": len(flds),
            "passed": not dropped}


# ── #46 叙事最低信息量闸门 ───────────────────────────────────────────────
_TREND_WORDS = (
    "上升", "下降", "攀升", "下滑", "增长", "减少", "走高", "走低", "反弹", "波动",
    "峰值", "谷值", "最高", "最低", "逐月", "持续", "连续", "高于", "低于", "均值",
    "中位数", "持平", "恶化", "改善", "扩大", "收窄",
)


def check_information_density(text: str, pack: Dict[str, Any],
                              min_numbers: int = 3, min_signals: int = 1) -> Dict[str, Any]:
    """叙事最低信息量闸门（#46 通用能力）。

    套话（无真实数值、无字段名、无趋势判断）不得通过事实校验。与 check_numbers 独立，
    不改动既有 guard_narrative 的通过语义（避免破坏已全绿的回归断言）。
    """
    pack = pack or {}
    columns = pack.get("columns") or {}
    body = str(text or "")
    # 真实数值：直接复用事实包允许值，逐个核对叙事里出现的小数
    allowed = [float(v) for v in (pack.get("allowed_numbers") or [])]
    nums = [float(x) for x in re.findall(r"(?<![\d.])(0\.\d{3,}|\d+\.\d{3,})(?![\d])", body)]
    matched = []
    for v in nums:
        if any(abs(v - a) <= 5e-5 for a in allowed):
            matched.append(v)
    matched_unique = sorted(set(matched))
    field_refs = [c for c in columns if c and c in body]
    trend_hits = [w for w in _TREND_WORDS if w in body]
    signals = len(field_refs) + len(trend_hits)
    passed = (len(matched_unique) >= min_numbers and signals >= min_signals)
    return {
        "passed": passed,
        "numbers_found": len(nums),
        "numbers_matched": len(matched_unique),
        "matched_values": matched_unique[:12],
        "field_refs": field_refs[:12],
        "trend_hits": trend_hits[:12],
        "signal_count": signals,
        "min_numbers": min_numbers,
        "min_signals": min_signals,
        "reason": ("叙事含 %d 个真实数值 + %d 个字段/趋势信号，信息量合格"
                   % (len(matched_unique), signals)) if passed else
                  ("叙事信息量不足：真实数值 %d<%d，字段/趋势信号 %d<%d（套话不得作为分析结论）"
                   % (len(matched_unique), min_numbers, signals, min_signals)),
    }


# ── #47 交付分级（地基版 vs AI 全链版） ─────────────────────────────────
RUN_KIND_AI = "ai_confirmed_full"
RUN_KIND_RULE = "user_confirmed_rule"


def apply_delivery_policy(passed: bool, result_kind: str,
                          info_density_ok: bool = True,
                          hallucinated_goals: int = 0) -> Dict[str, Any]:
    """交付分级（#47 通用能力）：全链兜底不得与 AI 全链版同分同绿。

    不篡改用户确认后的评分布尔值（保持可展示），但白盒输出 delivery_tier / quality_flags /
    score_label，供落库与前端区分「AI 全链确认成果」与「规则地基版」。
    """
    ai_full = (result_kind == RUN_KIND_AI)
    flags: List[str] = []
    if not ai_full:
        flags.append("全链规则兜底（非 AI 完整交付）")
    if not info_density_ok:
        flags.append("叙事信息量不足")
    if hallucinated_goals > 0:
        flags.append("存在 %d 个幻觉目标" % hallucinated_goals)
    if ai_full and not flags:
        tier, label = "ai_full", "AI 全链确认"
    elif ai_full and flags:
        tier, label = "ai_full_guarded", "AI 全链确认（带护栏提示）"
    else:
        tier, label = "rule_floor", "规则地基版（未达 AI 完整交付水准）"
    return {
        "delivery_tier": tier,
        "score_label": label,
        "quality_flags": flags,
        "is_ai_full": ai_full,
        "passed": bool(passed),  # 不篡改评分布尔，保留用户确认后的可展示性
        "distinct_from_ai": tier != "ai_full",
    }


__all__ = [
    "semantic_aggregation", "filter_hallucinated_goals", "check_information_density",
    "apply_delivery_policy", "RUN_KIND_AI", "RUN_KIND_RULE",
]
