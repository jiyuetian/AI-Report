# -*- coding: utf-8 -*-
"""对话改看板 · AI 全节点治理编排器（Task #701 · 2026-11-12）。

项目设计真意（权限矩阵 v2）：L1-L4「最高权限 = 每层检查确认结果 + 直接修改编辑(增删改查)」，
护栏四件套 = 走规则引擎 API / 血缘白盒 / ai_action_log 十项留痕 / 改前存回退点。
**兜底只是地基，AI 参与才是完整产品功能；规则是辅助 AI 的，不是审批者。**

本模块把「对话改看板」从「规则分类 → 规则规划 → 规则可行性一票否决 → 执行」
改成五个节点全部由 AI 把关：

  N1 understand  AI 理解原话、拆出要办的事（含口语字段→真实字段的语义判断）
  N2 plan        AI 把每件事规划成真实字段/图型/聚合的图表规格
  N3 execute     AI 以最高 CRUD 权限签发 add/update/delete/query 变更（含改现有图）
  N4 verify      AI 对照原话自检：数量、字段真实性、是否空图、是否臆造标题、是否满足要求
  N5 revise      AI 有疑问随时调整：把 verify 的 questions 回灌，自己重出变更（最多 2 轮）

规则的位置：
  * 只在 **AI 链路整体不可用** 时兜底，且必须显式 by='rule_fallback' + failure_reason + 可重试；
  * 不再有「规则可行性检查」抢在 AI 前面否决；
  * 真正落库仍走 ActionExecutor（规则引擎 API 护栏），AI 是决策者而非绕过护栏。

护栏四件套在本模块的落点：
  1) 走规则引擎 API：产出统一转成 ActionExecutor 的 type/params，由 chat.py 执行；
  2) 血缘白盒：context.lineage 注入每个节点 prompt，patch 带 lineage_source；
  3) ai_action_log 十项留痕：每个节点一条（含自校正轮次），run_id 串起全链；
  4) 改前回退点：返回 rollback_point_required，由 chat.py 落库前打 VersionManager 快照。
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from app.core.ai_budget import (
    MAX_SELF_CORRECTIONS, NodeTimer, budget_for, chain_budget,
    chain_summary, failed_result, node_result,
)
from app.core.ai_action_log import log_ai_action
from app.core.prompt_loader import load_prompt
from app.core.llm_gateway import _extract_json, llm_chat

_SYSTEM_DEFAULT = "你是看板配置的 AI 主控（最高权限：增删改查）。规则引擎只是你的执行器与兜底，不是你的审批者。你必须自己理解用户语义、自己判断字段、自己签发变更、自己验收并纠错。只返回合法 JSON，不要解释文字、不要推理过程、不要代码块围栏。"


def _system() -> str:
    """系统人设走提示词中心 ai_governor_system 板块；中心/文件不可用时回退内联默认。"""
    return load_prompt("ai_governor_system", _SYSTEM_DEFAULT)


_NODE_LABEL = {
    "understand": "理解意图与拆解事项",
    "plan": "规划图表规格与字段映射",
    "execute": "签发增删改查变更",
    "verify": "自检验收",
    "revise": "按疑问自我调整",
}

# 五节点默认模板与 prompts/ai_governor_*.md 种子逐字一致：外置生效，内联仅作兜底。
# 管理员在「管理中心 → Prompt 中心」编辑 ai_governor_* 板块后，下一次对话立即生效，无需重启。
_D_UNDERSTAND = "【本次上下文与用户原话】\n{context_block}\n\n【节点1·理解】请你自己理解这句话要做什么，列出全部要办的事项（一个都不能漏），并把口语说法映射到真实字段。返回：\n{\"intent\":\"add_chart|change_chart|delete_chart|query|regenerate_dashboard|chat\",\"items\":[{\"name\":\"用户说法\",\"real_field\":\"真实字段名或空\",\"aggregation\":\"count|sum|avg|空\",\"op\":\"add|update|delete|query\",\"target_chart_id\":\"改/删现有图时填id，否则空\"}],\"understanding\":\"一句话复述你的理解\",\"questions\":[]}\n"
_D_PLAN = "【本次上下文与用户原话】\n{context_block}\n\n{node_input}\n\n【节点2·规划】请把每个事项规划成具体图表规格。规则：\n① 每个事项单独一张图，title 用该事项的简短名称，禁止把整串原话当标题；\n② chart_type 只能是 kpi|bar|line|pie|table，指标卡/卡片/总计卡一律用 kpi；\n③ y_field 必须是字段清单里的真实字段名；kpi 不要 x_field；\n④ 文本/标识类字段做指标时 aggregation 用 count，数值字段按语义用 sum 或 avg；\n⑤ update/delete 必须带 target_chart_id。返回：\n{\"patches\":[{\"op\":\"add|update|delete|query\",\"chart\":{\"title\":\"\",\"chart_type\":\"kpi\",\"y_field\":\"\",\"x_field\":\"\",\"aggregation\":\"count\",\"target_chart_id\":\"\"}}],\"notes\":\"\"}\n"
_D_EXECUTE = "【本次上下文与用户原话】\n{context_block}\n\n{node_input}\n\n【节点3·签发】你拥有看板配置的最高增删改查权限。请复核并签发最终变更：可以新增、修改、删除现有图表，也可以撤回规划里不合理的项。\n【#42 硬约束】节点1 点名的每个 op=add 事项都必须签发，不得因字段类型或形态偏好撤回；可改图表形态，不可删项。\n规则引擎只负责执行你的决定，不会替你审批。返回：\n{\"approved_patches\":[{\"op\":\"add|update|delete|query\",\"chart\":{...}}],\"crud_summary\":\"你做了哪些增删改查\",\"dropped\":[]}\n"
_D_VERIFY = "【本次上下文与用户原话】\n{context_block}\n\n{node_input}\n\n【节点4·自检】请你对照用户原话自己验收，重点检查：\n① 用户列举的每一项是否都有对应图表，数量是否一致；\n② 每张图的 y_field 是否真实存在、是否会产生「无可绘制数据」的空图；\n③ kpi 是否误带分类轴、文本指标是否用 count；\n④ 标题是否为臆造（如「按XX分布」这类用户没说的组合）；\n⑤ 是否满足原话全部要求。\n【#42 硬约束】用户明确点名的每一项都必须保留；字段是文本/维度/时间类型不构成否决理由，\n可以在 questions 里提形态建议，但不得因此判 ok=false，也不得删掉对应 patch。\nok=false 只允许因漏项、字段不存在、目标图 id 不存在、空图、动作不符、标题臆造。\n有疑问就写进 questions 并给出 fixes，不要交给规则、不要直接拒绝用户。返回：\n{\"ok\":true/false,\"questions\":[\"...\"],\"fixes\":[\"...\"],\"coverage\":\"已覆盖x/y项\"}\n"
_D_REVISE = "【本次上下文与用户原话】\n{context_block}\n\n{node_input}\n\n【节点5·自我调整】请你自己改好（有疑问随时调整，不需要问用户、不需要规则批准），直接返回完整最终版。\n【#42 硬约束】返回完整最终版时必须覆盖节点1 的全部点名项；只改 chart_type/aggregation/x_field/title 措辞，\n不得删除、合并或漏掉任何一项；形态建议写进 changes，不要删 patch。返回：\n{\"patches\":[{\"op\":\"add|update|delete|query\",\"chart\":{...}}],\"changes\":\"你改了什么\"}\n"


# ── #39 变更契约护栏（2026-11-16）──────────────────────────────────────────
# 定位：护栏，不是审批者。判断依据来自 AI 自己节点1 的理解，图表规格来自 AI 节点2/3 的签发；
# 这里只把「不可执行 / 违背 AI 自己意图」的载体修正为可执行形态，并白盒留痕。
_PATCH_CONTRACT = '## 变更契约（强制；违反的 patch 视为不可执行）\n- 当用户原话是「新增/添加 N 个卡片、图表」且节点1 的每个事项 op=add 时，所有 patch 的 op 必须保持 add；\n  禁止把新增项改成 update/delete 指向已有图表，也禁止漏掉任何一项。\n- op=update/delete 必须填写一个在「当前看板图表」里真实存在的 target_chart_id；\n  禁止臆造 id，也禁止只写 chart.id 而不写 target_chart_id。\n- 节点4 验收必须逐条核对「动作类型是否与节点1 的 op 一致」与「目标图 id 是否真实存在」，\n  不能只按字段数量判 ok=true。\n'


def _known_chart_ids(context: Dict[str, Any]) -> set:
    """当前看板真实存在的图表 id（唯一可信来源 = 上下文 current_config）。"""
    out = set()
    for ch in (((context.get("current_config") or {}).get("charts")) or []):
        if isinstance(ch, dict) and ch.get("id") not in (None, ""):
            out.add(str(ch.get("id")))
    return out


def _is_pure_additive(understood: Dict[str, Any]) -> bool:
    """节点1 是否判定为「纯新增」：每个事项的 op 都是 add。混合意图一律不算。"""
    items = [x for x in (understood.get("items") or []) if isinstance(x, dict)]
    if not items:
        return (understood.get("intent") or "").lower() == "add_chart"
    return all(str(x.get("op") or "add").lower() == "add" for x in items)


def _resolve_target_id(chart: Dict[str, Any]) -> str:
    """AI 会把目标图 id 写在不同字段，统一解析（修 _to_plan 丢 id 的根因）。"""
    for k in ("target_chart_id", "id", "chart_id"):
        v = chart.get(k)
        if v not in (None, ""):
            return str(v)
    return ""


def patch_contract_issues(patches: List[Dict], understood: Dict[str, Any],
                          context: Dict[str, Any]) -> List[str]:
    """纯函数：列出不可执行 / 违背节点1 意图的 patch，只产出事实，不替 AI 决策。"""
    ids = _known_chart_ids(context)
    additive = _is_pure_additive(understood)
    issues: List[str] = []
    for i, p in enumerate(patches):
        if not isinstance(p, dict):
            continue
        op = str(p.get("op") or "add").lower()
        ch = p.get("chart") if isinstance(p.get("chart"), dict) else {}
        tid = _resolve_target_id(ch)
        if additive and op in ("update", "delete"):
            issues.append("第%d项 op=%s 指向已有图(id=%s)，与节点1 全部 op=add 的新增意图冲突"
                          % (i + 1, op, tid or "空"))
        if op in ("update", "delete"):
            if not tid:
                issues.append("第%d项 op=%s 缺少目标图 id，执行器无法定位" % (i + 1, op))
            elif tid not in ids:
                issues.append("第%d项 目标图 id=%s 不在当前看板真实 id 清单里（臆造 id）"
                              % (i + 1, tid))
    return issues


def enforce_patch_contract(patches: List[Dict], understood: Dict[str, Any],
                           context: Dict[str, Any]) -> Tuple[List[Dict], List[str]]:
    """结构性护栏：只修载体，规格(标题/字段/图型/聚合)全部沿用 AI 原样。

    纯新增意图下把误签的 update/delete 改回 add；非纯新增时把写在 id 上的真实目标
    id 补到 target_chart_id。绝不新增/删除 AI 没签发过的图表规格。
    """
    ids = _known_chart_ids(context)
    additive = _is_pure_additive(understood)
    out: List[Dict] = []
    notes: List[str] = []
    for i, p in enumerate(patches):
        if not isinstance(p, dict):
            continue
        op = str(p.get("op") or "add").lower()
        ch = dict(p.get("chart") or {}) if isinstance(p.get("chart"), dict) else {}
        tid = _resolve_target_id(ch)
        if additive and op in ("update", "delete"):
            q = dict(p)
            q["op"] = "add"
            for k in ("id", "target_chart_id", "chart_id"):
                ch.pop(k, None)
            q["chart"] = ch
            out.append(q)
            notes.append("第%d项 %s(id=%s) → add：节点1 判定纯新增，保留 AI 图表规格改为新增"
                         % (i + 1, op, tid or "空"))
            continue
        if op in ("update", "delete") and tid and tid in ids \
                and not ch.get("target_chart_id"):
            ch["target_chart_id"] = tid
            q = dict(p)
            q["chart"] = ch
            out.append(q)
            notes.append("第%d项 补回 target_chart_id=%s（AI 原写在 id/chart_id 字段）"
                         % (i + 1, tid))
            continue
        out.append(p)
    return out, notes


# ── #42 用户点名项守恒（2026-11-16）────────────────────────────────────────
# 定位：护栏，不是审批者。验收基准取自 AI 自己节点1 的 items，补回规格取自 AI 自己
# 节点2/3 的 patch；这里只做「一对一守恒核验 + 确定性补回 + 白盒留痕」，不替 AI 决策。
_ITEM_CONTRACT = '## 用户点名项守恒（强制；优先级高于字段形态偏好）\n- 节点1 拆出的每个 op=add 事项，都是用户明确点名的交付物；节点3/4/5 一律不得删除、合并或漏掉任何一项。\n  只允许调整 chart_type / aggregation / x_field / title 措辞等图表形态，必须保留对应图表。\n- 字段是文本 / 维度 / 时间类型，不构成否决理由：用户点名要它就必须保留；\n  可以在 questions 或 changes 里提形态建议（改维度轴 / 筛选器），但不得因此把 ok 判为 false 或删图。\n- 节点4 的 ok=false 只允许因事实错误：漏项、字段名不存在、目标图 id 不存在、\n  会产生无绘制数据的空图、动作类型与节点1 不一致、标题臆造。\n- 节点5 返回完整最终版时，patch 必须覆盖节点1 的全部点名项；只改形态不删项。\n'


def _norm_key(v: Any) -> str:
    """字段/标题归一：去空白、转小写，避免 AI 措辞微变导致误判缺项。"""
    return str(v if v is not None else "").strip().lower().replace(" ", "").replace("\u3000", "")


def _item_keys(item: Dict[str, Any]) -> set:
    out = set()
    for k in ("real_field", "name", "field", "y_field", "metric_field"):
        v = _norm_key(item.get(k))
        if v:
            out.add(v)
    return out


def _patch_keys(p: Dict[str, Any]) -> set:
    ch = p.get("chart") if isinstance(p.get("chart"), dict) else {}
    out = set()
    for k in ("y_field", "metric_field", "title", "name"):
        v = _norm_key(ch.get(k))
        if v:
            out.add(v)
    return out


def _add_patches(patches: List[Dict]) -> List[Dict]:
    return [p for p in patches if isinstance(p, dict)
            and str(p.get("op") or "add").lower() == "add"]


def missing_required_items(patches: List[Dict], understood: Dict[str, Any],
                           context: Dict[str, Any]) -> List[Dict]:
    """纯函数：一对一贪心核验用户点名项是否都有独立 add 图。

    只在「节点1 判定纯新增且确实列出事项」时生效；混合意图/闲聊不误伤。
    一个 patch 只能认领一个点名项 —— 这样「6 项被合并成 1 张概览图」也算漏项，
    不会因标题里含全部字段名而侥幸判守恒。
    """
    items = [x for x in (understood.get("items") or []) if isinstance(x, dict)]
    if not items or not _is_pure_additive(understood):
        return []
    adds = _add_patches(patches)
    matched = {}
    used = set()
    # 第一轮：字段名/标题精确交集
    for i, it in enumerate(items):
        ik = _item_keys(it)
        if not ik:
            continue
        for j, p in enumerate(adds):
            if j in used or not (ik & _patch_keys(p)):
                continue
            used.add(j)
            matched[i] = j
            break
    # 第二轮：标题包含点名字段（如「业务流程合规率（均值）」）
    for i, it in enumerate(items):
        if i in matched:
            continue
        ik = _item_keys(it)
        for j, p in enumerate(adds):
            if j in used:
                continue
            ch = p.get("chart") if isinstance(p.get("chart"), dict) else {}
            t = _norm_key(ch.get("title"))
            if t and any(len(k) >= 2 and k in t for k in ik):
                used.add(j)
                matched[i] = j
                break
    out = []
    for i, it in enumerate(items):
        if i not in matched and _item_keys(it):
            out.append({"index": i, "item": it, "keys": sorted(_item_keys(it))})
    return out


def _majority_chart_type(specs: List[Dict]) -> str:
    cnt: Dict[str, int] = {}
    for p in specs:
        ch = p.get("chart") if isinstance(p.get("chart"), dict) else {}
        v = _norm_key(ch.get("chart_type"))
        if v in ("kpi", "bar", "line", "pie", "table"):
            cnt[v] = cnt.get(v, 0) + 1
    return max(cnt, key=cnt.get) if cnt else "kpi"


def enforce_item_conservation(patches: List[Dict], understood: Dict[str, Any],
                              context: Dict[str, Any],
                              known_specs: Optional[List[Dict]] = None
                              ) -> Tuple[List[Dict], List[Dict], List[str]]:
    """确定性补回被 N4/N5 删掉的用户点名项；规格优先复用 AI 自己签发的 patch。

    返回 (new_patches, restored_records, notes)。绝不臆造字段名：节点1 没有
    real_field/name 的项宁可留痕不补，也不生成空图。
    """
    miss = missing_required_items(patches, understood, context)
    if not miss:
        return list(patches), [], []
    pool = list(known_specs or []) + [p for p in patches if isinstance(p, dict)]
    ctype = _majority_chart_type(pool)
    out = list(patches)
    restored: List[Dict] = []
    notes: List[str] = []
    for m in miss:
        it = m["item"]
        keys = set(m["keys"])
        src = None
        for p in pool:
            if keys & _patch_keys(p):
                c = p.get("chart")
                if isinstance(c, dict) and _norm_key(c.get("y_field") or c.get("metric_field")):
                    src = c
                    break
        if src is not None:
            ch = dict(src)
            for k in ("target_chart_id", "id", "chart_id"):
                ch.pop(k, None)
            origin = "ai_patch_spec"
        else:
            field = str(it.get("real_field") or it.get("name") or "").strip()
            if not field:
                continue
            ch = {
                "title": str(it.get("name") or field).strip(),
                "chart_type": ctype,
                "y_field": field,
                "x_field": "",
                "aggregation": str(it.get("aggregation") or "").strip() or "count",
            }
            origin = "ai_n1_item"
        out.append({"op": "add", "chart": ch})
        label = str(it.get("name") or it.get("real_field") or "点名项")
        restored.append({"index": m["index"], "item": label,
                         "source": origin, "chart": ch})
        notes.append("第%d项「%s」被 AI 改版删除/漏掉，按节点1 点名项守恒补回（规格来源=%s）"
                     % (m["index"] + 1, label, origin))
    return out, restored, notes


def _render(node: str, default: str, context_block: str, **extra) -> str:
    """统一从提示词中心渲染节点指令，并兜住「覆盖文案删掉占位符」导致的数据丢失。"""
    kw = {"context_block": context_block}
    kw.update(extra)
    text = load_prompt("ai_governor_%s" % node, default, **kw)
    if context_block and context_block not in text:
        text += "\n【本次上下文与用户原话（自动补回）】\n" + context_block
    for k, v in extra.items():
        if v and str(v) not in text:
            text += "\n【%s（自动补回）】\n%s" % (k, v)
    # #39：变更契约必须随每次渲染下发，Prompt 中心的旧管理员覆盖也抹不掉
    if node in ("plan", "execute", "verify", "revise") and _PATCH_CONTRACT not in text:
        text += "\n" + _PATCH_CONTRACT
    # #42：守恒契约必须随每次渲染下发，Prompt 中心的旧管理员覆盖也抹不掉
    if node in ("plan", "execute", "verify", "revise") and _ITEM_CONTRACT not in text:
        text += "\n" + _ITEM_CONTRACT
    return text


def _fields_desc(context: Dict[str, Any], limit: int = 30) -> str:
    fps = ((context.get("dataset_info") or {}).get("field_profiles") or [])
    out = []
    for fp in fps[:limit]:
        if isinstance(fp, dict):
            nm = fp.get("name") or fp.get("column") or ""
            typ = fp.get("type") or fp.get("dtype") or fp.get("data_type") or ""
            out.append(f"{nm}({typ})" if typ else str(nm))
        else:
            out.append(str(fp))
    return ", ".join(out) or "（无字段画像）"


def _charts_desc(context: Dict[str, Any], limit: int = 30) -> str:
    charts = ((context.get("current_config") or {}).get("charts") or [])
    out = []
    for c in charts[:limit]:
        out.append({
            "id": c.get("id"), "title": c.get("title"),
            "chart_type": c.get("chart_type"),
            "y_field": c.get("y_field") or c.get("value_field"),
            "x_field": c.get("x_field") or c.get("category_field"),
        })
    return json.dumps(out, ensure_ascii=False) if out else "[]"


def _lineage_desc(context: Dict[str, Any], limit: int = 350) -> str:
    try:
        s = json.dumps(context.get("lineage") or {}, ensure_ascii=False, default=str)
    except Exception:
        s = str(context.get("lineage") or "")
    return s[:limit]


def _history_desc(context: Dict[str, Any], limit: int = 250) -> str:
    try:
        s = json.dumps(context.get("history") or [], ensure_ascii=False, default=str)
    except Exception:
        s = str(context.get("history") or "")
    return s[:limit]


async def _log_node(
    node: str, *, session_id, dashboard_id, user_id, run_id,
    status: str, latency_ms: int, payload: Any = None, error: Optional[str] = None,
    round_no: int = 0,
) -> None:
    """ai_action_log 十项留痕：每个 AI 节点一条（自校正轮次带 round_no）。"""
    await log_ai_action(
        session_id=session_id, dashboard_id=dashboard_id, user_id=user_id,
        run_id=run_id, intent="ai_govern_%s" % node,
        action_type="ai_node_%s" % node,
        params_summary={
            "node": node, "label": _NODE_LABEL.get(node, node),
            "round": round_no, "payload": payload,
        },
        result_status=status, error_msg=error,
        llm_layer="ai_governor", latency_ms=latency_ms,
    )


async def _ai_node(
    node: str, prompt: str, *, session_id, dashboard_id, user_id, run_id,
    round_no: int = 0, deadline: Optional[float] = None,
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """统一 AI 节点调用：预算来自 ai_budget，失败不抛、返回带原因的 node_result。"""
    timer = NodeTimer()
    b = budget_for(node)
    if deadline is not None:
        # Task #728/#33：单节点不得吃光整链预算；按链路剩余时间收敛（与 S3 同一口径）。
        # 预算耗尽时 timeout 仍保留 2s，让失败原因诚实落到 node_result，而不是被外层静默截断。
        left = deadline - time.monotonic()
        b["timeout"] = max(2, min(int(b["timeout"]), int(left)))
    try:
        resp = await asyncio.wait_for(
            llm_chat(
                messages=[
                    {"role": "system", "content": _system()},
                    {"role": "user", "content": prompt},
                ],
                json_mode=True,
                # Task #728/#33：b["timeout"] 是「整次调用总预算」而不是单次上限。
                # 单次最多等 45s（网关实测慢响应可达 53s，含一次 failover），
                # 超时后由 total_deadline 把剩余时间收敛给下一层 provider。
                timeout=float(min(45, b["timeout"])),
                total_timeout=float(b["timeout"]),
                # 同一 provider 不再重试（旧 max_retries=1 会 45s 超时 + 8s 退避再等
                # 45s，直接把整份预算吃光）。把机会让给跨 provider failover。
                max_retries=0,
                max_tokens=int(b["max_tokens"]),
                user_id=str(user_id or ""),
            ),
            timeout=b["timeout"] + 3,
        )
        data = resp.response_json if isinstance(resp.response_json, dict) else _extract_json(resp.content or "")
        if not isinstance(data, dict):
            data = {"items": data} if isinstance(data, list) else None
        if not data or getattr(resp, "fallback_used", False):
            raise RuntimeError("LLM 未产出结构化结果或走了兜底: %s" % str(getattr(resp, "error", ""))[:120])
        r = node_result(node, by="ai", llm_called=True,
                        attempts=int(getattr(resp, "retry_count", 0) or 0) + 1,
                        self_corrected=(node == "revise"), latency_ms=timer.ms)
        await _log_node(node, session_id=session_id, dashboard_id=dashboard_id,
                        user_id=user_id, run_id=run_id, status="success",
                        latency_ms=timer.ms, payload=data, round_no=round_no)
        return data, r
    except Exception as e:
        reason = "%s: %s" % (type(e).__name__, str(e)[:180])
        print(f"[AI-GOVERN] 节点 {node} 第{round_no}轮 AI 不可用: {reason}")
        r = node_result(node, by="rule_fallback", llm_called=False,
                        reason=reason, latency_ms=timer.ms, fallback_used=True)
        await _log_node(node, session_id=session_id, dashboard_id=dashboard_id,
                        user_id=user_id, run_id=run_id, status="failed",
                        latency_ms=timer.ms, error=reason, round_no=round_no)
        return None, r


def _common(message: str, context: Dict[str, Any]) -> str:
    return (
        f"用户原话：{message}\n"
        f"真实字段清单（只能用这里的名字，禁止编造）：{_fields_desc(context)}\n"
        f"当前看板图表（可增删改查）：{_charts_desc(context)}\n"
        f"血缘快照：{_lineage_desc(context)}\n"
        f"最近对话：{_history_desc(context)}\n"
    )


def _p_understand(message: str, context: Dict[str, Any]) -> str:
    return _render("understand", _D_UNDERSTAND, _common(message, context))


def _p_plan(message: str, context: Dict[str, Any], understood: Dict[str, Any]) -> str:
    return _render("plan", _D_PLAN, _common(message, context),
                   node_input="【节点1的理解】" + json.dumps(understood, ensure_ascii=False)[:900])


def _p_execute(message: str, context: Dict[str, Any], planned: Dict[str, Any]) -> str:
    return _render("execute", _D_EXECUTE, _common(message, context),
                   node_input="【节点2的规划】" + json.dumps(planned, ensure_ascii=False)[:1200])


def _p_verify(message: str, context: Dict[str, Any], patches: List[Dict],
              contract_notes: Optional[List[str]] = None,
              item_fact: Optional[Dict[str, Any]] = None,
              conservation_notes: Optional[List[str]] = None) -> str:
    # #42：6+ 项长清单不再被 1400 字符截断，否则 N4 看不到全部点名项会误判漏项/删项。
    inp = "【待验收变更（完整清单）】" + json.dumps(patches, ensure_ascii=False)[:6000]
    if item_fact:
        inp += "\n【用户点名项守恒事实（确定性核验，优先于任何字段形态偏好）】" + \
               json.dumps(item_fact, ensure_ascii=False)[:1200]
    if contract_notes:
        inp += "\n【变更契约护栏白盒记录（纳入你的验收）】" + \
               json.dumps(contract_notes, ensure_ascii=False)[:2000]
    if conservation_notes:
        inp += "\n【点名项守恒护栏白盒记录（这些项已按用户原话补回，不得再删）】" + \
               json.dumps(conservation_notes, ensure_ascii=False)[:2000]
    return _render("verify", _D_VERIFY, _common(message, context), node_input=inp)


def _p_revise(message: str, context: Dict[str, Any], patches: List[Dict],
              questions: List[str], fixes: List[str],
              contract_notes: Optional[List[str]] = None,
              conservation_notes: Optional[List[str]] = None) -> str:
    # #42：长清单不再被 2200 字符截断，N5 必须看到全部点名项才不会误删。
    inp = ("【上一版变更（完整清单）】" + json.dumps(patches, ensure_ascii=False)[:9000]
           + "\n【你自检发现的疑问】" + json.dumps(questions, ensure_ascii=False)[:1600]
           + "\n【你给的修正意见】" + json.dumps(fixes, ensure_ascii=False)[:1600])
    if contract_notes:
        inp += "\n【变更契约护栏白盒记录（不要再改回不可执行的形态）】" + \
               json.dumps(contract_notes, ensure_ascii=False)[:2000]
    if conservation_notes:
        inp += "\n【点名项守恒护栏白盒记录（用户点名的项一律不得删除）】" + \
               json.dumps(conservation_notes, ensure_ascii=False)[:2000]
    return _render("revise", _D_REVISE, _common(message, context), node_input=inp)


def _to_plan(understood: Dict[str, Any], patches: List[Dict],
             governance: Dict[str, Any]) -> Dict[str, Any]:
    """把 AI 签发的 CRUD patches 适配成 ActionExecutor 的 type/params（护栏①：走规则引擎 API）。
    这里只做结构适配，不做「字段是否合法」的规则审批——判断权属于 AI。"""
    add_specs: List[Dict[str, Any]] = []
    actions: List[Dict[str, Any]] = []
    for p in patches:
        if not isinstance(p, dict):
            continue
        op = (p.get("op") or "add").lower()
        ch = p.get("chart") if isinstance(p.get("chart"), dict) else {}
        # #39：AI 可能把目标图 id 写在 target_chart_id / id / chart_id 任一字段
        tid = _resolve_target_id(ch)
        src = {
            "title": (ch.get("title") or "").strip(),
            "chart_type": (ch.get("chart_type") or "kpi").strip().lower(),
            "metric_field": (ch.get("y_field") or ch.get("metric_field") or "").strip(),
            "dimension_field": (ch.get("x_field") or "").strip(),
            "aggregation": (ch.get("aggregation") or "").strip() or None,
        }
        src["lineage_source"] = "ai_governor"
        # AI 掌权：AI 定的标题就是最终标题，规则不得按「口语片段」改写
        src["preserve_title"] = True
        if op == "add":
            add_specs.append(src)
        elif op == "update":
            actions.append({
                "type": "change_chart",
                "params": {"chart_id": tid,
                           "title": ch.get("title"), "chart_spec": src},
                "clause": ch.get("title"), "classified_by": "llm_governor",
            })
        elif op == "delete":
            actions.append({
                "type": "delete_chart",
                "params": {"chart_id": tid,
                           "title": ch.get("title")},
                "clause": ch.get("title"), "classified_by": "llm_governor",
            })
        elif op == "query":
            actions.append({
                "type": "calculate_metric",
                "params": {"metric_field": src["metric_field"],
                           "aggregation": src["aggregation"] or "count"},
                "clause": ch.get("title"), "classified_by": "llm_governor",
            })
    if add_specs:
        actions.insert(0, {
            "type": "add_chart",
            "params": {"charts": add_specs},
            "clause": understood.get("understanding") or "",
            "classified_by": "llm_governor",
        })

    intent = (understood.get("intent") or "").lower()
    if intent not in ("add_chart", "change_chart", "delete_chart", "query",
                      "regenerate_dashboard", "chat", "clarify"):
        intent = "add_chart" if actions else "chat"
    if intent == "add_chart" and not actions:
        intent = "chat"

    return {
        "primary_intent": {
            "intent_type": intent,
            "confidence": 0.95,
            "is_confident": True,
            "classified_by": "llm_governor",
            "analysis": {
                "extracted_params": {"charts": add_specs},
                "understanding": understood.get("understanding"),
                "items": understood.get("items") or [],
            },
        },
        "actions": actions,
        "is_compound": len(actions) > 1 or len(add_specs) > 1,
        "clauses": [a.get("clause") for a in actions],
        "unparsed_clauses": [],
        "ai_governance": governance,
    }


async def govern(
    message: str,
    context: Dict[str, Any],
    *,
    session_id: Optional[str] = None,
    dashboard_id: Optional[str] = None,
    user_id: Optional[str] = None,
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """AI 五节点治理主入口。返回 chat.py 可直接消费的 plan 兼容结构 + governance。

    全链 AI 不可用时返回 by='rule_fallback'，由调用方走规则兜底并显式标注。
    """
    run_id = run_id or ("aigov_" + uuid.uuid4().hex[:16])
    deadline = time.monotonic() + chain_budget("chat")
    nodes: List[Dict[str, Any]] = []
    trace: List[Dict[str, Any]] = []

    async def run_node(node: str, prompt: str, round_no: int = 0):
        data, r = await _ai_node(
            node, prompt, session_id=session_id, dashboard_id=dashboard_id,
            user_id=user_id, run_id=run_id, round_no=round_no,
            deadline=deadline,
        )
        nodes.append(r)
        trace.append({"node": node, "round": round_no, "by": r["by"],
                      "reason": r.get("reason"), "latency_ms": r["latency_ms"]})
        return data

    try:
        return await asyncio.wait_for(
            _govern_inner(message, context, run_id, nodes, trace, run_node,
                          session_id=session_id, dashboard_id=dashboard_id,
                          user_id=user_id),
            timeout=chain_budget("chat"),
        )
    except asyncio.TimeoutError:
        reason = "AI 治理链路超过总闸 %ss" % chain_budget("chat")
        nodes.append(node_result("chat", by="rule_fallback", llm_called=False,
                                 reason=reason, fallback_used=True))
        return _fallback(reason, chain_summary(nodes, chain="chat"), run_id, trace)
    except Exception as e:
        reason = "%s: %s" % (type(e).__name__, str(e)[:200])
        nodes.append(node_result("chat", by="rule_fallback", llm_called=False,
                                 reason=reason, fallback_used=True))
        return _fallback(reason, chain_summary(nodes, chain="chat"), run_id, trace)


def _fallback(reason: str, summary: Dict[str, Any], run_id: str,
              trace: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "ok": False, "by": "rule_fallback", "plan": None,
        "governance": summary, "run_id": run_id,
        "rollback_point_required": False, "failure_reason": reason,
        "trace": trace,
    }


async def _govern_inner(
    message: str, context: Dict[str, Any], run_id: str,
    nodes: List[Dict[str, Any]], trace: List[Dict[str, Any]], run_node,
    *, session_id, dashboard_id, user_id,
) -> Dict[str, Any]:
    # ── N1 理解（AI 主控）──
    understood = await run_node("understand", _p_understand(message, context))
    if not understood:
        return _fallback("节点1 理解：AI 不可用", chain_summary(nodes, chain="chat"), run_id, trace)

    # ── N2 规划（AI 主控）──
    planned = await run_node("plan", _p_plan(message, context, understood))
    patches = list((planned or {}).get("patches") or []) if planned else []
    # #42：AI 自己签发的图表规格是守恒补回的唯一规格来源，护栏不臆造规格。
    known_specs: List[Dict] = [dict(p) for p in patches if isinstance(p, dict)]

    # ── N3 签发（AI 拥有最高 CRUD 权限）──
    signed = await run_node("execute", _p_execute(message, context, {"patches": patches}))
    if signed and isinstance(signed.get("approved_patches"), list):
        patches = signed["approved_patches"]
    known_specs.extend(dict(p) for p in patches if isinstance(p, dict))

    # #39/#42：护栏只修载体与守恒，规格全部沿用 AI；修正事实白盒回灌 N4/N5 由 AI 自己复核。
    contract_notes: List[str] = []
    conservation_notes: List[str] = []
    conservation_restored: List[Dict] = []

    def _guard(current: List[Dict]) -> List[Dict]:
        cur, n1 = enforce_patch_contract(current, understood, context)
        contract_notes.extend(n1)
        cur, restored, n2 = enforce_item_conservation(cur, understood, context, known_specs)
        conservation_restored.extend(restored)
        conservation_notes.extend(n2)
        return cur

    def _gate_fact(current: List[Dict]) -> Dict[str, Any]:
        items = [x for x in (understood.get("items") or []) if isinstance(x, dict)]
        miss = missing_required_items(current, understood, context)
        return {
            "required_items": len(items),
            "add_patches": len(_add_patches(current)),
            "missing_items": len(miss),
            "conserved": not miss,
            "contract_residual": patch_contract_issues(current, understood, context),
        }

    patches = _guard(patches)

    # ── N4 自检 + N5 有疑问随时调整（AI 自己纠错，不交给规则、不问用户）──
    questions: List[str] = []
    verified = False
    for rnd in range(1, MAX_SELF_CORRECTIONS + 1):
        verdict = await run_node(
            "verify", _p_verify(message, context, patches, contract_notes,
                                item_fact=_gate_fact(patches),
                                conservation_notes=conservation_notes), round_no=rnd)
        if verdict and verdict.get("ok") is True:
            verified = True
            break
        if not verdict:
            # verify 节点 AI 不可用：不静默放行、不把半成品交给规则审批
            break
        questions = list(verdict.get("questions") or []) or ["自检未通过，请重新核对用户原话"]
        fixes = list(verdict.get("fixes") or [])
        revised = await run_node(
            "revise", _p_revise(message, context, patches, questions, fixes,
                                contract_notes, conservation_notes=conservation_notes),
            round_no=rnd
        )
        if revised and isinstance(revised.get("patches"), list) and revised["patches"]:
            patches = _guard(revised["patches"])
        # AI 自校正未产出改版：保留疑问，交由下一轮 verify 复核（护栏仍守住点名项）

    # #42：最后一轮 revise 可能又删了点名项，出厂前再守一次，杜绝半成品落地。
    patches = _guard(patches)
    gate_fact = _gate_fact(patches)
    residual = gate_fact["contract_residual"]
    fact_ok = bool(patches) and gate_fact["conserved"] and not residual

    summary = chain_summary(nodes, chain="chat")
    # #42：AI 自检未通过不再无条件出厂。只有「点名项守恒 + 字段真实 + 动作契约无残留」
    # 这一确定性事实闸门通过，才把模型残留的字段形态偏好类疑问记为 advisory 并放行；
    # 闸门不通过则诚实失败，绝不把缺项的半成品当作成功交付。
    verification: Dict[str, Any] = {
        "ai_verified": verified,
        "source": "ai_self_check" if verified else "deterministic_item_gate",
        "fact_gate_passed": fact_ok,
        "fact_pack": gate_fact,
        "ai_questions": questions[:12],
    }
    if not verified:
        if fact_ok:
            verification["reason"] = (
                "AI 自检两轮未通过，但用户点名项守恒、字段真实、动作契约无残留；"
                "AI 疑问仅为字段形态偏好，按用户原话优先级放行并白盒留痕")
        else:
            reason = ("AI 自检未通过且事实闸门不通过：缺%d个用户点名项、契约残留%d项"
                      % (gate_fact["missing_items"], len(residual)))
            nodes.append(node_result("chat", by="rule_fallback", llm_called=False,
                                     reason=reason, fallback_used=True))
            verification["reason"] = reason
            summary["verification"] = verification
            summary["verified"] = False
            return _fallback(reason, summary, run_id, trace)
    verified = True
    summary["verified"] = verified
    summary["verification"] = verification
    # 白盒：护栏做了什么、修完后是否还有不可执行项，如实随 SSE 下发
    summary["patch_guardrail"] = {
        "notes": contract_notes,
        "residual_issues": residual,
        "source": "ai_n1_intent + real_chart_ids",
    }
    summary["item_conservation"] = {
        "required_items": gate_fact["required_items"],
        "add_patches": gate_fact["add_patches"],
        "missing_final": gate_fact["missing_items"],
        "fact_gate_passed": fact_ok,
        "restored": conservation_restored,
        "notes": conservation_notes,
        "source": "ai_n1_items + ai_patch_specs",
    }
    if not patches or not summary["ai_governed"]:
        reason = ("AI 节点不可用或未产出可执行变更（%s）"
                  % ("; ".join(questions)[:160] or "节点 AI 不可用 / 无可签发 patch"))
        nodes.append(node_result("chat", by="rule_fallback", llm_called=False,
                                 reason=reason, fallback_used=True))
        return _fallback(reason, chain_summary(nodes, chain="chat"), run_id, trace)

    plan = _to_plan(understood, patches, summary)
    return {
        "ok": True,
        "by": "ai",
        "plan": plan,
        "governance": summary,
        "run_id": run_id,
        "rollback_point_required": True,
        "failure_reason": summary.get("failure_reason"),
        "trace": trace,
    }
