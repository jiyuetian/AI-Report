"""每步结构化推理日志（C1：O10-1/O10-2/O10-3，对应改造方案 §7.2）。

纯函数，不依赖 LLM / DuckDB / 数据库会话，可离线单测。

职责：
- build_step_reasoning：把单个 S1-S5 阶段的「决策 + 原因 + 规则 + 兜底」收敛成
  一条结构化推理记录（改造方案 §7.2 规定的字段）。
- contract_reasons_to_log：把 S3 AI 主执行契约(run_contract)产出的 reasons 规整成
  同构的推理记录，便于与每步日志统一存储与查询。
- extract_self_corrections：从契约 reasons 中抽取「AI 原想 X，规则改成 Y」自纠事件
  （O10-3 飞轮强信号），供经验库反向优化 prompt。
- merge_reasoning：把追加的推理片段合并进已落库的 reasoning 列表（S3 契约在
  complete_stage 之后才产出，需要 append 而非覆盖）。
"""
from typing import Any, Dict, List, Optional


# 推理记录必备字段（改造方案 §7.2）
REASONING_FIELDS = (
    "step",            # 阶段标识：S1..S5 或 "S3-AI契约校验" 等子步骤
    "input_summary",   # 本步输入摘要
    "ai_decision",     # AI/规则 的处置决定
    "ai_reason",       # 决定的依据/原因
    "rules_applied",   # 应用到的白盒规则列表
    "fallback_used",   # 是否触发兜底
    "output_ref",      # 输出指代（如图表数/主题/评分），便于回溯
)


def build_step_reasoning(
    stage: str,
    *,
    input_summary: Optional[str] = None,
    ai_decision: Optional[str] = None,
    ai_reason: Optional[str] = None,
    rules_applied: Optional[List[str]] = None,
    fallback_used: bool = False,
    output_ref: Optional[Any] = None,
) -> Dict[str, Any]:
    """构造一条结构化推理记录（O10-1 单步日志）。

    字段与《改造方案》§7.2 对齐：step / input_summary / ai_decision / ai_reason /
    rules_applied / fallback_used / output_ref。
    """
    return {
        "step": stage,
        "input_summary": input_summary,
        "ai_decision": ai_decision,
        "ai_reason": ai_reason,
        "rules_applied": list(rules_applied or []),
        "fallback_used": bool(fallback_used),
        "output_ref": output_ref,
    }


def contract_reasons_to_log(reasons: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """把 S3 契约护栏 reasons 规整成推理记录列表（O10-2 三级留痕之一）。

    run_contract 的每条 reason 形如：
      {step, chart_index, rule, severity, decision, detail}
    其中 decision ∈ {"自修","上报","修复","放行","拦截并自修"}。
    规整后保留 step / 决策 / 规则 / 原因，便于与 build_step_reasoning 同构存储。
    """
    out: List[Dict[str, Any]] = []
    for r in reasons or []:
        if not isinstance(r, dict):
            continue
        out.append({
            "step": r.get("step") or "S3-AI契约",
            "input_summary": (
                f"图{r.get('chart_index')}" if r.get("chart_index") is not None else "全局"
            ),
            "ai_decision": r.get("decision"),
            "ai_reason": r.get("detail"),
            "rules_applied": [r.get("rule")] if r.get("rule") else [],
            "fallback_used": r.get("decision") in ("自修", "修复", "拦截并自修"),
            "output_ref": {"chart_index": r.get("chart_index"), "severity": r.get("severity")},
        })
    return out


def extract_self_corrections(reasons: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """从契约 reasons 中抽取「AI 原想 X，规则改成 Y」自纠事件（O10-3 飞轮强信号）。

    判定：decision ∈ {"自修","修复","拦截并自修"} 视为规则对 AI 产物的强制修正。
    返回结构可直接喂给经验库 record_experience / record_feedback。
    """
    corrections: List[Dict[str, Any]] = []
    for r in reasons or []:
        if not isinstance(r, dict):
            continue
        decision = r.get("decision")
        if decision in ("自修", "修复", "拦截并自修"):
            corrections.append({
                "event": "ai_self_correction",
                "rule": r.get("rule"),
                "step": r.get("step"),
                "chart_index": r.get("chart_index"),
                "decision": decision,
                "detail": r.get("detail"),
                # 便于经验库反向优化 prompt 的检索签名
                "signature": f"{r.get('rule')}:{decision}:{r.get('step')}",
            })
    return corrections


def merge_reasoning(
    existing: Optional[Any],
    fragment: Optional[Any],
) -> List[Dict[str, Any]]:
    """把追加推理片段合并进已有 reasoning（S3 契约滞后 append 用）。

    existing 可为 None / list / dict；fragment 可为单条 dict 或 list。
    返回合并后的 list（去重按 step+ai_decision+output_ref 近似，避免重复写入）。
    """
    merged: List[Dict[str, Any]] = []
    if isinstance(existing, list):
        merged.extend([x for x in existing if isinstance(x, dict)])
    elif isinstance(existing, dict):
        merged.append(existing)

    frags: List[Any] = []
    if isinstance(fragment, list):
        frags.extend(fragment)
    elif isinstance(fragment, dict):
        frags.append(fragment)

    seen = set()
    for rec in merged:
        key = (rec.get("step"), rec.get("ai_decision"), str(rec.get("output_ref")))
        seen.add(key)

    for f in frags:
        if not isinstance(f, dict):
            continue
        key = (f.get("step"), f.get("ai_decision"), str(f.get("output_ref")))
        if key in seen:
            continue
        seen.add(key)
        merged.append(f)
    return merged
