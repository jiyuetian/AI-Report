# -*- coding: utf-8 -*-
"""字段名归一化（FIELD-NORM，2026-10-14）

背景（P0 真 bug）：S3 LLM 增强器对 AI 输出字段做**精确字符串**比对，
AI 输出 " 抵押率 "（带空格）或大小写/全角差异时，会被判"字段不存在" →
重试 2 次仍错 → 整批降级 rule_engine（绿标变灰标）。即 AI 明明答对却被错杀。

本模块提供"归一化 + 就近纠正"，让字段比对具备容错，并把纠正结果回写 config，
保证落库字段始终是数据集里的真实字段名。
"""
import re
from typing import Dict, List, Optional

_WS_RE = re.compile(r"[\s\u3000\u00a0]+")
_QUOTES = "\"'‘’“”`"

def normalize_field_name(name) -> str:
    """归一化：去空白/全角空格、去包裹引号、小写、去零宽字符"""
    s = str(name or "")
    s = s.replace("\u200b", "").replace("\ufeff", "")
    s = s.strip().strip(_QUOTES).strip()
    s = _WS_RE.sub("", s)
    # 去掉常见分隔符，避免 loan_amount / Loan-Amount / Loan Amount 互相判不上
    s = re.sub(r"[._\-()（）\[\]【】%％]+", "", s)
    return s.lower()

def resolve_field_name(name, available_fields) -> Optional[str]:
    """把 AI 输出的字段名解析为数据集中的真实字段名。

    匹配顺序：精确 → 归一化 → 去空白包含 → 前缀/后缀包含
    返回真实字段名；无法解析返回 None。
    """
    if not name or not available_fields:
        return None
    fields = list(available_fields)
    if name in fields:
        return name
    n = normalize_field_name(name)
    if not n:
        return None
    norm_map = {normalize_field_name(f): f for f in fields}
    if n in norm_map:
        return norm_map[n]
    # 去空白后的包含匹配（"抵押率(%)" vs "抵押率"）
    cands = [f for nf, f in norm_map.items() if n and (n in nf or nf in n)]
    if cands:
        return sorted(cands, key=len)[0]
    return None

def nearest_fields(name, available_fields, k: int = 3) -> List[str]:
    """给出最接近的 k 个真实字段名，用于把"失败原因"回传给 AI 自愈"""
    if not name or not available_fields:
        return []
    n = normalize_field_name(name)
    norm_map = {normalize_field_name(f): f for f in available_fields}
    scored = []
    for nf, f in norm_map.items():
        common = len(set(n) & set(nf))
        scored.append((-common, len(f), f))
    scored.sort()
    return [f for _, _, f in scored[:k]]

def normalize_chart_fields(config: Dict, available_fields: List[str]) -> Dict[str, str]:
    """就地纠正 config 里的字段引用，返回 {key: 纠正后的真实字段名}"""
    fixed: Dict[str, str] = {}
    if not isinstance(config, dict):
        return fixed
    for key in ("x_field", "y_field", "category_field", "value_field"):
        v = config.get(key)
        if not v:
            continue
        if v in available_fields:
            continue
        r = resolve_field_name(v, available_fields)
        if r:
            config[key] = r
            fixed[key] = r
    return fixed
