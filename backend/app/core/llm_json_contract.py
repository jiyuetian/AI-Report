# -*- coding: utf-8 -*-
"""LLM 结构化输出契约（#41，2026-11-16）。

背景：网关 `_extract_json` 只保证「能把 content 解析成合法 JSON」，并不保证形状符合
业务契约。模型偶发返回语义等价但形状不同的 JSON —— 顶层裸数组、包一层
result/data/output、别名键 problems/findings、issues 是对象或 null、数组里塞字符串等。
调用方若只认一种硬编码形状，就会把一次成功的 AI 调用误判成整链失败，正是
「AI 补充检测连续失败」的同类根因。

本模块提供三个纯函数（零 LLM / 零 DB / 零网络，可离线单测，任意 AI 链路可复用）：
- describe_shape(obj)            白盒描述真实形状，用于失败留痕与取证
- coerce_issues_payload(obj)     把语义等价形状归一为 issues 数组；返回 None 代表「无法确定」
- build_json_fix_messages(...)   构造一次确定性 JSON-FIX 对话（重新调用 AI，不靠规则补丁）

红线（与用户长期要求一致）：
- 「无法确定」与「确定为 0 个问题」严格区分：只有 issues 是 list（含空 list）或明确
  等价形状才返回 list；解析不出来一律返回 None，绝不伪装成 []。
- 归一只做形状映射，不改内容、不编造字段、不猜测语义；不可信形状交给调用方
  重新调用 AI 修复，仍不符才诚实判失败。
"""
import json
from typing import Any, List, Optional, Tuple

# 别名键（大小写不敏感）：模型偶尔把问题列表放在这些键下
_ALIAS_KEYS = {
    "issues", "problems", "findings", "results", "items", "data",
    "quality_issues", "anomalies", "issue_list", "problem_list",
    "问题", "异常", "异常项", "检测结果", "问题列表",
}
# 包一层的容器键
_WRAPPER_KEYS = (
    "result", "data", "output", "response", "payload", "results",
    "check_result", "结果", "检测结果",
)
# issues 为对象时，其内部承载数组的键
_OBJECT_ITEM_KEYS = ("items", "list", "records", "rows", "issues", "data")
# HTTP 200 实为失败的错误体（与 llm_gateway 的错误体判定同源）
_ERROR_KEYS = ("error", "error_code", "error_message", "errcode", "err_msg")


def describe_shape(obj: Any, _depth: int = 0) -> str:
    """白盒描述真实形状：类型、键名、长度、元素类型；截断防日志爆炸。"""
    if _depth > 3:
        return "..."
    if obj is None:
        return "null"
    if isinstance(obj, bool):
        return "bool(%s)" % obj
    if isinstance(obj, (int, float)):
        return type(obj).__name__
    if isinstance(obj, str):
        return "str[len=%d]" % len(obj)
    if isinstance(obj, list):
        elem = describe_shape(obj[0], _depth + 1) if obj else "-"
        return "list[len=%d, elem=%s]" % (len(obj), elem)
    if isinstance(obj, dict):
        parts = []
        for k, v in list(obj.items())[:8]:
            parts.append("%s=%s" % (k, describe_shape(v, _depth + 1)))
        more = "..." if len(obj) > 8 else ""
        return "dict(keys=%s%s)" % (",".join(parts), more)
    return type(obj).__name__


def _issue_list_or_none(value: Any) -> Tuple[Optional[List[dict]], Optional[str]]:
    """只接受 list，且元素必须全是 dict；空 list 视为「确定 0 个问题」。"""
    if not isinstance(value, list):
        return None, None
    if not value:
        return [], "empty_list"
    if all(isinstance(x, dict) for x in value):
        return list(value), "dict_list"
    return None, None


def coerce_issues_payload(obj: Any, _depth: int = 0) -> Tuple[Optional[List[dict]], Optional[str]]:
    """把语义等价的 LLM 输出归一为 issues 数组。

    返回 (issues, provenance)：
      issues=list   → 归一成功（空 list = 明确「无问题」）
      issues=None   → 形状无法确定，调用方必须做一次确定性 JSON-FIX 或诚实判失败
    provenance 记录归一来源，供白盒留痕：strict / wrapped:result / alias:problems /
    issues_object:items / toplevel_list / json_fix 等。
    """
    if _depth > 2:
        return None, None

    # ① 顶层裸数组：模型直接把问题列成数组（显式留痕，便于白盒取证）
    if isinstance(obj, list):
        inner, tag = _issue_list_or_none(obj)
        if inner is None:
            return None, None
        return inner, ("toplevel_empty" if tag == "empty_list" else "toplevel_list")

    if not isinstance(obj, dict):
        return None, None

    # ② 错误体：明确不是业务结果，不得当成「无问题」
    if any(k in obj for k in _ERROR_KEYS):
        return None, None

    # ③ 严格形状：{"issues": [...]}
    if "issues" in obj:
        got, tag = _issue_list_or_none(obj["issues"])
        if got is not None:
            return got, ("strict_empty" if tag == "empty_list" else "strict")
        v = obj["issues"]
        # {"issues": {"items": [...]}} —— 对象内承载数组
        if isinstance(v, dict):
            for k in _OBJECT_ITEM_KEYS:
                inner, itag = _issue_list_or_none(v.get(k))
                if inner is not None:
                    return inner, "issues_object:%s" % k
        # null / 字符串 / 对象都不猜，交给 JSON-FIX
        return None, None

    # ④ 包一层：{"result": {"issues": [...]}} 或 {"data": [...]}
    for wk in _WRAPPER_KEYS:
        if wk not in obj:
            continue
        w = obj[wk]
        if isinstance(w, dict):
            inner, tag = coerce_issues_payload(w, _depth + 1)
            if inner is not None:
                return inner, "wrapped:%s/%s" % (wk, tag)
        elif isinstance(w, list):
            inner, tag = _issue_list_or_none(w)
            if inner is not None:
                return inner, "wrapped_list:%s" % wk

    # ⑤ 顶层别名键：唯一一个数组且键名在别名白名单里才归一，避免多数组歧义
    alias_lists = [(k, v) for k, v in obj.items()
                   if isinstance(k, str) and k.lower() in _ALIAS_KEYS and isinstance(v, list)]
    if len(alias_lists) == 1:
        k, v = alias_lists[0]
        inner, tag = _issue_list_or_none(v)
        if inner is not None:
            return inner, "alias:%s" % k
    return None, None


_FIX_INSTRUCTION = (
    "你上一次的输出不是约定的 JSON 形状。请【原样保留你已经判断出的问题内容】，"
    "只把外层结构改写成严格的顶层对象 {\"issues\":[...]}：\n"
    "- 顶层必须且只能是这个对象，不要包进 result/data/output，不要返回裸数组；\n"
    "- issues 必须是数组，数组里每个元素都是对象；确实没有新问题就返回 {\"issues\":[]}；\n"
    "- 不要返回 null、字符串、解释文字，不要写 Markdown 代码块围栏；\n"
    "- 不要增删问题、不要改字段名、不要改字段值、不要改中文结论；只做结构改写；\n"
    "- 直接以 { 开头、以 } 结尾输出这一个 JSON 对象。"
)


def build_json_fix_messages(original_prompt: str, bad_payload: Any,
                            shape: Optional[str] = None) -> List[dict]:
    """构造一次确定性 JSON-FIX 对话：系统约束 + 原 prompt + 模型真实输出 + 修复指令。

    这是「重新调用 AI 按契约重发」，不是规则补丁、不是静默吞掉，也不是随机重试；
    同输入同指令可复现。调用方只允许执行一次。
    """
    try:
        bad_text = json.dumps(bad_payload, ensure_ascii=False, default=str)[:2000]
    except Exception:
        bad_text = str(bad_payload)[:2000]
    hint = ("你上一次输出的真实形状是：%s。" % shape) if shape else ""
    return [
        {"role": "system",
         "content": "你是 JSON 结构化输出修复器。只输出严格合法的一个 JSON 对象，"
                    "不要解释文字、不要代码块围栏、不要推理过程。"},
        {"role": "user", "content": original_prompt},
        {"role": "assistant", "content": bad_text},
        {"role": "user", "content": hint + _FIX_INSTRUCTION},
    ]
