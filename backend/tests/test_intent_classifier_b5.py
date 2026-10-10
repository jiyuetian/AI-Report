# -*- coding: utf-8 -*-
"""B5 回归（night42）：IntentType 应含 CLARIFY 成员，避免澄清意图构造枚举时 ValueError 打断 SSE 流。

TASK0_AUDIT B5 / Q9：分类器/LLM 路径可能返回 intent_type="clarify"，
旧代码 IntentType("clarify") 因无成员抛 ValueError → 整条 chat SSE 流中断（无回复、pending 不落库）。
新增 CLARIFY="clarify" 成员后，构造应成功且不抛。
"""
from app.core.intent_classifier import IntentType


def test_clarify_is_valid_intent_member():
    it = IntentType("clarify")
    assert it == IntentType.CLARIFY
    # str 枚举：可作为 JSON 值序列化（SSE 透传给前端）
    assert it.value == "clarify"
    assert isinstance(it.value, str)


def test_clarify_distinct_from_unknown():
    assert IntentType.CLARIFY != IntentType.UNKNOWN
