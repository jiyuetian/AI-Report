"""S6 · AI 自主 CRUD 编排层（缺口闭环：L1-L4 增删改查「AI 自主执行」链路）。

需求对齐（用户 4 条子需求）：
- 需求2：AI 是每步执行者，增删改查「如何操作生成数据」都知悉 → 开工前读外置契约
  `prompts/s6_ai_crud.md`（可用动作/参数/护栏/行业指标模版），先规划再执行。
- 需求4：每个动作都有日志可查、可溯源 → 每步写 `ai_action_log`（`llm_layer="ai"`，`run_id` 关联三级留痕）；
  变更前按 R8-4 打快照回退点。

与既有路径的关系：
- 复用与 `chat.py` / `ai_crud.py` **同源**的 `ActionExecutor.execute` 引擎，保证执行语义一致；
- 把「AI 自主规划一串 CRUD 动作」抽成一等公民能力，可被 brain/run 的 S 阶段、管理后台、对话调用；
- 护栏 R15（ai_crud_* 阈值，单一真相源 threshold_config）约束动作数/禁批量/禁权限/强制快照。

执行模型（沙箱可真跑验证）：
- `ActionExecutor.execute` 直接对**内存中的 current_config dict** 做增删改并返回 new_config，**不依赖 DuckDB**，
  因此可在沙箱里真实驱动 CRUD 引擎、断言看板结构被改；快照/日志走可注入钩子（默认接真实实现）。
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, List, Optional

# ── 内置兜底提示词（Prompt 中心不可用时的种子；正常走 load_prompt 外置文件）──
_INLINE_S6_PROMPT = """你是看板改造工程师。把用户指令翻译成一串可执行 CRUD 动作。
用户指令：{directive}
当前看板：{dashboard_summary}
可用字段：{available_fields}
护栏：{guardrails}
最大动作数：{max_actions}
严格输出 JSON：{"analysis":"...","actions":[{"action_type":"add_chart","params":{...},"reason":"..."}]}"""


def _extract_json(text: Optional[str]) -> Optional[Dict[str, Any]]:
    """从 LLM 返回里解析首个 JSON 对象；容错 ```json 围栏与前后杂文。"""
    if not text:
        return None
    s = text.strip()
    if "```" in s:
        # 取最后一个 ``` 区块
        parts = s.split("```")
        for blk in reversed(parts):
            blk = blk.strip()
            if blk.lower().startswith("json"):
                blk = blk[4:].strip()
            try:
                return json.loads(blk)
            except Exception:
                continue
    # 退而求其次：大括号截段
    try:
        start, end = s.find("{"), s.rfind("}")
        if start >= 0 and end > start:
            return json.loads(s[start:end + 1])
    except Exception:
        return None
    return None


# 受护栏约束、AI 不可自主发起的高危动作（除非显式授权且超管）
_FORBIDDEN_BY_DEFAULT = {"bulk_update_data", "manage_permissions"}


async def _llm_plan(directive: str, context: Dict[str, Any], timeout: float) -> Optional[Dict[str, Any]]:
    """调用 LLM 生成 CRUD 动作计划；失败/超时返回 None（交给规则兜底）。"""
    import asyncio as _asyncio
    try:
        from app.core.llm_gateway import llm_chat
        from app.core.prompt_loader import load_prompt
    except Exception:
        return None

    prompt = load_prompt(
        "s6_ai_crud", _INLINE_S6_PROMPT,
        directive=directive,
        dashboard_summary=context.get("dashboard_summary", "（空看板）"),
        available_fields=context.get("available_fields", "（未知）"),
        guardrails=context.get("guardrails_text", "禁止批量改数/变更权限；不得编造字段"),
        max_actions=str(context.get("max_actions", 5)),
    )
    try:
        resp = await _asyncio.wait_for(
            llm_chat(prompt=prompt, json_mode=True, user_id="s6_ai_crud", timeout=timeout),
            timeout=timeout + 2,
        )
        return _extract_json(resp)
    except Exception:
        return None


def _rule_plan(directive: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """规则兜底规划：关键词映射到单个 CRUD 动作（AI 离线/失败时使用，保证链路不断）。"""
    d = (directive or "").lower()
    fields = context.get("available_fields_list") or []
    charts = context.get("current_charts") or []

    # 删除意图
    if any(k in d for k in ("删除", "去掉", "删掉", "移除", "remove", "delete")):
        # 删除 AI 新增的图？
        if "你新增" in d or "刚加" in d or "上一张" in d:
            return {"analysis": "规则兜底：删除 AI 最近新增的图表",
                    "actions": [{"action_type": "delete_chart",
                                  "params": {"delete_last_ai": True}, "reason": "规则兜底删除AI新增图"}]}
        # 按标题关键词
        for c in charts:
            t = (c.get("title") or "").lower()
            if t and t in d:
                return {"analysis": f"规则兜底：删除标题含「{c.get('title')}」的图",
                        "actions": [{"action_type": "delete_chart",
                                      "params": {"title_keyword": c.get("title")},
                                      "reason": "规则兜底按标题删图"}]}
        return {"analysis": "规则兜底：未定位到可删图表", "actions": []}

    # 新增意图
    if any(k in d for k in ("新增", "加一个", "加张", "添加", "加个", "add", "新增图")):
        # 从指令里挑维度/指标
        x_field = next((f for f in fields if any(k in f.lower() for k in ("地区", "区域", "region", "城市", "类别", "category", "时间", "date", "月份", "month"))), fields[0] if fields else None)
        y_field = next((f for f in fields if any(k in f.lower() for k in ("额", "量", "sales", "amount", "count", "数", "营收", "成本"))), fields[1] if len(fields) > 1 else (fields[0] if fields else None))
        if not (x_field and y_field):
            return {"analysis": "规则兜底：字段不足以新增图表", "actions": []}
        return {"analysis": f"规则兜底：新增一张 {x_field}→{y_field} 柱状图",
                "actions": [{"action_type": "add_chart",
                              "params": {"chart_type": "bar", "title": f"{x_field}的{y_field}",
                                         "x_field": x_field, "y_field": y_field, "aggregation": "sum"},
                              "reason": "规则兜底新增柱状图"}]}

    # 指标计算意图
    if any(k in d for k in ("算一下", "计算", "指标", "calculate", "同比", "环比")):
        return {"analysis": "规则兜底：触发指标计算",
                "actions": [{"action_type": "calculate_metric",
                              "params": {"metric": directive[:50], "operation": "query"},
                              "reason": "规则兜底指标计算"}]}

    return {"analysis": "规则兜底：未识别到可执行 CRUD 意图", "actions": []}


async def plan_crud_actions(
    directive: str,
    context: Dict[str, Any],
    *,
    thresholds: Optional[Dict[str, Any]] = None,
    llm_offline: bool = False,
    timeout: float = 25.0,
) -> Dict[str, Any]:
    """规划 CRUD 动作列表。返回 {analysis, actions:[{action_type,params,reason}], source:"ai"|"rule"}。

    - AI 主执行：调 LLM 输出计划（source="ai"）；
    - 失败/离线/关闭：规则兜底（source="rule"）。
    """
    thresholds = thresholds or {}
    source = "rule"
    plan: Optional[Dict[str, Any]] = None
    if not llm_offline and thresholds.get("ai_crud_enabled", True):
        plan = await _llm_plan(directive, context, timeout)
        if plan and isinstance(plan.get("actions"), list):
            source = "ai"
    if plan is None:
        plan = _rule_plan(directive, context)
    plan.setdefault("analysis", "")
    plan.setdefault("actions", [])
    plan["source"] = source
    return plan


def _apply_guardrails(
    actions: List[Dict[str, Any]],
    *,
    thresholds: Dict[str, Any],
    is_admin: bool = False,
) -> Dict[str, Any]:
    """R15 护栏：截断动作数、拦截高危动作。

    返回 {"executable": [...], "blocked": [...]}：
    - executable：被允许且未超上限的动作（交由执行层）；
    - blocked：被护栏拦截的动作（仅记录、不执行，供透明追溯）。
    """
    max_actions = int(thresholds.get("ai_crud_max_actions", 5))
    allow_bulk = bool(thresholds.get("ai_crud_allow_bulk", False)) and is_admin
    allow_perm = bool(thresholds.get("ai_crud_allow_permission", False)) and is_admin

    executable: List[Dict[str, Any]] = []
    blocked: List[Dict[str, Any]] = []
    for a in actions:
        at = (a.get("action_type") or "").lower()
        if at in _FORBIDDEN_BY_DEFAULT and not (allow_bulk and at == "bulk_update_data") and not (allow_perm and at == "manage_permissions"):
            b = dict(a)
            b["_blocked"] = f"护栏R15拦截：{at} 需超管手动/显式授权"
            blocked.append(b)
            continue
        executable.append(a)
    # 截断到 max_actions
    if len(executable) > max_actions:
        for dropped in executable[max_actions:]:
            d = dict(dropped)
            d["_blocked"] = f"护栏R15拦截：超出单次最大动作数 {max_actions}"
            blocked.append(d)
        executable = executable[:max_actions]
    return {"executable": executable, "blocked": blocked}


async def dispatch_ai_crud(
    *,
    directive: str,
    current_config: Dict[str, Any],
    db=None,
    dashboard_id: Optional[str] = None,
    user: Optional[Dict] = None,
    run_id: Optional[str] = None,
    thresholds: Optional[Dict[str, Any]] = None,
    llm_offline: bool = False,
    is_admin: bool = False,
    field_profiles: Optional[List[Dict[str, Any]]] = None,
    # 可注入钩子（自测用；默认接真实实现）
    executor_fn=None,
    snapshot_fn=None,
    log_fn=None,
    timeout: float = 25.0,
) -> Dict[str, Any]:
    """AI 自主 CRUD 主入口：规划 → R15 护栏 → 逐个执行（快照+日志）→ 返回结果。

    返回 dict：
      source, analysis, planned_count, executed_count, blocked,
      results:[{action_type, success, message, new_chart_count}], new_config, log_refs
    """
    from app.core.action_executor import ActionExecutor
    from app.core.version_manager import VersionManager
    from app.core.ai_action_log import log_ai_action

    thresholds = thresholds or {}
    user = user or {}
    executor_fn = executor_fn or (lambda at, p, cfg, ctx: ActionExecutor.execute(at, p, cfg, ctx))
    snapshot_fn = snapshot_fn or (lambda: VersionManager.create_version(
        db, dashboard_id, name="R8-4 改前回退点", description=f"S6 CRUD 前自动快照",
        created_by=user.get("user_id", "anonymous"), is_auto_save=True))
    log_fn = log_fn or log_ai_action

    # 字段画像：优先用调用方传入，否则由 thresholds["_fields"] 推导（默认非数值为维度）
    if field_profiles is None:
        _fnames = thresholds.get("_fields", []) or []
        field_profiles = [{"name": f, "type": ("number" if any(k in f.lower() for k in ("额", "量", "sales", "amount", "数", "count", "price", "cost")) else "string")} for f in _fnames]

    # 1. 规划
    ctx = {
        "dashboard_summary": json.dumps(current_config.get("charts", []), ensure_ascii=False)[:500],
        "available_fields": ", ".join(thresholds.get("_fields", []) or []),
        "available_fields_list": thresholds.get("_fields", []) or [],
        "current_charts": current_config.get("charts", []),
        "guardrails_text": "禁止批量改数/变更权限；不得编造字段；最多%d个动作" % int(thresholds.get("ai_crud_max_actions", 5)),
        "max_actions": int(thresholds.get("ai_crud_max_actions", 5)),
    }
    plan = await plan_crud_actions(directive, ctx, thresholds=thresholds, llm_offline=llm_offline, timeout=timeout)
    source = plan.get("source", "rule")
    guard = _apply_guardrails(plan.get("actions", []), thresholds=thresholds, is_admin=is_admin)
    executable = guard["executable"]
    blocked = [b.get("_blocked") for b in guard["blocked"]]

    # 传给 ActionExecutor 的执行上下文（含字段画像，供严格字段匹配）
    exec_context = {
        "user": user,
        "dashboard_id": dashboard_id,
        "dataset_id": dashboard_id or "",
        "dataset_info": {"field_profiles": field_profiles},
    }

    session_id = run_id or f"s6_{int(time.time()*1000)}"
    results: List[Dict[str, Any]] = []
    log_refs: List[Dict[str, Any]] = []

    require_snapshot = bool(thresholds.get("ai_crud_require_snapshot", True)) and db is not None and dashboard_id

    for a in executable:
        at = a.get("action_type")
        params = a.get("params", {}) or {}
        reason = a.get("reason", "")
        # R8-4 改前快照
        if require_snapshot:
            try:
                await snapshot_fn()
            except Exception:
                pass  # 快照失败不阻断（与 ai_crud.py 一致）
        # 执行（同源 ActionExecutor 引擎）
        start = time.monotonic()
        try:
            r = executor_fn(at, params, current_config, exec_context)
            latency = int((time.monotonic() - start) * 1000)
            ok = bool(r.get("success")) if isinstance(r, dict) else False
        except Exception as e:
            r = {"success": False, "error": str(e)[:200]}
            ok = False
            latency = int((time.monotonic() - start) * 1000)
        # 写 ai_action_log（llm_layer="ai"，run_id 关联三级留痕）
        rid = f"{session_id}-{len(results)+1}"
        try:
            await log_fn(
                session_id=session_id, dashboard_id=dashboard_id,
                user_id=user.get("user_id"), run_id=run_id,
                intent="ai_crud_agent", action_type=at,
                params_summary={"params": params, "reason": reason},
                result_status="success" if ok else "failed",
                error_msg=None if ok else r.get("error"),
                llm_layer="ai", latency_ms=latency,
            )
        except Exception:
            pass
        results.append({
            "action_type": at, "success": ok,
            "message": r.get("message") if isinstance(r, dict) else None,
            "error": r.get("error") if isinstance(r, dict) else None,
        })
        log_refs.append({"ref": rid, "action_type": at, "success": ok})

    return {
        "source": source,
        "analysis": plan.get("analysis", ""),
        "planned_count": len(plan.get("actions", [])),
        "executed_count": len(results),
        "blocked": [b.get("_blocked") for b in blocked],
        "results": results,
        "log_refs": log_refs,
        "new_config": current_config,
        "new_chart_count": len(current_config.get("charts", [])),
    }
