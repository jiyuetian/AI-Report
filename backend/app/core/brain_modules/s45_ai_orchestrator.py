# -*- coding: utf-8 -*-
"""S4/S5 的 AI 主执行层（G1，2026-10-29）。

★ 设计真意（对齐《AI-Report改造方案》用户四条标尺之②）
  AI 是 S4（编排）与 S5（验收）的**主执行者**：规则结果先算出来作为「事实底座 + 护栏」
  交给 AI，AI 可引用、可推翻（在护栏内）、可结合自己的数据判断重新产出步骤产物；
  AI 失败/超时/产出不合规 → 由规则编排与规则评分卡接管，全程零崩溃。

  ┌ 之前 ┐   s4_orchestrator.py 全文零 LLM 调用 → S4 排序/S5 及格裁定 100% 规则
  └ 现在 ┘   AI 先干 → 规则护栏强制纠正 → 规则兜底保命（三态可查：s4_source / s5_source）

翻转模式沿用 S3 的 A2 经验（`_dispatch_s3_ai_primary`）：
    AI 成功且过护栏 → 用 AI 结果（记 source=ai）
    AI 失败/超时     → 用规则结果（记 source=rule + fallback_reason）
    护栏纠正         → 用纠正后结果（记 source=ai_guarded + guardrail 动作列表）

提示词外置在 prompts/ 下（H6 精神），占位符用 <<KEY>> 避免与 JSON 花括号冲突。
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

_PROMPT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prompts"
)


# ─────────────────────────── 提示词加载 ───────────────────────────

def load_prompt(filename: str, **placeholders: Any) -> str:
    """加载外置提示词并按 <<KEY>> 占位符替换；文件缺失时抛异常由上层兜底。

    管理员可在「提示词中心 / brain_configs」维护同名文件，改提示词无需改代码。
    """
    path = os.path.join(_PROMPT_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        tpl = f.read()
    for k, v in placeholders.items():
        tpl = tpl.replace(f"<<{k}>>", str(v))
    return tpl


def _safe_load_prompt(filename: str, inline: str, **placeholders: Any) -> str:
    try:
        return load_prompt(filename, **placeholders)
    except Exception as e:
        print(f"[S45AI] 提示词 {filename} 加载失败，回落内联默认: {e}")
        for k, v in placeholders.items():
            inline = inline.replace(f"<<{k}>>", str(v))
        return inline


_INLINE_S4_PROMPT = (
    "你是资深数据看板主编，请按「结论→佐证→明细」编排下列图表。\n"
    "主题：<<THEME>>\n目标：<<GOALS>>\n可用图表：<<CHARTS>>\n"
    "只输出 JSON：{\"order\":[id], \"kpi_ids\":[id], \"drops\":[{\"id\":id,\"reason\":原因}], "
    "\"narrative_flow\":\"主线\", \"reasoning\":\"依据\"}\n"
)

_INLINE_S5_PROMPT = (
    "你是资深看板评审，请给这组看板打分。\n主题：<<THEME>>\n目标：<<GOALS>>\n"
    "规则评分：<<RULE_SCORE>>\n图表：<<CHARTS>>\n"
    "只输出 JSON：{\"dims\":{\"coverage\":..,\"narrative\":..,\"redundancy\":..,\"accuracy\":..,"
    "\"readability\":..},\"overall\":..,\"critique\":\"..\",\"must_fix\":[],\"verdict\":\"pass|fail\"}\n"
)


# ─────────────────────────── 工具 ───────────────────────────

def ensure_chart_ids(charts: List[Dict]) -> List[Dict]:
    """给每张图补稳定 id（AI 只能引用这些 id，防臆造）。"""
    for i, c in enumerate(charts or []):
        if not isinstance(c, dict):
            continue
        if not c.get("id"):
            c["id"] = f"chart_{i}"
    return charts


def describe_charts(charts: List[Dict]) -> str:
    lines = []
    for c in charts or []:
        if not isinstance(c, dict):
            continue
        cid = c.get("id", "?")
        ctype = c.get("chart_type", "unknown")
        title = c.get("title", "无标题")
        dim = c.get("x_field") or c.get("category_field") or ""
        val = c.get("y_field") or c.get("value_field") or ""
        lines.append(f"- {cid} | {ctype} | {title} | {dim}→{val}")
    return "\n".join(lines) if lines else "（无图表）"


def describe_insights(insights: Optional[Dict[str, List[Dict]]], limit: int = 12) -> str:
    if not insights:
        return "（无洞察）"
    lines = []
    n = 0
    for group in ("threshold_breach", "mom_yoy_delta", "top_contributor",
                  "attribution", "forecast", "outliers", "recommendation"):
        for c in (insights.get(group) or [])[:4]:
            if n >= limit:
                break
            note = c.get("note") or c.get("action") or ""
            if note:
                lines.append(f"[{group}] {note}")
                n += 1
    return "\n".join(lines) if lines else "（无洞察）"


def _extract_json(resp: Any) -> Optional[Dict[str, Any]]:
    if resp is None:
        return None
    rj = getattr(resp, "response_json", None)
    if isinstance(rj, dict):
        return rj
    txt = getattr(resp, "content", None) or getattr(resp, "response", None)
    if isinstance(txt, str) and txt.strip():
        try:
            obj = json.loads(txt)
            return obj if isinstance(obj, dict) else None
        except Exception:
            # 容忍 LLM 包一层 markdown 代码块
            try:
                clean = txt.strip().strip("`")
                if clean.lower().startswith("json"):
                    clean = clean[4:]
                obj = json.loads(clean)
                return obj if isinstance(obj, dict) else None
            except Exception:
                return None
    return None


# ─────────────────────────── S4 护栏 ───────────────────────────

def apply_arrangement_guardrails(
    charts: List[Dict],
    plan: Dict[str, Any],
    thresholds: Dict[str, Any],
) -> Dict[str, Any]:
    """把 AI 编排结果强制收敛到护栏内（这是规则不可让渡的地基职责）。

    护栏清单（每条都记进 guardrail 动作，便于血缘追溯）：
      G-A 幻觉图表：order/kpi_ids/layers 中不在可用集合内的 id → 丢弃
      G-B 遗漏图表：既没进 order 也没给出合法 drop 理由的图 → 追加到末尾
      G-C 图表总数上限 s4_max_charts → 截断
      G-D KPI 卡上限 r3_max_kpis  → 超限的降级排到末尾（不再是结论层）
      G-E 去重：同一 id 只允许出现一次
      G-F 叙事分层：按图表类型优先级重算三层（AI 的分层仅存档不动用）
      G-G 叙事硬排序（narrative_enforce_strict_sort=True 时）：按 NARRATIVE_PRIORITY 重排
    """
    from app.core.brain_modules.s4_orchestrator import S4Orchestrator  # 延迟导入避免循环

    actions: List[str] = []
    charts = ensure_chart_ids(charts)
    by_id = {c["id"]: c for c in charts if isinstance(c, dict)}
    max_charts = int(thresholds.get("s4_max_charts", 6) or 6)
    max_kpis = int(thresholds.get("r3_max_kpis", 4) or 4)

    raw_order = plan.get("order") if isinstance(plan.get("order"), list) else []
    raw_drops = plan.get("drops") if isinstance(plan.get("drops"), list) else []
    dropped_ids = set()
    drop_notes = []
    for d in raw_drops:
        if isinstance(d, dict) and d.get("id") in by_id and str(d.get("reason", "")).strip():
            dropped_ids.add(d["id"])
            drop_notes.append({"id": d["id"], "reason": str(d.get("reason"))})
        elif isinstance(d, str) and d in by_id:
            dropped_ids.add(d)
            drop_notes.append({"id": d, "reason": "AI 判定可删（未给理由）"})

    ordered: List[Dict] = []
    seen = set()
    hallucinated = 0
    for cid in raw_order:
        if not isinstance(cid, str):
            continue
        if cid not in by_id:
            hallucinated += 1
            continue
        if cid in seen or cid in dropped_ids:
            continue
        ordered.append(by_id[cid])
        seen.add(cid)
    if hallucinated:
        actions.append(f"G-A 丢弃AI臆造/不存在的图表 {hallucinated} 个")

    # G-B 遗漏补齐
    missing = [c for cid, c in by_id.items() if cid not in seen and cid not in dropped_ids]
    if missing:
        actions.append(f"G-B 补齐被AI遗漏的图表 {len(missing)} 张（排到末尾）")
        ordered.extend(missing)

    # G-C 总数上限
    if len(ordered) > max_charts:
        actions.append(f"G-C 图表数 {len(ordered)} 超上限 {max_charts}，截断")
        ordered = ordered[:max_charts]

    # AI 指定的结论层 KPI（仅存档追溯，实际分层由类型确定性重算）
    ai_kpis = [k for k in (plan.get("kpi_ids") or []) if isinstance(k, str) and k in {c.get("id") for c in ordered}]

    # G-D KPI 上限：只保留 AI 排序里最靠前的 max_kpis 张 KPI，多余的**真的删掉**
    #     （仅挪到末尾没用——按类型分层时它们仍会回到结论层，护栏形同虚设）
    kpi_now = [c for c in ordered if c.get("chart_type") == "kpi"]
    if len(kpi_now) > max_kpis:
        keep_ids = {id(c) for c in kpi_now[:max_kpis]}
        ordered = [c for c in ordered if id(c) in keep_ids or c.get("chart_type") != "kpi"]
        actions.append(f"G-D KPI 卡 {len(kpi_now)} 超上限 {max_kpis}，删除多余的 {len(kpi_now) - max_kpis} 张")

    # G-G 叙事次序（白盒可调 s4_narrative_mode）：
    #   strict   = 完全按 NARRATIVE_PRIORITY 硬排序（规则主导，等同旧规则编排）
    #   ai_first = AI 顺序为准（AI 是主执行者），规则只守「KPI 结论层前置」这一条硬底线
    _mode = str(thresholds.get("s4_narrative_mode", "ai_first") or "ai_first").lower()
    if _mode == "strict":
        prio = S4Orchestrator.NARRATIVE_PRIORITY
        ordered.sort(key=lambda c: prio.get(c.get("chart_type"), 3))
        actions.append("G-G 严格叙事硬排序（管理员设 s4_narrative_mode=strict）")
    else:
        _kpi = [c for c in ordered if c.get("chart_type") == "kpi"]
        _rest = [c for c in ordered if c.get("chart_type") != "kpi"]
        ordered = _kpi + _rest
        actions.append("G-G 尊重AI叙事顺序，仅强制KPI结论层前置（s4_narrative_mode=ai_first）")

    # G-F 分层由图表类型确定性重算；AI 分层只存档
    orch = S4Orchestrator()
    layers = orch.organize_narrative(ordered)
    ai_layers = plan.get("layers") if isinstance(plan.get("layers"), dict) else None
    narrative_flow = str(plan.get("narrative_flow") or "").strip()
    if not narrative_flow:
        narrative_flow = orch._build_narrative_flow(layers, ordered)
        actions.append("G-F AI 未给叙事主线，用真实分层回填")

    return {
        "ok": True,
        "charts": ordered,
        "layers": layers,
        "kpi_ids": ai_kpis,
        "kpi_count": len(layers.get("L1_conclusion", [])),
        "narrative_flow": narrative_flow,
        "drops": drop_notes,
        "ai_layers": ai_layers,
        "guardrail": actions,
        "hallucinated": hallucinated,
    }


# ─────────────────────────── AI：S4 编排 ───────────────────────────

async def ai_orchestrate(
    db, charts: List[Dict], theme: str, goals: Any, insights: Optional[Dict],
    thresholds: Dict[str, Any], timeout: float,
) -> Optional[Dict[str, Any]]:
    """调用 LLM 做看板编排（叙事顺序/KPI 选取/去冗余）。失败返回 None。"""
    import asyncio
    from app.core.llm_gateway import llm_chat

    ensure_chart_ids(charts)
    prompt = _safe_load_prompt(
        "s4_ai_orchestrate.md", _INLINE_S4_PROMPT,
        THEME=theme or "通用数据看板",
        GOALS="\n".join(f"- {g.get('goal', '')}" for g in (goals or [])[:5])
        if isinstance(goals, list) else str(goals or "无"),
        INSIGHTS=describe_insights(insights),
        CHARTS=describe_charts(charts),
        MAX_KPIS=int(thresholds.get("r3_max_kpis", 4) or 4),
        MAX_CHARTS=int(thresholds.get("s4_max_charts", 6) or 6),
    )
    resp = await asyncio.wait_for(
        llm_chat(prompt=prompt, json_mode=True, user_id="s4_ai_orchestrate", timeout=timeout),
        timeout=timeout + 2,
    )
    plan = _extract_json(resp)
    if not plan or not isinstance(plan.get("order"), list) or not plan.get("order"):
        return None
    return plan


async def _log_step(stage: str, run_id: Optional[str], meta: Dict[str, Any]) -> None:
    """把本次 AI 步骤的**处理方案与原因**写进 ai_action_log（用户标尺④：每步可追溯）。

    只在给出 run_id 时写（离线单测/无 run 场景跳过）；fire-and-forget，任何异常不阻断主链路。
    """
    if not run_id:
        return
    try:
        import asyncio
        from app.core.ai_action_log import log_ai_action

        status = "success" if meta.get("source") in ("ai", "ai_guarded") or meta.get("s5_source") == "ai_joint" else "failed"
        params = {
            "source": meta.get("source") or meta.get("s5_source"),
            "reasoning": (meta.get("reasoning") or "")[:400],
            "guardrail": meta.get("guardrail") or [],
            "drops": (meta.get("drops") or [])[:10],
            "hallucinated": meta.get("hallucinated", 0),
            "ai_overall": meta.get("ai_overall"),
            "ai_dims": meta.get("ai_dims"),
            "ai_verdict": meta.get("ai_verdict"),
            "must_fix": (meta.get("must_fix") or [])[:10],
        }
        asyncio.create_task(log_ai_action(
            run_id=run_id,
            intent=f"s45_{stage}",
            action_type="ai_decision",
            params_summary=params,
            result_status=status,
            error_msg=meta.get("fallback_reason"),
            llm_layer=status,
        ))
    except Exception as e:
        print(f"[S45AI] 步骤日志写入失败(不阻断): {e}")


async def dispatch_s4_ai_primary(
    db, charts: List[Dict], theme: str, goals: Any, insights: Optional[Dict],
    thresholds: Dict[str, Any], llm_offline: bool = False, run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """S4 AI 主执行编排（含护栏纠正 + 规则兜底）。返回 (arrangement, meta)。

    arrangement: {"charts","layers","narrative_flow","kpi_count"}
    meta:        {"source": "ai"|"ai_guarded"|"rule", "reasoning":..., "guardrail":[...], "fallback_reason":...}
    """
    from app.core.brain_modules.s4_orchestrator import S4Orchestrator

    orch = S4Orchestrator()
    meta: Dict[str, Any] = {"source": "rule", "reasoning": "", "guardrail": [], "fallback_reason": None}

    def _rule_arrangement() -> Dict[str, Any]:
        res = orch.orchestrate(charts, max_charts=int(thresholds.get("s4_max_charts", 6) or 6))
        return {
            "charts": res.get("charts", []),
            "layers": res.get("layers", {}),
            "narrative_flow": res.get("narrative_flow", ""),
            "kpi_count": res.get("kpi_count", 0),
        }

    if llm_offline or not thresholds.get("s4_ai_enabled", True):
        meta["fallback_reason"] = "llm_offline" if llm_offline else "s4_ai_enabled=False（管理员关闭）"
        await _log_step("s4_arrange", run_id, meta)
        return _rule_arrangement(), meta

    timeout = float(thresholds.get("s4_ai_timeout", 30) or 30)
    try:
        plan = await ai_orchestrate(db, charts, theme, goals, insights, thresholds, timeout)
        if not plan:
            meta["fallback_reason"] = "AI 未返回有效编排方案"
            await _log_step("s4_arrange", run_id, meta)
            return _rule_arrangement(), meta
        guarded = apply_arrangement_guardrails(charts, plan, thresholds)
        meta.update({
            "source": "ai_guarded" if guarded.get("guardrail") else "ai",
            "reasoning": str(plan.get("reasoning") or "")[:800],
            "guardrail": guarded.get("guardrail", []),
            "drops": guarded.get("drops", []),
            "hallucinated": guarded.get("hallucinated", 0),
            "ai_plan": {
                "order": plan.get("order"),
                "kpi_ids": plan.get("kpi_ids"),
                "narrative_flow": plan.get("narrative_flow"),
            },
        })
        await _log_step("s4_arrange", run_id, meta)
        return {
            "charts": guarded["charts"],
            "layers": guarded["layers"],
            "narrative_flow": guarded["narrative_flow"],
            "kpi_count": guarded["kpi_count"],
        }, meta
    except Exception as e:
        print(f"[S45AI] S4 AI 编排失败，规则兜底: {e}")
        meta["fallback_reason"] = str(e)[:300]
        await _log_step("s4_arrange", run_id, meta)
        return _rule_arrangement(), meta


# ─────────────────────────── AI：S5 裁判 ───────────────────────────

async def ai_score(
    db, charts: List[Dict], theme: str, goals: Any, rule_score: Dict[str, Any],
    thresholds: Dict[str, Any], timeout: float,
) -> Optional[Dict[str, Any]]:
    """调用 LLM 做 S5 评审裁判。返回 {"dims","overall","critique","must_fix","verdict"} 或 None。"""
    import asyncio
    from app.core.llm_gateway import llm_chat

    prompt = _safe_load_prompt(
        "s5_ai_score.md", _INLINE_S5_PROMPT,
        THEME=theme or "通用数据看板",
        GOALS="\n".join(f"- {g.get('goal', '')}" for g in (goals or [])[:5])
        if isinstance(goals, list) else str(goals or "无"),
        RULE_SCORE=json.dumps(rule_score or {}, ensure_ascii=False)[:1200],
        CHARTS=describe_charts(charts),
    )
    resp = await asyncio.wait_for(
        llm_chat(prompt=prompt, json_mode=True, user_id="s5_ai_score", timeout=timeout),
        timeout=timeout + 2,
    )
    rj = _extract_json(resp)
    if not rj:
        return None
    dims = rj.get("dims")
    if not isinstance(dims, dict):
        return None
    cleaned = {}
    for k in ("coverage", "narrative", "redundancy", "accuracy", "readability"):
        v = dims.get(k)
        if isinstance(v, (int, float)):
            cleaned[k] = max(0.0, min(100.0, float(v)))
    if len(cleaned) < 5:
        return None
    return {
        "dims": cleaned,
        "overall": float(rj.get("overall", 0) or 0),
        "critique": str(rj.get("critique", ""))[:500],
        "must_fix": rj.get("must_fix") or [],
        "verdict": str(rj.get("verdict", "")).lower(),
    }


async def dispatch_s5_ai_judge(
    db, charts: List[Dict], theme: str, goals: Any, rule_score_obj: Any,
    weights: Dict[str, float], thresholds: Dict[str, Any], llm_offline: bool = False,
    run_id: Optional[str] = None,
) -> Tuple[Any, Dict[str, Any]]:
    """S5 双裁判：规则（地基/硬门禁） × AI（质量把关）。

    裁决规则（白盒，可在 brain_configs 关停 AI 裁判）：
      - AI 可用且返回完整五维 → passed = rule_pass AND ai_pass（两票都要过）
      - AI 失败/超时/返回不全 → passed = rule_pass，source=rule
    返回 (DashboardScore, meta)；DashboardScore 的 dims/overall 采用 AI 值（若有），
    passed 采用双票结果，并记录 s5_source 便于血缘追溯。
    """
    from app.core.brain_modules.s4_orchestrator import aggregate_score

    meta: Dict[str, Any] = {
        "s5_source": "rule", "ai_dims": None, "ai_overall": None,
        "ai_critique": None, "must_fix": [], "ai_verdict": None, "fallback_reason": None,
    }
    rule_pass = bool(getattr(rule_score_obj, "passed", False))

    if not llm_offline and thresholds.get("s5_ai_enabled", True):
        timeout = float(thresholds.get("s5_ai_timeout", 25) or 25)
        rule_score = {
            "overall": round(getattr(rule_score_obj, "overall_score", 0) or 0, 2),
            "dims": {k: round(v, 2) for k, v in (getattr(rule_score_obj, "dimension_scores", {}) or {}).items()},
            "passed": rule_pass,
        }
        try:
            got = await ai_score(db, charts, theme, goals, rule_score, thresholds, timeout)
            if got:
                meta.update({
                    "s5_source": "ai_joint",
                    "ai_dims": got["dims"],
                    "ai_overall": round(aggregate_score(got["dims"], weights), 2),
                    "ai_critique": got["critique"],
                    "must_fix": got["must_fix"] if isinstance(got["must_fix"], list) else [],
                    "ai_verdict": got["verdict"],
                })
                # AI 联合裁判：采用 AI 五维评分作为对外展示分（ critiques 并入返工建议）
                rule_score_obj.dimension_scores = dict(got["dims"])
                rule_score_obj.overall_score = meta["ai_overall"]
                ai_pass = got["verdict"] != "fail" and meta["ai_overall"] >= float(
                    thresholds.get("r6_grade_accept", 70)
                )
                rule_score_obj.passed = bool(rule_pass and ai_pass)
                if got["critique"]:
                    rule_score_obj.improvement_suggestions = (
                        list(rule_score_obj.improvement_suggestions or []) + [f"[AI评审] {got['critique']}"]
                    )
                await _log_step("s5_judge", run_id, meta)
                return rule_score_obj, meta
            meta["fallback_reason"] = "AI 评审未返回有效五维评分"
        except Exception as e:
            print(f"[S45AI] S5 AI 裁判失败，规则评分卡兜底: {e}")
            meta["fallback_reason"] = str(e)[:300]
    else:
        meta["fallback_reason"] = "llm_offline" if llm_offline else "s5_ai_enabled=False（管理员关闭）"

    await _log_step("s5_judge", run_id, meta)
    return rule_score_obj, meta
