# -*- coding: utf-8 -*-
"""洞察 AI 解读层（G4，2026-10-29）。

分层职责（对齐用户标尺②：**AI 是每步主执行者，规则兜底逻辑也交给 AI**）：
    s3_insight_layer.compute_insights  → 规则**事实底座**（确定性、可离线、可单测）
    本模块 enhance_insights_with_ai    → AI **分析师级解读**（把事实卡深化为
                                          executive_summary / reading / hypotheses / watchlist）

不可让渡的护栏：
    - AI **不得删改**任何规则事实卡（事实卡原样保留，AI 产物放在 `ai_layer` 子键下）
    - AI 失败/超时/返回不合规 → `insight_source="rule"`，底座照常出厂，绝不空手
    - AI 解读原文标注 `"source": "ai"`，前端/报告可按来源分别渲染与信任分级

提示词外置：prompts/s3_insight_deepen.md（可在提示词中心维护）。
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional

_MAX_STR = 1200


def _describe_cards(insights: Dict[str, List[Dict[str, Any]]]) -> str:
    out = []
    for group in ("threshold_breach", "mom_yoy_delta", "top_contributor",
                  "attribution", "forecast", "outliers", "recommendation"):
        cards = insights.get(group) or []
        for idx, c in enumerate(cards[:6]):
            note = c.get("note") or c.get("action") or ""
            out.append(f"[{group}#{idx}] {note}")
    return "\n".join(out) if out else "（规则未算出显著事实卡）"


def _extract(resp: Any) -> Optional[Dict[str, Any]]:
    rj = getattr(resp, "response_json", None)
    if isinstance(rj, dict):
        return rj
    txt = getattr(resp, "content", None) or getattr(resp, "response", None)
    if isinstance(txt, str) and txt.strip():
        try:
            obj = json.loads(txt)
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None
    return None


async def enhance_insights_with_ai(
    insights: Dict[str, List[Dict[str, Any]]],
    data_summary: Dict[str, Any],
    *,
    theme: str = "",
    goals: Any = None,
    playbook: Optional[Dict[str, Any]] = None,
    thresholds: Optional[Dict[str, Any]] = None,
    llm_offline: bool = False,
) -> Dict[str, Any]:
    """在规则事实底座之上叠加 AI 分析师解读。

    返回结构（规则卡原样保留 + ai_layer 增量）：
    {
      <七组规则事实卡...>,
      "meta": {"source": "rule"|"ai", "executive_summary": [...], "fallback_reason": ...},
      "ai_layer": {"executive_summary": [...], "interpretations": [...],
                   "hypotheses": [...], "watchlist": [...]}
    }
    """
    t = dict(thresholds or {})
    base = dict(insights or {})  # 事实底座，AI 不可触碰
    result: Dict[str, Any] = {
        **base,
        "meta": {"source": "rule", "fallback_reason": None, "ai_groups": 0},
        "ai_layer": None,
    }

    if llm_offline or not t.get("insight_ai_enabled", True):
        result["meta"]["fallback_reason"] = (
            "llm_offline" if llm_offline else "insight_ai_enabled=False（管理员关闭）"
        )
        return result

    timeout = float(t.get("insight_ai_timeout", 25) or 25)
    try:
        from app.core.llm_gateway import llm_chat
        from app.core.brain_modules.s45_ai_orchestrator import load_prompt

        try:
            prompt = load_prompt(
                "s3_insight_deepen.md",
                THEME=theme or "通用数据看板",
                GOALS="\n".join(f"- {g.get('goal', '')}" for g in (goals or [])[:5])
                if isinstance(goals, list) else str(goals or "无"),
                PLAYBOOK=json.dumps(
                    {k: v for k, v in (playbook or {}).items() if k in ("domain", "benchmark", "kpi")},
                    ensure_ascii=False,
                )[:_MAX_STR] or "（无行业剧本）",
                DATA_SUMMARY=json.dumps(data_summary or {}, ensure_ascii=False)[:_MAX_STR],
                RULE_CARDS=_describe_cards(base),
            )
        except Exception as e:  # 提示词文件缺失 → 内联最小可用提示词
            print(f"[InsightAI] 提示词加载失败，回落内联: {e}")
            prompt = (
                "你是资深数据分析师。基于下列规则算出的真实事实卡做解读深化，"
                "不得臆造数字、不得删改事实卡。\n主题："
                + str(theme or "通用")
                + "\n事实卡：\n" + _describe_cards(base)
                + '\n只输出 JSON：{"executive_summary":[],"interpretations":[],'
                  '"hypotheses":[],"watchlist":[]}'
            )

        resp = await asyncio.wait_for(
            llm_chat(prompt=prompt, json_mode=True, user_id="insight_deepen", timeout=timeout),
            timeout=timeout + 5,
        )
        obj = _extract(resp)
        if not obj or not isinstance(obj.get("executive_summary"), list):
            result["meta"]["fallback_reason"] = "AI 返回结果缺少 executive_summary"
            return result

        ai_layer = {
            "executive_summary": [str(x)[:200] for x in obj.get("executive_summary", [])][:5],
            "interpretations": obj.get("interpretations") if isinstance(obj.get("interpretations"), list) else [],
            "hypotheses": obj.get("hypotheses") if isinstance(obj.get("hypotheses"), list) else [],
            "watchlist": [str(x)[:200] for x in (obj.get("watchlist") or [])][:6],
        }
        for card in ai_layer["interpretations"]:
            if isinstance(card, dict):
                card["source"] = "ai"
        for card in ai_layer["hypotheses"]:
            if isinstance(card, dict):
                card["source"] = "ai"
        result["ai_layer"] = ai_layer
        result["meta"].update({
            "source": "ai",
            "executive_summary": ai_layer["executive_summary"],
            "ai_groups": len(ai_layer["interpretations"]),
        })
        return result
    except Exception as e:
        print(f"[InsightAI] 洞察 AI 解读失败，规则底座出厂: {e}")
        result["meta"]["fallback_reason"] = str(e)[:300]
        return result
