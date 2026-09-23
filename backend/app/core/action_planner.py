"""
动作规划器 - 2026-09-18 新增（复合指令支持 + 歧义澄清）

背景（根因）：
    IntentClassifier.classify() 遍历 INTENT_PATTERNS 命中第一个就 return，
    天然只支持"一条消息 = 一个意图"。因此：
      - 「删除转化率那张图，新增一张地区分布柱状图」→ ADD_CHART 抢先命中，删除动作被静默丢弃
      - 「标题改成客户风险画像，并补充一段结论」→ 只有 EDIT_TITLE，"补结论"无意图类型
    本模块在分类之前先把消息拆成有序子句，逐子句分类，产出**有序动作列表**，
    并对歧义/矛盾/字段不存在的情况产出 CLARIFY（只澄清，不猜测执行）。
"""
import re
from typing import Any, Dict, List, Optional

from app.core.intent_classifier import classify_intent, IntentType

# ---------------- 分句 ----------------
# 复合指令的连接词/分隔符
# 2026-09-22 修复（N1 复合回归）：此前用 \b并\b 等带单词边界的正则，
# 但 \b 是 ASCII 词边界，在中文字符之间不会触发，导致「删A图并新增B图」
# 这类无逗号的中文复合指令无法分句——整句被当成一个 ADD_CHART，删除动作被吞。
# 去掉 \b，直接用中连词语义切分（后续 _ACTION_VERB_RE 会把无动词续接子句回并，
# 不会因过度切分产生垃圾子句）。
_SPLIT_PATTERN = re.compile(
    r"[，,；;、]|并且|并|同时|然后|接着|而且|另外|还有|以及|再"
)
# 子句开头的连接词残留
_LEAD_NOISE = re.compile(r"^(?:并且|并|同时|然后|接着|而且|另外|还有|以及|再|还有|那|那么|请|帮我|麻烦)\s*")
# 子句结尾的"吧/呢/啊/一下/"
_TAIL_NOISE = re.compile(r"(?:吧|呢|啊|一下|一下子|哈)$")

# 问题2 修复（防截断）：动作动词集合。
# split_clauses 默认按逗号/顿号切分，但「加上每个：A，B，C，D，E 的平均值汇总」被切成多段后，
# 只有首段带「加上」能产出动作，其余裸字段名被丢进 unparsed（截断成 1 个）。
# 用本正则识别「带动作动词的子句」作为锚点，把其后「无动作动词的续接子句」回并，杜绝截断。
# 复合指令「删A图，新增B图」两段都含动作动词，不会被合并——回归安全。
_ACTION_VERB_RE = re.compile(
    r"(加上|新增|添加|插入|再来|删除|删掉|移除|去掉|删了|改成|改为|换成|替换|"
    r"把|将|移动|排序|上移|下移|置顶|置底|筛选|过滤|聚焦|补充)"
)

# 具体图表类型词（用于判断"更好的图"这类模糊指令）
_CONCRETE_TYPES = ["饼图", "柱图", "柱状图", "条形图", "直方图", "线图", "折线图", "曲线图", "散点图",
                   "圆环图", "环形图", "表格", "指标卡", "kpi", "KPI"]
_VAGUE_TYPE_WORDS = ["更好", "更合适", "合适", "更清晰", "清晰", "好看", "更美观", "美观",
                     "优化", "更专业", "专业", "高级", "高大上", "最佳", "最合适", "合适的"]

# 时间粒度词
_GRAIN_WORDS = [
    ("按月", "month"), ("每月", "month"), ("月度", "month"), ("按月份", "month"),
    ("按天", "day"), ("每天", "day"), ("按日", "day"), ("按周", "week"), ("每周", "week"),
    ("按季度", "quarter"), ("按季", "quarter"),
    ("按年", "year"), ("每年", "year"), ("年度", "year"),
]
# 单字粒度（不做字段存在性校验）
_GRAIN_SINGLE = {"月", "天", "日", "周", "季", "年", "时"}

# 明确点名字段的模式（用于"禁止幻觉"校验）
_FIELD_TOKEN_PATTERNS = [
    r"按\s*([^，。；！？\s、]{2,16}?)(?:的|做|成|聚合|汇总|统计|分布|趋势|占比|来|$)",
    r"([^，。；！？\s、]{2,16}?)(?:字段|列)",
    r"把\s*([^，。；！？\s、]{2,16}?)(?:做成|改成|换成|改为|作为)",
    r"[《「『\"']([^》」』\"']{2,20})[》」』\"']",
    r"[（(]([^）)]{2,20})[）)]",
]
_TOKEN_LEAD_NOISE = re.compile(r"^(?:把|将|用|按|以|根据|按照|对|从|这个|那个|的)")

# 指代消解（P0-1）："再来一个/再加一张/另一个"等无动词、承接上一轮动作的请求
_ADD_REPEAT_RE = re.compile(
    r"再来[一一个张]|再加[一一个张]|另一个|也[加来]一个|再给我[一一个张]|复制[一一个张]|多来[一一个张]"
)

# 澄清循环（P0-3）：中文序号 -> 数字
_CN_NUM = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def split_clauses(message: str) -> List[str]:
    """把复合指令拆成有序子句。拆不开就原样返回单元素列表（保证单指令行为不变）。"""
    if not message:
        return []
    raw = _SPLIT_PATTERN.split(message)
    out = []
    for part in raw:
        p = (part or "").strip()
        # 反复剥离开头连接词
        for _ in range(3):
            new = _LEAD_NOISE.sub("", p).strip()
            if new == p:
                break
            p = new
        p = _TAIL_NOISE.sub("", p).strip()
        if p:
            out.append(p)

    # 问题2 修复（防截断）：把「无动作动词的续接子句」回并到上一带动词子句。
    # 例：「我想要...加上每个：业务流程合规率，抵押登记合规率，...的平均值汇总」
    #   → 切分后首段带「加上」，后 4 段为裸字段名；回并成单子句，字段列举完整保留。
    # 复合指令「删掉A图，新增B图」两段均含动作动词，各自成句——不受影响。
    merged = []
    for p in out:
        if merged and not _ACTION_VERB_RE.search(p):
            merged[-1] = merged[-1] + "，" + p
        else:
            merged.append(p)
    out = merged

    return out or ([message.strip()] if message.strip() else [])


def _field_names(context: Dict[str, Any]) -> List[str]:
    fps = ((context or {}).get("dataset_info") or {}).get("field_profiles") or []
    names = []
    for fp in fps:
        n = fp.get("name") or fp.get("column") or ""
        if n:
            names.append(n)
    return names


def explicit_field_tokens(message: str) -> List[str]:
    """抽出用户"明确点名"的字段/维度词（用于校验是否真的存在）。"""
    toks: List[str] = []
    for pat in _FIELD_TOKEN_PATTERNS:
        for m in re.finditer(pat, message or ""):
            t = (m.group(1) or "").strip()
            t = _TOKEN_LEAD_NOISE.sub("", t).strip()
            if not t:
                continue
            if t in _GRAIN_SINGLE:
                continue
            if len(t) < 2:
                continue
            # 去掉明显的非字段词
            if any(w in t for w in ("图", "看板", "标题", "结论", "数据", "所有", "全部")):
                continue
            # 时间粒度词不是字段（"按月聚合"里的"月聚合"），必须跳过，否则会误报"字段不存在"
            if re.search(r"[月天日周季年时]", t) and len(t) <= 4:
                continue
            if any(w in t for w in ("聚合", "汇总", "统计", "按月", "按天", "按周", "按年")):
                continue
            toks.append(t)
    # 去重保序
    seen, out = set(), []
    for t in toks:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _field_exists(token: str, field_names: List[str]) -> bool:
    if not field_names:
        # 没有字段画像时不做校验（避免误拦）
        return True
    for fn in field_names:
        if token == fn or token in fn or fn in token:
            return True
    return False


_GRAIN_LABEL = {"month": "按月", "day": "按天", "week": "按周", "quarter": "按季度", "year": "按年"}


def detect_contradictory_grain(message: str) -> Optional[Dict[str, Any]]:
    """「同时按月和按天聚合」——两种粒度冲突，必须澄清。"""
    hits = {}
    for w, g in _GRAIN_WORDS:
        if w in (message or ""):
            hits.setdefault(g, g)
    if len(hits) >= 2:
        gs = list(hits.keys())
        labels = [_GRAIN_LABEL.get(g, g) for g in gs]
        return {
            "reason": "contradictory_grain",
            "message": (
                f"你同时要求{'和'.join(labels)}聚合，一张图只能用一种时间粒度。"
                f"请明确选一种（可直接回复「{'」或「'.join(labels)}」）。"
            ),
            "options": [{"grain": g, "label": _GRAIN_LABEL.get(g, g)} for g in gs],
        }
    return None


def detect_vague_chart_type(clause: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """「改成更好的图」——没有具体图型却要求换图，必须澄清而不是默认改柱状图。"""
    has_concrete = any(t in clause for t in _CONCRETE_TYPES)
    if has_concrete:
        return None
    if any(v in clause for v in _VAGUE_TYPE_WORDS) or not params.get("target_type"):
        return {
            "reason": "vague_chart_type",
            "message": (
                "「更好的图」我不知道具体指哪种——请告诉我目标图型。"
                "可选：柱状图、折线图、饼图、散点图、表格、指标卡。"
                "例如：「把销售额趋势改成折线图」。"
            ),
            "options": [{"chart_type": t, "label": t} for t in
                        ("柱状图", "折线图", "饼图", "散点图", "表格")],
        }
    return None


def _clarify_action(reason: str, message: str, clause: str, options=None, pending=None) -> Dict[str, Any]:
    """P0-3：clarify 产出携带 pending 载荷（意图类型 + 已确定的部分参数），
    供下一轮用户给短答案时由 _resolve_pending_clarify 接住，避免"听不懂就报错/落 UNKNOWN"。"""
    return {
        "type": "clarify",
        "params": {"reason": reason, "message": message, "options": options or [], "pending": pending},
        "clause": clause,
        "intent_type": "clarify",
        "confidence": 0,
    }


def _resolve_pending_clarify(message: str, pending: Dict[str, Any], context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """P0-3 澄清循环承接：用户上一轮被问"改哪张/哪种图/哪个字段/哪种粒度"，本轮给短答案，
    把短答案解析成完整的待执行动作，避免重新分类时落 UNKNOWN。

    pending 结构（由 chat.py 持久化、下一轮注入 context["pending_clarify"]）：
        {reason, clause, intent_type, partial_params, options, created_at}
    """
    if not pending or not message:
        return None
    reason = pending.get("reason")
    options = pending.get("options") or []
    if not options:
        return None
    msg = (message or "").strip()
    pp = pending.get("partial_params") or {}

    # 1) 序号选择："第二张" / "第3个" / "两个" / 裸数字
    _idx = None
    _m = re.search(r"(?:第\s*)?([0-9]+|[一二两三四五六七八九十]+)\s*(?:个|张|幅|图)?", msg)
    if _m:
        _tok = _m.group(1)
        if _tok.isdigit():
            _idx = int(_tok)
        elif _tok in _CN_NUM:
            _idx = _CN_NUM[_tok]

    # 2) 关键词命中：答案里包含某个选项的图名/图型/字段名/粒度
    _kw_opt = None
    for _o in options:
        _key = _o.get("title") or _o.get("chart_type") or _o.get("label") or _o.get("field") or _o.get("grain") or ""
        if _key and (_key in msg or msg in _key):
            _kw_opt = _o
            break

    _opt = None
    if _idx is not None and 1 <= _idx <= len(options):
        _opt = options[_idx - 1]
    elif _kw_opt:
        _opt = _kw_opt
    if not _opt:
        return None

    # 3) 按 reason 构造待执行动作
    if reason == "which_chart":
        return {
            "type": "change_chart",
            "params": {"chart_id": _opt.get("chart_id"), "target_type": pp.get("target_type")},
            "clause": message, "intent_type": "change_chart", "confidence": 85,
            "classified_by": "pending_clarify",
        }
    if reason == "vague_chart_type":
        return {
            "type": "change_chart",
            "params": {"title_keyword": pp.get("title_keyword"), "target_type": _opt.get("chart_type") or _opt.get("label")},
            "clause": message, "intent_type": "change_chart", "confidence": 85,
            "classified_by": "pending_clarify",
        }
    if reason == "contradictory_grain":
        return {
            "type": "filter_drill",
            "params": {"aggregation": _opt.get("grain") or _opt.get("label")},
            "clause": message, "intent_type": "filter_drill", "confidence": 85,
            "classified_by": "pending_clarify",
        }
    if reason == "field_not_found":
        # best-effort：用选中的真实字段替换原 clause 里的坏字段后，复用 planner 再规划一次
        _bad = pp.get("bad_field")
        _chosen = _opt.get("field") or _opt.get("label")
        _new_clause = pp.get("clause") or message
        if _bad and _chosen and _bad in (_new_clause or ""):
            _new_clause = (_new_clause or "").replace(_bad, _chosen)
        try:
            _re = plan_actions(_new_clause, context)
            _acts = _re.get("actions") or []
            if _acts:
                _acts[0]["classified_by"] = "pending_clarify"
                return _acts[0]
        except Exception:
            return None
        return None
    return None


def _to_action(intent_type: str, analysis: Dict[str, Any], clause: str, confidence: int) -> Optional[Dict[str, Any]]:
    """意图 → 动作；无需执行动作的意图（如归因追问）返回 None。"""
    mapping = {
        IntentType.CHANGE_CHART.value: "change_chart",
        IntentType.ADD_CHART.value: "add_chart",
        IntentType.DELETE_CHART.value: "delete_chart",
        IntentType.REORDER_CHART.value: "reorder_chart",
        IntentType.FILTER_DRILL.value: "filter_drill",
        IntentType.ATTRIBUTION.value: "attribution",
        IntentType.EDIT_TITLE.value: "edit_title",
        IntentType.ADD_CONCLUSION.value: "add_conclusion",
        IntentType.CHART_FIX.value: "chart_fix",
        IntentType.QUALITY_FIX.value: "quality_fix",
    }
    act = mapping.get(intent_type)
    if not act:
        return None
    params = dict((analysis or {}).get("extracted_params") or {})
    params.setdefault("clause", clause)
    return {
        "type": act,
        "params": params,
        "clause": clause,
        "intent_type": intent_type,
        "confidence": confidence,
    }


def _resolve_history_anaphora(message: str, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """P0-1 指代消解：用户说"再来一个/再加一张"等无动词、承接上一轮动作的请求。

    仅当上下文记忆里存在上一次图表动作（change_chart/add_chart）时才生效，
    产出"再加一张类似图"的 add_chart 动作（复用上次的图型与真实字段），不落 UNKNOWN。
    """
    last = (context or {}).get("memory", {}).get("last_action")
    if not last or not last.get("action_type"):
        return None
    if not _ADD_REPEAT_RE.search(message or ""):
        return None
    if last["action_type"] in ("change_chart", "add_chart"):
        params = {
            "chart_type": last.get("chart_type") or "bar",
            "dimension_field": last.get("dimension_field"),
            "metric_field": last.get("metric_field") or last.get("value_field"),
            "title": (last.get("title") or "图表") + "（类似）",
            "source": "history_repeat",
        }
        return {
            "type": "add_chart",
            "params": params,
            "clause": message,
            "intent_type": "add_chart",
            "confidence": 80,
            "classified_by": "history",
        }
    return None


def plan_actions(message: str, context: Dict[str, Any] = None, override: bool = False) -> Dict[str, Any]:
    """把一条用户消息规划成有序动作列表。

    Returns:
        {
          "is_compound": bool,               # 是否拆出多个动作
          "actions": [ {type, params, clause, intent_type, confidence}, ... ],
          "clauses": [...],
          "unparsed_clauses": [...],
          "primary_intent": {...classify_intent 兼容结构...},
        }
    """
    context = context or {}
    clauses = split_clauses(message)
    field_names = _field_names(context)

    # ---- P0-3 澄清循环承接：上一轮被问"改哪张/哪种图/哪个字段"，本轮给短答案 ----
    # 优先尝试把短答案解析成完整动作，命中则直接短路返回，避免重新分类时落 UNKNOWN 或重复澄清。
    _pending = (context or {}).get("pending_clarify")
    if _pending:
        _resolved = _resolve_pending_clarify(message, _pending, context)
        if _resolved:
            return {
                "is_compound": False,
                "actions": [_resolved],
                "clauses": [message],
                "unparsed_clauses": [],
                "primary_intent": {
                    "intent_type": _resolved["intent_type"],
                    "confidence": _resolved["confidence"],
                    "analysis": {"raw_message": message, "extracted_params": _resolved.get("params", {})},
                    "is_confident": True,
                    "classified_by": "pending_clarify",
                },
            }

    # ---- 全局歧义：粒度冲突（一句话里同时要两种粒度）----
    contra = detect_contradictory_grain(message)
    if contra:
        return {
            "is_compound": False,
            "actions": [_clarify_action(contra["reason"], contra["message"], message, contra.get("options"))],
            "clauses": clauses,
            "unparsed_clauses": [],
            "primary_intent": {
                "intent_type": "unknown", "confidence": 0,
                "analysis": {"raw_message": message, "extracted_params": {}},
                "is_confident": False, "classified_by": "planner",
            },
        }

    actions: List[Dict[str, Any]] = []
    unparsed: List[str] = []
    primary = None

    for clause in clauses:
        result = classify_intent(clause, context)
        itype = result.get("intent_type", "unknown")
        analysis = result.get("analysis", {})
        params = analysis.get("extracted_params", {}) or {}

        if itype == IntentType.UNKNOWN.value or not result.get("is_confident", True):
            unparsed.append(clause)
            continue

        # ---- 单点歧义 1：换图但没说/说得模糊 ----
        if itype == IntentType.CHANGE_CHART.value:
            # P0-1 指代消解：「就改成折线图」无主语时，锁定上一轮操作的图（memory.last_action）
            if not params.get("title_keyword") and not params.get("chart_id"):
                _last = (context or {}).get("memory", {}).get("last_action")
                if _last and _last.get("action_type") in ("change_chart", "add_chart"):
                    _tk = _last.get("title") or ""
                    if _tk:
                        params["title_keyword"] = _tk
                    elif _last.get("chart_id"):
                        params["chart_id"] = _last.get("chart_id")
            # P0-3：「把图改成饼图」——目标图型已知但没点名哪张图，且看板有多张图，
            # 必须先澄清"改哪张"（携带 which_chart pending，下一轮用序号/图名接住），
            # 杜绝"无主语兜底改第一张非目标类型图"这种答非所问。
            if not params.get("title_keyword") and not params.get("chart_id"):
                _charts = (context or {}).get("current_config", {}).get("charts", []) or []
                if params.get("target_type") and len(_charts) >= 2:
                    actions.append(_clarify_action(
                        "which_chart",
                        "你想改哪一张图？请告诉我图名，或直接回复序号（如「第二张」）。",
                        clause,
                        [{"chart_id": c.get("id"), "title": c.get("title"), "chart_type": c.get("chart_type")}
                         for c in _charts],
                        pending={"intent_type": "change_chart", "target_type": params.get("target_type")},
                    ))
                    if primary is None:
                        primary = result
                    continue
            vague = detect_vague_chart_type(clause, params)
            if vague:
                # P0-3：vague_chart_type 也携带 pending（已知图名时下一轮用图型名接住）
                _vague_pending = None
                if params.get("title_keyword"):
                    _vague_pending = {"intent_type": "change_chart", "title_keyword": params.get("title_keyword")}
                actions.append(_clarify_action(vague["reason"], vague["message"], clause, vague.get("options"), pending=_vague_pending))
                if primary is None:
                    primary = result
                continue

        # ---- 单点歧义 2：点名了不存在的字段 → 禁止幻觉，必须澄清 ----
        missing = [t for t in explicit_field_tokens(clause) if not _field_exists(t, field_names)]
        if missing and itype in (IntentType.ADD_CHART.value, IntentType.CHANGE_CHART.value,
                                 IntentType.FILTER_DRILL.value, IntentType.DELETE_CHART.value):
            avail = "、".join(field_names[:10]) or "（当前数据集没有可用字段画像）"
            actions.append(_clarify_action(
                "field_not_found",
                f"数据里没有「{'、'.join(missing[:3])}」这个字段，我不能拿别的字段顶替。"
                f"当前可用字段：{avail}。请换成其中一个再试。",
                clause,
                [{"field": f, "label": f} for f in field_names[:8]],
                pending={"intent_type": itype, "bad_field": missing[0], "clause": clause},
            ))
            if primary is None:
                primary = result
            continue

        act = _to_action(itype, analysis, clause, result.get("confidence", 0))
        if act:
            # 「删掉所有图」：用户显式说了"确认"或前端 override 才真正执行
            if act["type"] == "delete_chart" and act["params"].get("delete_all"):
                act["params"]["confirmed"] = bool(
                    override or re.search(r"(确认|确定|是的|是的删|就删|执行|我确定)", message or "")
                )
            actions.append(act)
            if primary is None:
                primary = result

    if primary is None:
        primary = {
            "intent_type": "unknown", "confidence": 0,
            "analysis": {"raw_message": message, "extracted_params": {}},
            "is_confident": False, "classified_by": "planner",
        }

    # P0-1 指代消解：「再来一个/再加一张」等无动词指代 → 承接上一轮动作（memory.last_action）
    if not actions and unparsed:
        _ana = _resolve_history_anaphora(message, context)
        if _ana:
            actions.append(_ana)
            primary = {
                "intent_type": _ana["intent_type"],
                "confidence": _ana["confidence"],
                "analysis": {"raw_message": message, "extracted_params": _ana["params"]},
                "is_confident": True,
                "classified_by": "history",
            }

    return {
        "is_compound": len(actions) > 1,
        "actions": actions,
        "clauses": clauses,
        "unparsed_clauses": unparsed,
        "primary_intent": primary,
    }
