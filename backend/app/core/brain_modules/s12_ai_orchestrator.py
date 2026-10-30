# -*- coding: utf-8 -*-
"""S1/S2 的 AI 主执行层（债A，2026-10-29）。

★ 设计真意（对齐《AI-Report改造方案》用户四条标尺之②）
  AI 是 S1（主题识别）与 S2（目标生成）的**主执行者**：规则结果先算出来作为「事实底座 + 护栏」
  交给 AI，AI 可引用、可推翻（在护栏内）、可结合自己的数据判断重新产出步骤产物；
  AI 失败/超时/产出不合规 → 由规则结果接管，全程零崩溃。

  ┌ 之前 ┐   S1 词典优先 + LLM兜底；S2 规则优先 + LLM增强（与翻转模式相反）
  └ 现在 ┘   AI 先干 → 规则护栏强制纠正 → 规则兜底保命（三态可查：s1_source / s2_source）

翻转模式沿用 S4/S5 的 G1 经验（s45_ai_orchestrator）：
    AI 成功且过护栏 → 用 AI 结果（记 source=ai）
    AI 失败/超时     → 用规则结果（记 source=rule + fallback_reason）
    护栏纠正         → 用纠正后结果（记 source=ai_guarded + guardrail 动作列表）

提示词外置在 prompts/ 下（H6 精神），占位符用 {KEY}（与 prompt_loader 约定一致，支持提示词中心覆盖）。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.core.prompt_loader import load_prompt
from app.core.flywheel import build_flywheel_context_from_fields


# 主题域候选（与 s1_theme_detector 保持一致，作为 AI 的候选范围 + 规则护栏基线参考）
_THEME_DOMAINS = """- 担保风控（包含担保、抵押、质押等字段）
- 逾期分析（包含逾期、违约等字段）
- 地区分布（包含省份、城市等字段）
- 客户画像（包含客户、企业等字段）
- 产品分析（包含贷款、借据等字段）"""


# ─────────────────────────── 提示词（内联兜底，外置 prompts/s1_ai_theme.md / s2_ai_goal.md 优先）───────────────────

_INLINE_S1_PROMPT = (
    "你是资深数据分析师。请分析以下数据集的主题。\n"
    "数据集名称：{dataset_name}\n字段列表：{fields}\n字段数量：{field_count}\n{sample_str}\n"
    "可识别的主题候选：\n{theme_domains}\n"
    "规则词典已给出的参考主题（置信度 {dict_confidence}）：{dict_theme}\n"
    "请你结合字段语义与样本数据，判断最匹配的主题标签（可沿用参考主题，也可提出更贴切的新主题）。\n"
    "只输出 JSON：{\"theme_tag\":\"主题标签\",\"confidence\":0.0~1.0,\"reason\":\"识别理由\"}\n"
)

_INLINE_S2_PROMPT = (
    "你是资深风控/业务分析师。请基于以下信息，从「结论→佐证→明细」视角生成分析目标。\n"
    "数据主题：{theme}\n数据粒度：{grain}\n字段列表：{fields}\n\n"
    "规则引擎已给出的基础目标（作为事实底座，可在其之上优化、增删、重排）：\n{base_goals}\n\n"
    "{flywheel_context}\n"
    "要求：\n"
    "1. 目标必须是中文业务化表述，避免技术术语（如\"维度分析\"、\"指标\"等）\n"
    "2. 覆盖类型：KPI/趋势/对比/分布/预警/画像/关联 各至少 1 个\n"
    "3. 描述要通俗易懂；每张图期望图型写在 expected_charts\n"
    "4. 目标数量控制在 {max_goals} 个以内\n"
    "{sample_data}\n"
    "只输出 JSON：{\"goals\":[{\"goal_id\":\"G1\",\"title\":\"..\",\"description\":\"..\","
    "\"type\":\"KPI/趋势/对比/分布/预警/画像/关联\",\"priority\":10,\"expected_charts\":[\"line\"]}]}\n"
)


# ─────────────────────────── 工具 ───────────────────────────

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
            try:
                clean = txt.strip().strip("`")
                if clean.lower().startswith("json"):
                    clean = clean[4:]
                obj = json.loads(clean)
                return obj if isinstance(obj, dict) else None
            except Exception:
                return None
    return None


async def _log_step_s1(run_id: Optional[str], meta: Dict[str, Any]) -> None:
    """把 S1 的**处理方案与原因**写进 ai_action_log（用户标尺④：每步可追溯）。"""
    if not run_id:
        return
    try:
        import asyncio
        from app.core.ai_action_log import log_ai_action

        status = "success" if meta.get("source") in ("ai", "ai_guarded") else "failed"
        asyncio.create_task(log_ai_action(
            run_id=run_id,
            intent="s12_s1_identify",
            action_type="ai_decision",
            params_summary={
                "source": meta.get("source"),
                "theme_tag": meta.get("theme_tag"),
                "confidence": meta.get("confidence"),
                "matched_keywords": meta.get("matched_keywords", []),
                "guardrail": meta.get("guardrail", []),
                "reasoning": (meta.get("reasoning") or "")[:400],
            },
            result_status=status,
            error_msg=meta.get("fallback_reason"),
            llm_layer=status,
        ))
    except Exception as e:
        print(f"[S12AI] S1 步骤日志写入失败(不阻断): {e}")


async def _log_step_s2(run_id: Optional[str], meta: Dict[str, Any]) -> None:
    """把 S2 的**处理方案与原因**写进 ai_action_log（用户标尺④：每步可追溯）。"""
    if not run_id:
        return
    try:
        import asyncio
        from app.core.ai_action_log import log_ai_action

        status = "success" if meta.get("source") in ("ai", "ai_guarded") else "failed"
        asyncio.create_task(log_ai_action(
            run_id=run_id,
            intent="s12_s2_generate",
            action_type="ai_decision",
            params_summary={
                "source": meta.get("source"),
                "generated_by": meta.get("generated_by"),
                "goal_count": meta.get("goal_count"),
                "guardrail": meta.get("guardrail", []),
                "reasoning": (meta.get("reasoning") or "")[:400],
            },
            result_status=status,
            error_msg=meta.get("fallback_reason"),
            llm_layer=status,
        ))
    except Exception as e:
        print(f"[S12AI] S2 步骤日志写入失败(不阻断): {e}")


# ─────────────────────────── AI：S1 主题识别 ───────────────────────────

async def ai_identify_theme(
    db, fields: List[str], sample_data: Optional[List[Dict]], dataset_name: str,
    dict_theme: Optional[str], dict_confidence: float, timeout: float,
) -> Optional[Dict[str, Any]]:
    """调用 LLM 做主题识别（AI 主执行）。失败返回 None。"""
    import asyncio
    from app.core.llm_gateway import llm_chat

    sample_str = ""
    if sample_data:
        sample_str = f"样本数据（前3行）：\n{str(sample_data[:3])[:500]}"

    prompt = load_prompt(
        "s1_ai_theme", _INLINE_S1_PROMPT,
        dataset_name=dataset_name or "未命名数据集",
        fields=", ".join(fields),
        field_count=str(len(fields)),
        sample_str=sample_str,
        theme_domains=_THEME_DOMAINS,
        dict_theme=dict_theme or "（无）",
        dict_confidence=str(round(dict_confidence or 0.0, 2)),
    )
    resp = await asyncio.wait_for(
        llm_chat(prompt=prompt, json_mode=True, user_id="s1_ai_identify", timeout=timeout),
        timeout=timeout + 2,
    )
    return _extract_json(resp)


# ─────────────────────────── AI：S2 目标生成 ───────────────────────────

async def ai_generate_goals(
    db, theme: str, grain: str, fields: List[str], base_goals: List[Any],
    flywheel_context: str, field_profiles: Optional[List[Dict]], timeout: float, max_goals: int,
) -> Optional[Dict[str, Any]]:
    """调用 LLM 做目标生成（AI 主执行，规则 base_goals 为事实底座）。失败返回 None。"""
    import asyncio
    from app.core.llm_gateway import llm_chat

    base_goals_json = json.dumps(
        [g.to_dict() for g in base_goals], ensure_ascii=False, indent=2
    ) if base_goals else "（无）"
    sample_json = ""
    if field_profiles:
        sample_json = "字段画像（前5）：\n" + json.dumps(field_profiles[:5], ensure_ascii=False)

    prompt = load_prompt(
        "s2_ai_goal", _INLINE_S2_PROMPT,
        theme=theme or "通用分析",
        grain=grain or "detail",
        fields=json.dumps(fields, ensure_ascii=False),
        base_goals=base_goals_json,
        flywheel_context=flywheel_context or "",
        max_goals=str(int(max_goals or 6)),
        sample_data=sample_json,
    )
    resp = await asyncio.wait_for(
        llm_chat(prompt=prompt, json_mode=True, user_id="s2_ai_generate", timeout=timeout),
        timeout=timeout + 2,
    )
    return _extract_json(resp)


# ─────────────────────────── 主入口：S1 ───────────────────────────

async def dispatch_s1_ai_primary(
    db, fields: List[str], sample_data: Optional[List[Dict]] = None, dataset_name: str = "",
    thresholds: Optional[Dict[str, Any]] = None, llm_offline: bool = False, run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """S1 AI 主执行主题识别（含护栏纠正 + 规则兜底）。返回 S1 结果 dict（含 theme_tag 与三态 source）。

    返回 dict 字段：
      theme_tag, confidence, matched_keywords, method, llm_called, reason,
      source("ai"|"ai_guarded"|"rule"), guardrail[...], fallback_reason
    """
    from app.core.brain_modules.s1_theme_detector import S1ThemeDetector

    thresholds = thresholds or {}
    detector = S1ThemeDetector()
    # 规则事实底座 + 护栏基线（始终计算，供护栏对比）
    rule_res = await detector.detect(db, fields, sample_data, dataset_name, use_llm=False)
    dict_theme = rule_res.theme_tag
    dict_conf = rule_res.confidence
    dict_kw = rule_res.matched_keywords

    meta: Dict[str, Any] = {
        "source": "rule", "theme_tag": dict_theme or "数据概览", "confidence": dict_conf,
        "matched_keywords": dict_kw, "method": "dictionary", "llm_called": False,
        "reason": rule_res.reason if hasattr(rule_res, "reason") else "",
        "guardrail": [], "fallback_reason": None,
    }

    if llm_offline or not thresholds.get("s1_ai_enabled", True):
        meta["fallback_reason"] = "llm_offline" if llm_offline else "s1_ai_enabled=False（管理员关闭）"
        await _log_step_s1(run_id, meta)
        return meta

    timeout = float(thresholds.get("s1_ai_timeout", 25) or 25)
    try:
        ai = await ai_identify_theme(db, fields, sample_data, dataset_name, dict_theme, dict_conf, timeout)
        if not ai or not str(ai.get("theme_tag", "")).strip() or str(ai.get("theme_tag")) in ("未知", "unknown"):
            meta["fallback_reason"] = "AI 未返回有效主题"
            await _log_step_s1(run_id, meta)
            return meta
        ai_theme = str(ai.get("theme_tag")).strip()
        ai_conf = float(ai.get("confidence", 0.5) or 0.5)
        # 护栏 G-S1：高置信词典命中且 AI 偏离 → 强制纠正到词典结果（规则不可让渡的地基）
        _guard_thr = float(thresholds.get("s1_ai_guardrail_threshold", 0.8) or 0.8)
        if dict_conf >= _guard_thr and ai_theme != dict_theme:
            meta["source"] = "ai_guarded"
            meta["theme_tag"] = dict_theme
            meta["confidence"] = dict_conf
            meta["guardrail"] = [
                f"G-S1 词典高置信命中(dict={dict_theme},{dict_conf})，AI 偏离({ai_theme})已纠正"
            ]
            meta["reason"] = f"AI 提议 {ai_theme}({ai_conf})，但规则词典高置信指向 {dict_theme}，护栏纠正"
        else:
            meta["source"] = "ai"
            meta["theme_tag"] = ai_theme
            meta["confidence"] = ai_conf
            meta["reason"] = str(ai.get("reason", ""))[:400]
        meta["llm_called"] = True
        meta["method"] = meta["source"]
        await _log_step_s1(run_id, meta)
        return meta
    except Exception as e:
        print(f"[S12AI] S1 AI 识别失败，规则兜底: {e}")
        meta["fallback_reason"] = str(e)[:300]
        await _log_step_s1(run_id, meta)
        return meta


# ─────────────────────────── 主入口：S2 ───────────────────────────

async def dispatch_s2_ai_primary(
    db, fields: List[str], grain: str = "detail", theme: str = "",
    thresholds: Optional[Dict[str, Any]] = None, llm_offline: bool = False, run_id: Optional[str] = None,
    field_profiles: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """S2 AI 主执行目标生成（含护栏纠正 + 规则兜底）。

    返回 dict：{"goals":[goal_dict...], "source":"ai"|"ai_guarded"|"rule",
                "generated_by":"llm"|"rule", "guardrail":[...], "fallback_reason":...}
    """
    from app.core.brain_modules.s2_goal_generator import S2GoalGenerator

    thresholds = thresholds or {}
    generator = S2GoalGenerator()
    # 规则事实底座 + 护栏基线（始终计算，作为 AI 可引用/推翻的底座）
    base_goals = await generator.generate(
        db, theme, fields, grain, use_llm=False, field_profiles=field_profiles
    )

    meta: Dict[str, Any] = {
        "source": "rule", "generated_by": "rule", "reasoning": "",
        "guardrail": [], "fallback_reason": None, "goal_count": len(base_goals),
    }

    def _rule_payload(reason: str):
        meta["fallback_reason"] = reason
        return {
            "goals": [g.to_dict() for g in base_goals],
            "source": "rule", "generated_by": "rule",
            "guardrail": meta["guardrail"], "fallback_reason": reason,
        }

    if llm_offline or not thresholds.get("s2_ai_enabled", True):
        meta["fallback_reason"] = "llm_offline" if llm_offline else "s2_ai_enabled=False（管理员关闭）"
        await _log_step_s2(run_id, meta)
        return _rule_payload(meta["fallback_reason"])

    timeout = float(thresholds.get("s2_ai_timeout", 30) or 30)
    max_goals = int(thresholds.get("s2_max_goals", 6) or 6)
    # 债B 闭环【读路径】：把同形态历史经验注入 S2 提示词，让 AI 参考被验证有效的决策
    flywheel_context = build_flywheel_context_from_fields(fields, grain)
    try:
        ai = await ai_generate_goals(
            db, theme, grain, fields, base_goals, flywheel_context, field_profiles, timeout, max_goals
        )
        if not ai or not isinstance(ai.get("goals"), list) or not ai["goals"]:
            meta["fallback_reason"] = "AI 未返回有效目标"
            await _log_step_s2(run_id, meta)
            return _rule_payload(meta["fallback_reason"])
        raw = ai["goals"]
        valid: List[Dict[str, Any]] = []
        dropped = 0
        for g in raw[:max_goals + 3]:
            if isinstance(g, dict) and str(g.get("title", "")).strip() and str(g.get("type", "")).strip():
                valid.append({
                    "goal_id": g.get("goal_id") or f"G{len(valid) + 1}",
                    "title": str(g.get("title")),
                    "description": str(g.get("description", "")),
                    "type": str(g.get("type")),
                    "priority": int(g.get("priority", 5) or 5),
                    "expected_charts": g.get("expected_charts") or [],
                    "generated_by": "llm",
                })
            else:
                dropped += 1
        # 护栏 G-S2a：不足 3 个 → 用规则基础目标补齐（防 AI 产出过稀）
        if len(valid) < 3:
            valid += [g.to_dict() for g in base_goals[len(valid):]]
            if dropped:
                meta["guardrail"].append(f"G-S2 丢弃 {dropped} 个非法目标，规则补齐至 {len(valid)} 个")
        # 护栏 G-S2b：超上限 → 截断
        if len(valid) > max_goals:
            valid = valid[:max_goals]
            meta["guardrail"].append(f"G-S2 目标数超上限 {max_goals}，截断")
        meta["source"] = "ai_guarded" if meta["guardrail"] else "ai"
        meta["generated_by"] = "llm"
        meta["reasoning"] = str(ai.get("reason") or ai.get("reasoning") or "")[:400]
        await _log_step_s2(run_id, meta)
        return {
            "goals": valid, "source": meta["source"], "generated_by": "llm",
            "guardrail": meta["guardrail"], "fallback_reason": None,
        }
    except Exception as e:
        print(f"[S12AI] S2 AI 生成失败，规则兜底: {e}")
        meta["fallback_reason"] = str(e)[:300]
        await _log_step_s2(run_id, meta)
        return _rule_payload(meta["fallback_reason"])
