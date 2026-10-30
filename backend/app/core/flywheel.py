"""飞轮闭环基础（#653）。

最小但真实的闭环：在每次生成（S2 目标 / S3 图表叙事）过程中收集到的「反馈 / 经验」，
应反过来影响未来 S2 / S3 的生成，形成飞轮（feedback loop）。

数据底座：app.core.brain_modules.experience_store（按 (domain, 数据形态签名) 沉淀决策与结果）。
本模块只做三件事：
- get_flywheel_hints：把历史经验转成带权重的候选决策提示。
- build_flywheel_context：把提示拼成给人/模型读的中文短句。
- record_generation_outcome：把一次生成结果写回经验库。

注意：本模块不负责把 hints 注入 S2/S3（由调用方接线），此处只保证函数正确、可导入。
"""
from typing import Any, Dict, List, Optional

from app.core.brain_modules.experience_store import (
    record_experience,
    retrieve_experience,
)

# 飞轮经验库统一 domain（读/写路径必须一致，否则闭环无法对接）
FLYWHEEL_DOMAIN = "bi_dashboard"


def get_flywheel_hints(domain: str, data_signature: str, top_n: int = 3) -> List[Dict]:
    """检索历史经验，返回按采纳次数排序的带权重提示。

    每条 hint 形如：
        {"decision": str, "count": int, "good": int, "edited": int, "weight": float}
    权重 weight = good / (good + edited + 1)，越大代表该决策越被验证有效。
    """
    recs = retrieve_experience(domain, data_signature, top_n) or []
    hints: List[Dict] = []
    for r in recs:
        good = int(r.get("good", 0) or 0)
        edited = int(r.get("edited", 0) or 0)
        count = int(r.get("count", 0) or 0)
        weight = good / (good + edited + 1)
        hints.append({
            "decision": r.get("decision"),
            "count": count,
            "good": good,
            "edited": edited,
            "weight": weight,
        })
    return hints


def build_flywheel_context(domain: str, data_signature: str) -> str:
    """把历史经验拼成一句中文提示，供 S2/S3 生成时参考；无经验时返回空串。"""
    hints = get_flywheel_hints(domain, data_signature, top_n=3)
    if not hints:
        return ""
    parts = [
        f"历史经验：该数据形态下「{h['decision']}」被采纳 {h['good']} 次（权重 {h['weight']:.2f}）"
        for h in hints
    ]
    return "；".join(parts)


def record_generation_outcome(
    domain: str,
    data_signature: str,
    decision: str,
    outcome: str,
) -> Dict:
    """把一次生成决策的结果写回经验库。

    outcome: "good"（被采纳 / 低编辑 / 导出）| "edited"（被用户改掉，反向教材）。
    """
    return record_experience(domain, data_signature, decision, outcome)


def derive_signature(fields: List[str], grain: str = "") -> str:
    """从字段集合推导稳定的数据形态签名（排序后拼接，忽略顺序差异）。"""
    return f"{grain or 'detail'}#" + "|".join(sorted(set(fields or [])))


def build_flywheel_context_from_fields(
    fields: List[str], grain: str = "", domain: str = FLYWHEEL_DOMAIN
) -> str:
    """便捷封装：直接从字段推导签名并取历史经验上下文（供 S2/S3 生成时注入）。"""
    return build_flywheel_context(domain, derive_signature(fields, grain))
