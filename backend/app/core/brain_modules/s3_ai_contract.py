"""AI 主执行契约 · 白盒护栏 + 每一步原因日志（A2 · 对应需求 2 & 4）。

设计意图（见《白盒规则说明》§3 / §5）：
- AI（在线）是每一步的【主执行者】，在「框架内」自由生成步骤产物；
- 规则不是主链路，而是【护栏】：对 AI 产物做白盒校验（R1-R9 子集），
  不合规则给出明确原因，并在框架内【自修】（drop 非法 / 纠正聚合口径 / 补必看指标占位）；
- 每一步都产出【可查的处理方案与原因】（contract_report.reasons），供血缘追溯（需求 4）。

本模块为纯函数，不依赖 LLM / DuckDB，可离线单测：
  run_contract(charts, ctx) -> {charts, passed, violations, repairs, reasons}
ctx 由 build_framework_ctx 构造（domain/field_profiles/derived_metrics/grain/playbook）。
"""
from typing import Any, Dict, List, Optional

# 允许的图表类型（与 s3_llm_enhancer.CHART_CONFIG_SCHEMA 对齐）
ALLOWED_CHART_TYPES = ["kpi", "line", "bar", "pie", "scatter", "table", "map", "heatmap"]

# 各图表类型的字段角色要求（白盒 R1）
_ROLE_REQUIREMENTS = {
    "kpi": {"needs_value": True, "needs_dim": False, "needs_x": False, "needs_two_numeric": False},
    "line": {"needs_value": True, "needs_dim": False, "needs_x": True, "needs_two_numeric": False},
    "bar": {"needs_value": True, "needs_dim": True, "needs_x": False, "needs_two_numeric": False},
    "pie": {"needs_value": True, "needs_dim": True, "needs_x": False, "needs_two_numeric": False},
    "scatter": {"needs_value": False, "needs_dim": False, "needs_x": False, "needs_two_numeric": True},
    "table": {"needs_value": False, "needs_dim": False, "needs_x": False, "needs_two_numeric": False},
    "map": {"needs_value": True, "needs_dim": True, "needs_x": False, "needs_two_numeric": False},
    "heatmap": {"needs_value": True, "needs_dim": True, "needs_x": False, "needs_two_numeric": False},
}

# 宏观粒度禁止（白盒 R5）
_MACRO_FORBIDDEN = {"scatter", "heatmap", "map"}


def build_framework_ctx(
    domain: str,
    field_profiles: Optional[List[Dict[str, Any]]] = None,
    derived_metrics: Optional[Dict[str, Any]] = None,
    grain: str = "detail",
    available_fields: Optional[List[str]] = None,
    goals: Optional[List[Dict[str, Any]]] = None,
    playbook: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """构造 AI 主执行契约所需的「框架上下文」。

    白盒、可解释：仅聚合字段画像/派生指标/粒度/领域 playbook，不触碰 LLM/DB。
    """
    # 字段画像索引（name -> profile）
    profile_index: Dict[str, Dict[str, Any]] = {}
    for fp in field_profiles or []:
        if not isinstance(fp, dict):
            continue
        nm = fp.get("name") or fp.get("column")
        if nm:
            profile_index[str(nm)] = fp
    # available_fields 兜底
    if available_fields is None:
        available_fields = list(profile_index.keys())
    # 派生指标：比率字段集合（用于 R4 防 sum）
    ratio_fields = set()
    if derived_metrics:
        for m_name, info in derived_metrics.items():
            if isinstance(info, dict):
                try:
                    from app.core.derived_metric_service import is_ratio_metric  # 软依赖
                    if is_ratio_metric(info):
                        ratio_fields.add(m_name)
                except Exception:
                    # 无服务时按名称启发式（含"率/占比/比例"）
                    if any(k in str(m_name) for k in ("率", "占比", "比例")):
                        ratio_fields.add(m_name)
    # playbook 必看指标（R2 信息级）
    must_have = []
    if playbook and isinstance(playbook.get("must_have_metrics"), list):
        must_have = [m.get("name") for m in playbook["must_have_metrics"] if isinstance(m, dict) and m.get("name")]
    return {
        "domain": domain,
        "profile_index": profile_index,
        "available_fields": list(available_fields),
        "ratio_fields": ratio_fields,
        "grain": grain,
        "goals": goals or [],
        "playbook_must_have": must_have,
    }


def _field_role(name: Optional[str], ctx: Dict[str, Any]) -> str:
    """推断字段角色：dimension（分类）/ measure（数值度量）/ unknown。"""
    if not name:
        return "none"
    prof = ctx["profile_index"].get(name)
    if prof:
        t = str(prof.get("type") or prof.get("dtype") or "").lower()
        role = str(prof.get("business_role") or prof.get("role") or "").lower()
        if role in ("dimension", "category", "dim") or t in ("category", "string", "geo", "date"):
            return "dimension"
        if role in ("measure", "metric", "indicator") or t in ("number", "numeric", "float", "int"):
            return "measure"
        # 无明确角色：按高基数/取值判断
        card = prof.get("cardinality") or prof.get("distinct_count")
        if isinstance(card, int) and card > 20:
            return "measure"
        return "dimension"
    # 无画像：保守判 dimension（避免误杀）
    return "dimension"


def _numeric(name: Optional[str], ctx: Dict[str, Any]) -> bool:
    return _field_role(name, ctx) == "measure"


def validate_charts(charts: List[Dict[str, Any]], ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """白盒校验 AI/规则产物，返回违规清单。

    每条违规：{chart_index, rule, severity('error'|'warn'), message, fixable}
    - error：结构/角色硬错，可自修（drop 或纠正）
    - warn：信息级（如缺领域必看指标），不阻断、仅上报告知
    """
    violations: List[Dict[str, Any]] = []
    avail = set(ctx.get("available_fields", []))
    grain = ctx.get("grain", "detail")

    for i, ch in enumerate(charts):
        if not isinstance(ch, dict):
            violations.append({"chart_index": i, "rule": "R3", "severity": "error",
                               "message": "图表配置非字典", "fixable": True})
            continue
        ctype = ch.get("chart_type")
        title = ch.get("title", f"图{i+1}")

        # R3 结构：类型合法 + 标题非空
        if ctype not in ALLOWED_CHART_TYPES:
            violations.append({"chart_index": i, "rule": "R3", "severity": "error",
                               "message": f"非法图表类型 '{ctype}'", "fixable": True})
            continue
        if not str(ch.get("title", "")).strip():
            violations.append({"chart_index": i, "rule": "R3", "severity": "warn",
                               "message": "标题为空", "fixable": True})

        req = _ROLE_REQUIREMENTS.get(ctype, {})

        # 字段存在性（白盒 R1 边界）：所有引用字段须在可用字段内
        for key in ("x_field", "y_field", "category_field", "value_field"):
            f = ch.get(key)
            if f and f not in avail:
                violations.append({"chart_index": i, "rule": "R1", "severity": "error",
                                   "message": f"字段 '{f}' 不在数据集中", "fixable": False})

        # R1 角色要求
        if req.get("needs_value"):
            vf = ch.get("value_field") or ch.get("y_field")
            if not vf:
                violations.append({"chart_index": i, "rule": "R1", "severity": "error",
                                   "message": f"{ctype} 缺少度量字段(value/y)", "fixable": True})
            elif not _numeric(vf, ctx):
                violations.append({"chart_index": i, "rule": "R1", "severity": "warn",
                                   "message": f"{ctype} 的度量字段 '{vf}' 非数值", "fixable": False})
        if req.get("needs_dim"):
            dim = ch.get("category_field") or ch.get("x_field")
            if not dim:
                violations.append({"chart_index": i, "rule": "R1", "severity": "error",
                                   "message": f"{ctype} 缺少维度字段(category/x)", "fixable": True})
            elif _field_role(dim, ctx) != "dimension":
                violations.append({"chart_index": i, "rule": "R1", "severity": "warn",
                                   "message": f"{ctype} 的维度字段 '{dim}' 非分类", "fixable": False})
        if req.get("needs_x"):
            xf = ch.get("x_field")
            if not xf:
                violations.append({"chart_index": i, "rule": "R1", "severity": "error",
                                   "message": f"{ctype} 缺少横轴字段(x)", "fixable": True})
        if req.get("needs_two_numeric"):
            xf, yf = ch.get("x_field"), ch.get("y_field")
            if not (xf and yf and _numeric(xf, ctx) and _numeric(yf, ctx)):
                violations.append({"chart_index": i, "rule": "R1", "severity": "error",
                                   "message": f"{ctype} 需两个数值轴(x/y 都为度量)", "fixable": True})

        # R4 比率字段禁 sum/count
        metric = ch.get("y_field") or ch.get("value_field")
        if metric and metric in ctx.get("ratio_fields", set()):
            agg = str(ch.get("aggregate") or ch.get("aggregation") or
                      (ch.get("config") or {}).get("aggregate") or
                      (ch.get("config") or {}).get("aggregation") or "").lower()
            if agg in ("sum", "count"):
                violations.append({"chart_index": i, "rule": "R4", "severity": "error",
                                   "message": f"比率指标 '{metric}' 被写成 {agg}，应 avg", "fixable": True})

        # R5 粒度
        if grain == "macro" and ctype in _MACRO_FORBIDDEN:
            violations.append({"chart_index": i, "rule": "R5", "severity": "error",
                               "message": f"宏观粒度禁止 {ctype}", "fixable": True})

    # R2 信息级：领域必看指标是否被任何图覆盖
    must_have = ctx.get("playbook_must_have") or []
    covered = set()
    for ch in charts:
        if isinstance(ch, dict):
            covered.update({ch.get("y_field"), ch.get("value_field"), ch.get("category_field")})
    for m in must_have:
        if m and m not in covered:
            violations.append({"chart_index": -1, "rule": "R2", "severity": "warn",
                               "message": f"领域必看指标 '{m}' 未被任何图覆盖", "fixable": False})
    return violations


def self_repair(
    charts: List[Dict[str, Any]], violations: List[Dict[str, Any]], ctx: Dict[str, Any]
) -> tuple[List[Dict[str, Any]], List[str]]:
    """在框架内自修：drop 非法类型/缺关键字段的图、纠正比率 sum→avg。

    返回 (修复后图表, 修复理由列表)。非 fixable 的违规（如字段不存在）不在此硬删，交由上层告知。
    """
    repair_reasons: List[str] = []
    # 收集需删除的 index 与需纠正 ratio 的 index
    drop_idx = set()
    ratio_fix_idx = set()
    for v in violations:
        if v.get("severity") != "error":
            continue
        idx = v.get("chart_index")
        if idx is None or idx < 0:
            continue
        rule = v.get("rule")
        if rule in ("R3", "R1", "R5") and v.get("fixable"):
            # 非法类型 / 缺关键字段 / 宏观禁用 → 删除该图
            drop_idx.add(idx)
        elif rule == "R4" and v.get("fixable"):
            ratio_fix_idx.add(idx)

    repaired = []
    for i, ch in enumerate(charts):
        if i in drop_idx:
            repair_reasons.append(f"删除图{i+1}({ch.get('title','')}): 违反白盒护栏(类型/字段/粒度)，不可在框架内修复")
            continue
        ch = dict(ch)  # 浅拷贝，避免改到原对象
        if i in ratio_fix_idx:
            ch["aggregate"] = "avg"
            ch.pop("aggregation", None)
            cfg = ch.get("config")
            if isinstance(cfg, dict):
                cfg["aggregate"] = "avg"
                cfg["aggregation"] = "avg"
            repair_reasons.append(f"纠正图{i+1}({ch.get('title','')}): 比率指标聚合口径 sum→avg")
        repaired.append(ch)
    return repaired, repair_reasons


def run_contract(
    charts: List[Dict[str, Any]], ctx: Dict[str, Any]
) -> Dict[str, Any]:
    """AI 主执行契约入口：校验 → 自修 → 产出原因日志。

    纯增量、对主链路零侵入：调用方把生成的 charts 丢进来，
    拿回（可能已自修的）charts + 可追溯的 reasons。
    """
    violations = validate_charts(charts, ctx)
    errors = [v for v in violations if v.get("severity") == "error"]
    repaired, repair_reasons = self_repair(charts, violations, ctx)

    # 原因日志（需求 4：每步处理方案与原因可查）
    reasons: List[Dict[str, Any]] = []
    # 校验发现
    for v in violations:
        reasons.append({
            "step": "S3-AI契约校验",
            "chart_index": v.get("chart_index"),
            "rule": v.get("rule"),
            "severity": v.get("severity"),
            "decision": "自修" if (v.get("severity") == "error" and v.get("fixable") and v.get("chart_index", -1) >= 0) else "上报",
            "detail": v.get("message"),
        })
    # 自修动作
    for r in repair_reasons:
        reasons.append({"step": "S3-AI契约自修", "chart_index": None, "rule": None,
                        "severity": "info", "decision": "修复", "detail": r})

    # 步骤总览原因（需求 4：每步处理方案与原因可查，即使全通过也要有审计留痕）
    if errors:
        reasons.insert(0, {"step": "S3-AI契约总览", "chart_index": None, "rule": None,
                           "severity": "warn", "decision": "拦截并自修",
                           "detail": f"校验发现 {len(errors)} 处硬违规，已自修 {len(repair_reasons)} 处"})
    else:
        reasons.insert(0, {"step": "S3-AI契约总览", "chart_index": None, "rule": None,
                           "severity": "info", "decision": "放行",
                           "detail": f"校验通过：{len(repaired)} 张图均符合白盒护栏(R1-R5)，无需修复"})

    return {
        "charts": repaired,
        "passed": len(errors) == 0,
        "violation_count": len(violations),
        "error_count": len(errors),
        "repair_count": len(repair_reasons),
        "violations": violations,
        "reasons": reasons,
    }
