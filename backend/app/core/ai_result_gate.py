# -*- coding: utf-8 -*-
"""#43 AI 成果二值终态闸门（纯函数，零 IO）。

用户红线（2026-11-18）：
  1. AI 调用失败必须由用户确认「重试」或「兜底」，系统不得自动决定（含超时）。
  2. 不存在「部分成功 / 部分失败」拼接的成果；看板要么是 AI 每一步确认的最终成果，
     要么是用户明确选择兜底后的规则成果。

本模块只做判定，不写库、不调 LLM，任何链路都可复用。
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

# 五节点全集（看板生成链路）
DASHBOARD_NODES = ("s1", "s2", "s3", "s4", "s5")

RUN_KIND_AI = "ai_confirmed_full"        # 五节点全部 AI + 自检通过
RUN_KIND_RULE = "user_confirmed_rule"    # 用户明确选择规则兜底
RUN_KIND_NONE = None                     # 未出厂：等待用户确认 / 失败

VALID_RULE_CHOICES = frozenset({"rule_fallback"})
VALID_RETRY_CHOICES = frozenset({"wait_retry", "retry", "regenerate"})
# 超时 / 断连 / 未点选：一律不是用户确认
NON_CONFIRM_CHOICES = frozenset({"", "timeout", "awaiting_user", "auto", "system"})


def is_user_rule_choice(choice: Optional[str]) -> bool:
    """只有用户显式选了 rule_fallback 才算确认兜底。"""
    return isinstance(choice, str) and choice.strip().lower() in VALID_RULE_CHOICES


def is_user_retry_choice(choice: Optional[str]) -> bool:
    return isinstance(choice, str) and choice.strip().lower() in VALID_RETRY_CHOICES


def all_nodes_ai(by_node: Optional[Dict[str, Any]], nodes: Iterable[str] = DASHBOARD_NODES) -> bool:
    """五节点必须全部由 AI 主执行；缺节点 / rule_fallback / 空值都不算。"""
    if not isinstance(by_node, dict):
        return False
    for n in nodes:
        v = by_node.get(n)
        if isinstance(v, dict):
            v = v.get("by") or v.get("source")
        if str(v).strip().lower() != "ai":
            return False
    return True


def decide_result_kind(
    by_node: Optional[Dict[str, Any]],
    verified: bool,
    user_rule_choice: Optional[str],
    stage_errors: Optional[Iterable[str]] = None,
    nodes: Iterable[str] = DASHBOARD_NODES,
) -> Optional[str]:
    """二值终态判定，绝不返回混合态。

    - 五节点全 AI + 自检通过 + 无阶段错误 → ai_confirmed_full
    - 否则只有用户明确选了 rule_fallback → user_confirmed_rule
    - 其他一切情况（含超时 / 部分 AI / 自检未过 / 阶段失败未确认）→ None（不得出厂）
    """
    errs = [e for e in (stage_errors or []) if e]
    ai_ok = bool(verified) and all_nodes_ai(by_node, nodes) and not errs
    if ai_ok:
        return RUN_KIND_AI
    if is_user_rule_choice(user_rule_choice):
        return RUN_KIND_RULE
    return RUN_KIND_NONE


def factory_result_kind() -> Dict[str, Any]:
    """出厂失败时的统一负载：明确告知不出厂，并给出用户可选动作。"""
    return {
        "ok": False,
        "status": "awaiting_user",
        "result_kind": RUN_KIND_NONE,
        "message": "AI 未能在全部节点完成，且你尚未确认如何处理。看板未生成。"
                   "请选择「重试 AI」或「使用规则兜底生成」。",
        "options": ["wait_retry", "rule_fallback"],
    }


def badge_eligible(result_kind: Optional[str]) -> bool:
    """绿标只认 AI 全链确认成果；用户确认的规则兜底绝不冒领。"""
    return result_kind == RUN_KIND_AI
