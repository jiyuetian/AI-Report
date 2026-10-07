# -*- coding: utf-8 -*-
"""AI/LLM 失败原因归一化（chat 与 brain 共用，单一事实来源，避免分叉）。

统一枚举值：
    ok            —— 成功（LLM 参与了回复生成）
    timeout       —— 调用超时
    rate_limited  —— 模型限流（含 429 / too many requests）
    empty_response—— 返回空内容 / 无内容
    not_wired     —— 未接链 / 不可达 / 连接被拒
    rule_only     —— 全程规则兜底，未调 LLM（由调用方在"未失败"分支自行判定，本函数不返回）
    other         —— 其他未归类错误

判定顺序（严格，不可调换）：timeout → rate_limited → empty_response → not_wired → other

⚠️ 关键约束（night36-fix F1 修复点）：
    严禁使用裸 "rate" 子串匹配——会误命中 "gene**rate**"（如 'failed to generate response'），
    必须把限流信号限定为明确的 429 / rate limit / ratelimit / rate_limit / too many requests / 限流。
    'failed to generate response' 必须判为 other（不是 rate_limited）。
"""

__all__ = ["classify_ai_fail_reason"]

# rate_limited 仅认这些明确限流信号（不含裸 "rate"）
_RATE_LIMIT_TOKENS = ("429", "rate limit", "ratelimit", "rate_limit", "too many requests", "限流")

# not_wired：未接链 / 不可达 / 连接被拒
_NOT_WIRED_TOKENS = (
    "not wired", "未接", "offline", "不可达", "未连接", "not connected",
    "connection refused", "refused", "unreachable", "拒绝连接", "连接被拒",
)


def classify_ai_fail_reason(error: str) -> str:
    """把一段 LLM/AI 失败描述归一为统一枚举。

    Args:
        error: 失败描述文本（可为空；空串归为 other）。
    Returns:
        上述枚举字符串之一。
    """
    e = (error or "").lower()

    # 1) 超时（最优先，避免被其他关键词误命中）
    if "timeout" in e or "超时" in e:
        return "timeout"

    # 2) 限流：仅认明确限流信号，删除裸 "rate"（否则 gene**rate** 误命中）
    if any(tok in e for tok in _RATE_LIMIT_TOKENS):
        return "rate_limited"

    # 3) 空响应
    if "empty" in e or "空" in e or "无内容" in e or "no content" in e:
        return "empty_response"

    # 4) 未接 / 不可达 / 连接被拒
    if any(tok in e for tok in _NOT_WIRED_TOKENS):
        return "not_wired"

    # 5) 其他
    return "other"
