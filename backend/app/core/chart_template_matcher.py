# -*- coding: utf-8 -*-
"""
P2 图表模板种子校正 —— 字段双通道匹配 + 匹配报告。

旧行为（P2 痛点）：`chart_template_seed.py` 预置模板的字段名是硬编码中文
（"担保余额"/"区域"/"月份"），而真实数据集字段多为英文/拼音（guarantee_balance/
region/month）。`apply_template` 走 executor 严格匹配，命不中 → 大量跳过或子串
错配出错误图，用户看到的就是"数据/图都不对"。

本模块提供与 apply 流程解耦、可单测的匹配器：
- `infer_role(name, ftype)`：从字段名/类型推断语义角色（measure/time/category）；
- `match_template_charts(specs, dataset_fields)`：对每张图做
   ① 字段名精确匹配 → ② 语义角色匹配（带歧义风险标记）→ ③ 无匹配跳过；
  返回逐图状态 + 汇总报告（命中/角色命中/跳过/错配风险），供前端展示"匹配报告"
  并让用户确认后再落图，杜绝静默错配。
"""
from __future__ import annotations

from typing import Dict, Any, List, Optional, Tuple

# 语义角色关键词（中英文混排，大小写/空白不敏感）
ROLE_HINTS: Dict[str, List[str]] = {
    "time": ["date", "time", "month", "year", "day", "quarter", "week",
             "日期", "时间", "月份", "年月", "年", "季度", "日", "月"],
    "category": ["type", "channel", "region", "area", "category", "cate", "dept",
                 "部门", "区域", "地区", "类型", "渠道", "产品", "等级", "状态",
                 "供应商", "品类", "职级", "客户类型", "审批状态", "产品类型"],
    "measure": ["amount", "balance", "count", "num", "number", "qty", "sum", "total",
                "avg", "金额", "余额", "数量", "总数", "总额", "销售额", "采购额",
                "人数", "客户数", "订单量", "交易额", "放款", "担保余额", "收入", "成本"],
}


def infer_role(name: str, ftype: Optional[str] = None) -> str:
    """从字段名 + 类型推断语义角色。"""
    if not name:
        return "category"
    ln = str(name).strip().lower()
    for role, kws in ROLE_HINTS.items():
        if any(k in ln for k in kws):
            return role
    ft = str(ftype or "").lower()
    if ft in ("int", "float", "number", "decimal", "double"):
        return "measure"
    if ft in ("date", "datetime", "timestamp"):
        return "time"
    return "category"


def _norm(s: str) -> str:
    return str(s).strip().lower()


def _find_field(
    target: Optional[str],
    fields: List[Dict[str, Any]],
    preferred_role: str,
) -> Tuple[Optional[Dict[str, Any]], str]:
    """双通道匹配单个目标字段。

    返回 (命中字段 or None, 状态)。状态：
      - "matched_name"    ：字段名精确（归一化）匹配
      - "matched_role"    ：名称不中，但按语义角色唯一命中（最佳努力，可能非用户本意）
      - "mismatch_risk"   ：名称不中，且按角色命中多个（歧义，需人工确认）
      - "none"            ：无任何匹配 → 跳过
    """
    if not target:
        return None, "na"
    ln = _norm(target)
    # 通道①：名称精确匹配
    name_hits = [f for f in fields if _norm(f.get("name", "")) == ln]
    if name_hits:
        return name_hits[0], "matched_name"
    # 通道②：语义角色匹配
    role_hits = [f for f in fields if f.get("role") == preferred_role]
    if len(role_hits) == 1:
        return role_hits[0], "matched_role"
    if len(role_hits) >= 2:
        # 歧义：优先选名称包含目标关键字的；否则标风险
        sub = [f for f in role_hits if ln and ln in _norm(f.get("name", ""))]
        if len(sub) == 1:
            return sub[0], "matched_role"
        return role_hits[0], "mismatch_risk"
    return None, "none"


def _dim_role(chart_type: str) -> str:
    return "time" if chart_type in ("line", "area") else "category"


def match_template_charts(
    specs: List[Dict[str, Any]],
    dataset_fields: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """对一组图表规格做模板→数据集字段匹配，产出匹配报告。

    dataset_fields: [{name, type?, role?}]；若缺 role 则自动推断。
    """
    fields = []
    for f in dataset_fields:
        role = f.get("role") or infer_role(f.get("name", ""), f.get("type"))
        fields.append({"name": f.get("name"), "type": f.get("type"), "role": role})

    chart_reports = []
    counters = {"matched_name": 0, "matched_role": 0, "mismatch_risk": 0, "skipped": 0}
    for spec in specs:
        ct = spec.get("chart_type", "bar")
        metric_target = spec.get("metric_field")
        dim_target = spec.get("dimension_field")
        m_field, m_status = _find_field(metric_target, fields, "measure")
        d_field, d_status = _find_field(dim_target, fields, _dim_role(ct))

        # 整体状态取较差者（"na" 表示该项本就不需要，不参与比较）
        order = {"matched_name": 0, "matched_role": 1, "mismatch_risk": 2, "none": 3, "na": 9}
        real = [s for s in (m_status, d_status) if s != "na"]
        overall = sorted(real, key=lambda s: order[s])[-1] if real else "matched_name"
        if overall == "none":
            counters["skipped"] = counters.get("skipped", 0) + 1
        else:
            counters[overall] = counters.get(overall, 0) + 1

        risks = []
        if m_status == "mismatch_risk":
            risks.append(f"指标字段「{metric_target}」按角色命中多个，可能错配")
        if d_status == "mismatch_risk":
            risks.append(f"维度字段「{dim_target}」按角色命中多个，可能错配")
        if overall == "none":
            miss = [t for t, st in ((metric_target, m_status), (dim_target, d_status)) if st == "none"]
            risks.append(f"无匹配字段：{', '.join([m for m in miss if m])}")

        chart_reports.append({
            "title": spec.get("title", ""),
            "chart_type": ct,
            "metric_field": metric_target,
            "metric_matched": m_field["name"] if m_field else None,
            "metric_status": m_status,
            "dimension_field": dim_target,
            "dimension_matched": d_field["name"] if d_field else None,
            "dimension_status": d_status,
            "overall": overall,
            "risks": risks,
        })

    total = len(specs)
    applied_est = counters["matched_name"] + counters["matched_role"]
    return {
        "total": total,
        "matched_name": counters["matched_name"],
        "matched_role": counters["matched_role"],
        "mismatch_risk": counters["mismatch_risk"],
        "skipped": counters["skipped"],
        "applied_estimate": applied_est,
        "safe_to_apply": counters["mismatch_risk"] == 0 and counters["skipped"] == 0,
        "charts": chart_reports,
    }
