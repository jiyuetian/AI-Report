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
import json
from typing import Any, Dict, List, Optional

from app.core.intent_classifier import classify_intent, IntentType, IntentClassifier

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
    r"(加|加上|新增|添加|插入|再来|删除|删掉|移除|去掉|删了|改成|改为|换成|替换|"
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


def _dimension_categories(context: Dict[str, Any], field: str) -> List[str]:
    """取某维度字段的真实取值候选（categories/values）。用于"按哪个值"澄清的选项来源。
    无候选（字段画像未带枚举值）返回 []，让调用方保持原行为（不强制澄清）。"""
    fps = ((context or {}).get("dataset_info") or {}).get("field_profiles") or \
        (context or {}).get("field_profiles") or []
    if not field:
        return []
    for fp in fps:
        if (fp.get("name") or fp.get("column") or "") == field:
            cats = fp.get("categories") or fp.get("values") or []
            if isinstance(cats, list) and cats:
                return [str(c) for c in cats]
    return []


def _infer_filter_field(message: str, context: Dict[str, Any]) -> Optional[str]:
    """当分类器未给出 filter_field 时，从消息里"按/根据/筛选/过滤/聚焦/只看 + <维度字段名>"
    反推真实维度字段（限 context 中真实存在的字段），用于 which_filter_value 澄清。
    匹配不到返回 None（保持原行为，不臆造字段）。"""
    fps = ((context or {}).get("dataset_info") or {}).get("field_profiles") or \
        (context or {}).get("field_profiles") or []
    msg = (message or "").strip()
    if not msg:
        return None
    for fp in fps:
        fn = fp.get("name") or fp.get("column") or ""
        if not fn or len(fn) < 2:
            continue
        if re.search(r"(?:按|根据|筛选|过滤|聚焦|只看)\s*[^，。；]{0,4}?" + re.escape(fn), msg):
            return fn
    return None


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


# ---------------- P0-2：LLM 主导规划（规则未命中的看板操作语义）----------------

_ALLOWED_SEMANTIC_TYPES = (
    "change_chart", "add_chart", "delete_chart", "reorder_chart",
    "filter_drill", "edit_title", "attribution", "adjust_threshold",
)

# 模块级 LLM 调用封装，便于测试时 monkeypatch（返回解析后的 dict 或 None）
def _llm_plan_call(system_prompt: str, user_prompt: str, max_tokens: int = 700) -> Optional[Dict[str, Any]]:
    """调用 LLM 产出动作 JSON。失败/限流返回 None（交由规则降级，不抛异常）。"""
    try:
        from app.core.llm_gateway import get_llm_gateway, LLMRequest
        import concurrent.futures, asyncio
        request = LLMRequest(
            prompt=system_prompt + "\n" + user_prompt,
            json_mode=True,
            max_tokens=max_tokens,
            temperature=0.3,
        )
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            resp = ex.submit(
                lambda r: asyncio.run(get_llm_gateway().chat_complete(r)),
                request,
            ).result(timeout=40)
        if not resp or not resp.success or not resp.content:
            return None
        return resp.response_json or json.loads(resp.content)
    except Exception:
        return None


def _plan_with_llm(message: str, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """P0-2：把规则未命中的看板操作语义交给 LLM 直接规划成单个动作。

    返回：
      - 合规动作 dict（type/params/intent_type/confidence/classified_by）
      - {"clarify": reason}  —— LLM 认为信息不足需澄清
      - None                  —— LLM 失败/产出不合规 → 由调用方降级回规则/UNKNOWN
    """
    charts = (context or {}).get("current_config", {}).get("charts", []) or []
    fps = ((context or {}).get("dataset_info") or {}).get("field_profiles") or (context or {}).get("field_profiles") or []
    chart_desc = "\n".join(
        f"- {c.get('title')}（id={c.get('id')}, 类型={c.get('chart_type')}）" for c in charts
    ) or "（无）"
    field_desc = "\n".join(
        f"- {fp.get('name')}（{'数值' if _is_numeric_profile(fp) else '文本/分类'}）" for fp in fps
    ) or "（无）"

    system = (
        "你是 BI 看板对话的执行规划器。用户用自然语言对看板提出修改要求，"
        "请直接输出要执行的【单个动作】JSON（不要任何解释）。\n"
        "可用动作类型：" + "/".join(_ALLOWED_SEMANTIC_TYPES) + "。\n"
        "约束：\n"
        "1. change_chart：必须给 chart_id 或 title_keyword（从现有图表里选），以及 target_type（pie/bar/line/scatter/table/kpi）。\n"
        "2. add_chart：必须给 chart_type，以及真实 dimension_field/metric_field（从字段画像选）或 title_keyword。\n"
        "3. 只能引用真实存在的图表与字段，不得臆造。\n"
        "4. 若用户意图不清晰或缺少必要信息，输出 {\"need_clarify\": true, \"reason\": \"...\"}。\n\n"
        f"现有图表：\n{chart_desc}\n\n字段画像：\n{field_desc}\n"
    )
    user = f"用户要求：{message}\n请输出动作 JSON。"
    data = _llm_plan_call(system, user)
    if not isinstance(data, dict):
        return None
    if data.get("need_clarify"):
        return {"clarify": data.get("reason") or "信息不足，请补充说明具体要做什么。"}

    atype = data.get("type") or data.get("action_type")
    if atype not in _ALLOWED_SEMANTIC_TYPES:
        return None
    params = data.get("params") or {}

    # ---- 合规校验：缺关键参数的不合规产出直接降级回规则 ----
    if atype == "change_chart":
        if not (params.get("chart_id") or params.get("title_keyword")) or not params.get("target_type"):
            return None
        # chart_id 必须真实存在
        if params.get("chart_id") and not any(c.get("id") == params["chart_id"] for c in charts):
            return None
    if atype == "add_chart":
        if not (params.get("chart_type") or params.get("title_keyword")):
            return None
    if atype in ("filter_drill",) and not (params.get("filter_field") or params.get("filter_value")):
        return None

    return {
        "type": atype,
        "params": params,
        "clause": message,
        "intent_type": atype,
        "confidence": 75,
        "classified_by": "llm_semantic",
    }


def _is_numeric_profile(fp: Dict[str, Any]) -> bool:
    ftype = (fp.get("type") or fp.get("dtype") or "").upper()
    return any(t in ftype for t in ("DECIMAL", "DOUBLE", "FLOAT", "INT", "BIGINT", "NUMERIC", "REAL", "NUMBER", "DEC"))


def detect_vague_chart_type(clause: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """「改成更好的图」——没有具体图型却要求换图，必须澄清而不是默认改柱状图。"""
    has_concrete = any(t in clause for t in _CONCRETE_TYPES)
    if has_concrete:
        return None
    if any(v in clause for v in _VAGUE_TYPE_WORDS) or not params.get("target_type"):
        # 2026-09-29 night10 Item1(ISS-039)：轴/字段替换（"把Y轴换成利润"）已显式点名目标字段，
        # 不算"图型模糊"，不应反问"要哪种图"。
        if params.get("target_field"):
            return None
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


def _clarify_action(reason: str, message: str, clause: str, options=None, pending=None, proposal=None) -> Dict[str, Any]:
    """P0-3：clarify 产出携带 pending 载荷（意图类型 + 已确定的部分参数），
    供下一轮用户给短答案时由 _resolve_pending_clarify 接住，避免"听不懂就报错/落 UNKNOWN"。

    night9 Item3 扩展：proposal 为「待用户确认的动作」（如 {"intent_type":"add_chart",
    "partial_params":{...}}）。当 AI 提议并询问"要加吗？"时带上 proposal，用户用确认词
    承接即执行该动作（模块 B5 承诺执行）；否定词则取消。
    """
    p = {
        "type": "clarify",
        "params": {"reason": reason, "message": message, "options": options or [], "pending": pending},
        "clause": clause,
        "intent_type": "clarify",
        "confidence": 0,
    }
    if proposal:
        p["proposal"] = proposal
    return p


# ---- night19 任务B：澄清循环最大轮次退避 ----
# 同一议题连续澄清达到上限（建议 2 轮）后不再追问，改为收敛话术（给最可能方案 + 确认/取消），
# 避免反复追问。承接成功（短答案被解析成动作 / 确认词）仍正常短路，不受轮次限制。
MAX_CLARIFY_ROUNDS = 2


def _converge_clarify(pending: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """澄清轮次达上限后的收敛话术（night19 任务B + night21 ISS-060 修复）。

    返回 type=clarify 且 params.converged=True。差异：
    - 若有选项且能取出最佳项的可执行动作 → 带 proposal（顶层，与 _clarify_action 一致）：
      下一轮「确认」命中 plan_actions 的 proposal 承接路径直接采纳，chat.py 持久化该 pending。
    - 若 reason=='vague_chart_type' 且缺图锚点（"第一个"仍解析成追问 which_chart 的 clarify）→
      用 options[0] 的图型 + 已有锚点 / 第一张图 拼可执行 change_chart proposal，使「确认」能落地。
    - 若确实无法构成可执行动作（无选项 / 无锚点）→ 收敛话术改为不引导"确认"，改引导用户直接给
      图名 / 序号（文案不承诺确认）；chat.py 据此 pop pending 结束循环。
    """
    _pending = pending or {}
    _opts = _pending.get("options") or []
    _reason = _pending.get("reason")
    _pp = _pending.get("partial_params") or {}

    def _build_converged(message: str, proposal=None):
        _ret = {
            "type": "clarify",
            "params": {
                "reason": _reason,
                "message": message,
                "options": _opts,
                "pending": {"intent_type": _pending.get("intent_type"),
                            "partial_params": _pp},
                "converged": True,
            },
            "clause": "",
            "intent_type": "clarify",
            "confidence": 0,
        }
        if proposal:
            _ret["proposal"] = proposal
        return _ret

    if not _opts:
        # 无选项：无法构成可执行动作，不引导"确认"
        _msg = (
            f"我已多次尝试确认，仍未能完全确定你的意图（{_reason or '当前意图'}）。"
            f"请直接告诉我要改哪张图 / 哪种图型 / 哪个字段（如图名或序号），或回复「取消」放弃。"
        )
        return _build_converged(_msg)

    # 尝试取出最佳项（"第一个"）的可执行动作
    _best_act = _resolve_pending_clarify("第一个", _pending, context)
    _proposal = None
    _detail = None
    if _best_act and _best_act.get("type") != "clarify":
        _proposal = {
            "intent_type": _best_act["intent_type"],
            "partial_params": _best_act.get("params") or {},
        }
        _detail = (_best_act.get("params") or {}).get("target_type") or _best_act["intent_type"]
    elif _reason == "vague_chart_type":
        # "第一个" 仍解析成追问 which_chart 的 clarify：用 options[0] 图型 + 锚点 / 首图拼可执行 proposal
        _best = _opts[0]
        _target = _best.get("chart_type") or _best.get("label")
        _anchor_kw = _pp.get("title_keyword")
        _anchor_id = _pp.get("chart_id")
        _charts = (context or {}).get("current_config", {}).get("charts", []) or []
        if not _anchor_kw and not _anchor_id and _charts:
            _anchor_kw = _charts[0].get("title")
            _anchor_id = _charts[0].get("id")
        if _anchor_kw or _anchor_id:
            _proposal = {
                "intent_type": "change_chart",
                "partial_params": {
                    "chart_id": _anchor_id,
                    "title_keyword": _anchor_kw,
                    "target_type": _target,
                },
            }
            _detail = _target

    if _proposal:
        _msg = (
            f"我已多次尝试确认，仍未能完全确定你的意图。当前看板最可能的方案是：{_detail or '推荐方案'}。"
            f"请回复「确认」采用该方案，或「取消」放弃；你也可以直接说明要改哪张图 / 哪种图型 / 哪个字段。"
        )
        return _build_converged(_msg, _proposal)

    # 无法构成可执行 proposal（其它 reason 或无锚点）：不引导"确认"
    _msg = (
        f"我已多次尝试确认，仍未能完全确定你的意图（{_reason or '当前意图'}）。"
        f"请直接告诉我要改哪张图 / 哪种图型 / 哪个字段（如图名或序号），或回复「取消」放弃。"
    )
    return _build_converged(_msg)


def _plan_from_single(act: Dict[str, Any], message: str,
                      pending: Dict[str, Any] = None,
                      classified_by: str = "pending_clarify") -> Dict[str, Any]:
    """把单个动作包装成 plan_actions 的标准返回结构（承接 clarify 语义，保留原 intent_type）。"""
    _it = act.get("intent_type")
    if act.get("type") == "clarify" and pending and pending.get("intent_type"):
        _it = pending.get("intent_type")
    return {
        "is_compound": False,
        "actions": [act],
        "clauses": [message],
        "unparsed_clauses": [],
        "primary_intent": {
            "intent_type": _it,
            "confidence": act.get("confidence", 0),
            "analysis": {"raw_message": message, "extracted_params": act.get("params", {})},
            "is_confident": True,
            "classified_by": classified_by,
        },
    }


def _detect_chart_anchor(msg: str, charts: list) -> Optional[str]:
    """P0-3 遗留修复：从用户短答案里找是否点名了某张图（按图名子串命中），返回图名或 None。

    背景：真实生成的看板里图表 id 大量为 null，「第2张/某个图名」是唯一可靠锚点。
    拿不到锚点就必须继续追问，不能让执行器去兜底改第一张图。
    """
    if not charts or not msg:
        return None
    _m = (msg or "").strip()
    for _c in charts:
        _t = (_c.get("title") or "").strip()
        if _t and _t in _m:
            return _t
    return None


# ==== night9 Item3：C 确认词承接（模块 B5 承诺执行）====
# 确认词 / 否定词词表。仅在「上一轮有 pending 提议」时由 plan_actions 调用 detect_confirmation 才有意义；
# 本函数只做文本判定，返回 "confirm" / "negate" / None。
_CONFIRM_TOKENS = {
    "好", "好的", "好呀", "好哒", "好嘞", "可以", "可以呀", "行", "行啊", "确认",
    "ok", "okay", "没问题", "没问题的", "就这样", "就这", "按你说的", "按你说的来",
    "同意", "可以了", "好的呀", "成", "成交", "准", "通过",
}
_NEGATE_TOKENS = {
    "不好", "不行", "不要", "不用", "先不", "暂不需要", "暂时不用", "算了", "别",
    "不想要", "不需要", "不用了", "否", "不可以", "不干", "不要了", "暂不", "先不用",
    # night21 ISS-060：收敛话术明确引导用户回「取消」放弃，故须被识别为否定词（cancel_pending）
    "取消",
}
_PUNCT_STRIP = " ，。！？、~～.,!?;；:：'\"''（）()【】[]<>《》\t\n\r　"


def _norm_confirm_text(msg: str) -> str:
    if not msg:
        return ""
    s = (msg or "").strip()
    for ch in _PUNCT_STRIP:
        s = s.replace(ch, "")
    return s.lower()


def detect_confirmation(message: str) -> Optional[str]:
    """night9 Item3：识别确认词 / 否定词。

    - "confirm"：用户用 好/可以/确认/就这样/ok 等承接上一轮 AI 的提议。
    - "negate"：用户用 不好/先不/不用/算了 等拒绝上一轮提议。
    - None：非确认/否定短语（走正常分类）。

    约束：要求归一化后文本**整体**命中词表且长度 <= 12，否定优先于确认，
    避免误判（如"这个图好""能不能不用"被当成确认）。
    """
    s = _norm_confirm_text(message)
    if not s or len(s) > 12:
        return None
    if s in _NEGATE_TOKENS:
        return "negate"
    # 兜底否定前缀：以 不/别/算了/暂/先不 开头且非单纯确认词
    if s.startswith(("不", "别", "算了", "暂", "先不")) and s not in _CONFIRM_TOKENS:
        return "negate"
    if s in _CONFIRM_TOKENS:
        return "confirm"
    return None


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
        _key = _o.get("title") or _o.get("chart_type") or _o.get("label") or _o.get("field") or _o.get("grain") or _o.get("value") or ""
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
    _charts = (context or {}).get("current_config", {}).get("charts", []) or []

    if reason == "which_chart":
        return {
            "type": "change_chart",
            # 2026-09-24 修复（P0-3 遗留）：AI 生成的看板里图表 id 常为 null，
            # 只带 chart_id 等于没锚点，执行器会兜底改"第一张还不是目标类型的图"，
            # 实测把第 1 张 KPI 卡改成了目标图型。补 title_keyword 让无 id 看板也能精确定位。
            "params": {"chart_id": _opt.get("chart_id"),
                       "title_keyword": _opt.get("title"),
                       "target_type": pp.get("target_type")},
            "clause": message, "intent_type": "change_chart", "confidence": 85,
            "classified_by": "pending_clarify",
        }
    if reason == "vague_chart_type":
        _target = _opt.get("chart_type") or _opt.get("label")
        # 2026-09-24 修复（P0-3 遗留）：上一轮问的是"改成哪种图"，本轮用户答了图型，
        # 但仍然没说改哪一张图 -> 继续追问"改哪张"，不许拿第一张图兜底。
        _anchor_kw = pp.get("title_keyword") or _detect_chart_anchor(msg, _charts)
        _anchor_id = pp.get("chart_id")
        if not _anchor_kw and not _anchor_id and len(_charts) >= 2:
            _names = "、".join(
                [(c.get("title") or "第%d张" % (i + 1)) for i, c in enumerate(_charts[:8])]
            )
            return _clarify_action(
                "which_chart",
                f"好的，改成{_target}。请告诉我要改哪一张图：{_names}"
                f"（回复图名或序号即可，例如「第二张」）。",
                message,
                [{"chart_id": c.get("id"), "title": c.get("title"), "chart_type": c.get("chart_type")}
                 for c in _charts],
                pending={"intent_type": "change_chart", "target_type": _target},
            )
        return {
            "type": "change_chart",
            "params": {"chart_id": _anchor_id, "title_keyword": _anchor_kw, "target_type": _target},
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
    # night23 Task B · ISS-042 多轮语义承接（filter 值）：上一轮问"按哪个值"（如"按哪个地区"），
    # 本轮用户用短答案（"用华南"）或序号承接，解析成 filter_drill 动作，避免落 UNKNOWN。
    if reason == "which_filter_value":
        _val = _opt.get("value") or _opt.get("label") or _opt.get("field")
        return {
            "type": "filter_drill",
            "params": {"filter_field": pp.get("filter_field"), "filter_value": _val},
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
        IntentType.UNDO.value: "undo",        # night13 Item1：撤销最近一次 AI 操作
        IntentType.ADJUST_THRESHOLD.value: "adjust_threshold",  # night18 ISS-058：阈值调整
        # ---- night15-16 Task G：最高权限 CRUD ----
        IntentType.CREATE_CONFIG.value: "create_config",
        IntentType.UPDATE_CONFIG.value: "update_config",
        IntentType.DELETE_CONFIG.value: "delete_config",
        IntentType.BULK_UPDATE_DATA.value: "bulk_update_data",
        IntentType.MANAGE_PERMISSIONS.value: "manage_permissions",
        # ---- night15-16 Task H：派生指标查询 ----
        IntentType.QUERY_METRIC.value: "calculate_metric",
        IntentType.RECALC_METRIC.value: "recalc_metric",
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


def _extract_position_hints_from_message(message: str) -> Dict[str, str]:
    """night13 Item3 K-2：从整句提取位置/邻近线索。

    split_clauses 可能把「在X的旁边」拆到与「加一张图」不同的 clause，
    导致落位信息丢失。这里从整句 message 兜底提取 near_title / position，
    写入 add_chart 动作参数，确保新图落在用户指定的图旁。
    """
    out: Dict[str, str] = {}
    # 「在 平均坏账率 的 旁边/附近/后面/之后/上方/上面」→ near_title + 后置
    m = re.search(
        r"在\s*([^，。；！？的]{1,20}?)\s*(的)?\s*"
        r"(旁边|附近|后面|之后|上方|上面|下方|下面|前面|之前)",
        message or ""
    )
    if m:
        out["near_title"] = m.group(1).strip()
        out["position"] = "after" if m.group(3) in ("旁边", "附近", "后面", "之后", "上方", "上面") else "before"
    # 「顶部/最上面/置顶」→ position=top
    if re.search(r"顶部|最上面|置顶|最前", message or ""):
        out["position"] = "top"
    return out


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
    _clarify_round = int((_pending or {}).get("clarify_round", 1) or 1) if _pending else 0
    _clarify_capped = bool(_pending) and _clarify_round >= MAX_CLARIFY_ROUNDS
    if _pending:
        # night9 Item3：确认词承接（模块 B5 承诺执行）。上一轮 AI 提出了待确认动作，
        # 本轮用户用确认词/否定词承接，确定性短路（不依赖 LLM 分类，规避 429 与误判）。
        _conf = detect_confirmation(message)
        if _conf == "negate":
            return {
                "is_compound": False,
                "actions": [{"type": "cancel_pending", "params": {}, "clause": message,
                             "intent_type": "cancel_pending", "confidence": 90,
                             "classified_by": "confirmation_word"}],
                "clauses": [message], "unparsed_clauses": [],
                "primary_intent": {"intent_type": "cancel_pending", "confidence": 90,
                                   "analysis": {"raw_message": message, "extracted_params": {}},
                                   "is_confident": True, "classified_by": "confirmation_word"},
            }
        if _conf == "confirm":
            _prop = _pending.get("proposal") or {}
            _it = _prop.get("intent_type") or _pending.get("intent_type")
            if _it and _it not in ("clarify", "unknown", "cancel_pending"):
                _params = dict(_prop.get("partial_params") or {})
                _params.setdefault("clause", message)
                return {
                    "is_compound": False,
                    "actions": [{"type": _it, "params": _params, "clause": message,
                                 "intent_type": _it, "confidence": 90,
                                 "classified_by": "confirmation_word"}],
                    "clauses": [message], "unparsed_clauses": [],
                    "primary_intent": {"intent_type": _it, "confidence": 90,
                                       "analysis": {"raw_message": message, "extracted_params": _params},
                                       "is_confident": True, "classified_by": "confirmation_word"},
                }
            # 上一轮是「选项式澄清」(pending 带 options 但无 proposal)：确认=采纳推荐项（第1个）
            if _pending.get("options"):
                _first = _resolve_pending_clarify("第一个", _pending, context)
                if _first:
                    return {
                        "is_compound": False,
                        "actions": [_first],
                        "clauses": [message], "unparsed_clauses": [],
                        "primary_intent": {"intent_type": _first["intent_type"], "confidence": 90,
                                           "analysis": {"raw_message": message, "extracted_params": _first.get("params", {})},
                                           "is_confident": True, "classified_by": "confirmation_word"},
                    }
            # 既没有 proposal 也没有 options：确认词无承接对象，落到正常分类（AI 会再问/闲聊）
        _resolved = _resolve_pending_clarify(message, _pending, context)
        if _resolved:
            # night19 任务B：若本轮仍要再追问（type==clarify）且已达轮次上限 → 收敛，不再追问
            if _resolved.get("type") == "clarify" and _clarify_capped:
                return _plan_from_single(_converge_clarify(_pending, context), message, _pending)
            return _plan_from_single(_resolved, message, _pending)
        # night19 任务B：短答案无法解析（仍歧义）且已达轮次上限 → 收敛，不再追问
        if _clarify_capped:
            return _plan_from_single(_converge_clarify(_pending, context), message, _pending)

    # ---- 全局歧义：粒度冲突（一句话里同时要两种粒度）----
    contra = detect_contradictory_grain(message)
    if contra:
        # night19 任务B：已有进行中的澄清且达轮次上限 → 收敛，不再重复追问粒度
        if _clarify_capped:
            return _plan_from_single(_converge_clarify(_pending, context), message, _pending)
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

        # ---- P0-2：规则未命中但属看板操作语义 → 交 LLM 主导规划动作 ----
        if itype == IntentType.SEMANTIC_ACTION.value:
            _llm_plan = _plan_with_llm(clause, context)
            if _llm_plan is None:
                # LLM 失败/产出不合规 → 降级回规则（落 unparsed，最终走 UNKNOWN 自然回复）
                unparsed.append(clause)
                continue
            if _llm_plan.get("clarify"):
                actions.append(_clarify_action(
                    "semantic_clarify", _llm_plan["clarify"], clause, None,
                    pending={"intent_type": "semantic", "clause": clause},
                ))
                if primary is None:
                    primary = result
                continue
            actions.append(_llm_plan)
            if primary is None:
                primary = {
                    "intent_type": _llm_plan["intent_type"],
                    "confidence": _llm_plan["confidence"],
                    "analysis": {"raw_message": clause, "extracted_params": _llm_plan.get("params", {})},
                    "is_confident": True,
                    "classified_by": "llm_semantic",
                }
            continue

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
                # 2026-09-23 修复（P0-1 真跑回归）：用户点明了源图型（「把饼图改成柱图」的"饼图"）
                # 时，源图型本身就是定位线索。看板里该图型唯一 → 目标已明确，直接锁定，
                # 不再反问"你想改哪一张图"——问了就是答非所问（用户最痛的点）。
                # 此前只看 title_keyword/chart_id，忽略 source_type，
                # 导致真实多图看板上 Round 1 被打断成澄清，饼图始终没被改成柱图。
                _src_raw = params.get("source_type")
                _src = IntentClassifier._normalize_chart_type(_src_raw) if _src_raw else None
                if _src:
                    _src_hits = [c for c in _charts if (c.get("chart_type") or "") == _src]
                    if len(_src_hits) == 1:
                        _t = (_src_hits[0].get("title") or "").strip()
                        if _t:
                            params["title_keyword"] = _t
                        elif _src_hits[0].get("id"):
                            params["chart_id"] = _src_hits[0].get("id")
                # 命中 0 张（源图型不存在）或 ≥2 张（仍歧义）→ 保持原澄清行为
                if not params.get("title_keyword") and not params.get("chart_id"):
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
            # night13 Item3 K-11：歧义换图（换角度/换视角）必须澄清，不能擅自执行。
            if params.get("ambiguous_change"):
                _charts = (context or {}).get("current_config", {}).get("charts", []) or []
                actions.append(_clarify_action(
                    "ambiguous_change",
                    "「换一个角度」我还不太确定你想换什么——是换维度（如按担保类型拆分）、换图型（柱状/折线/饼图），"
                    "还是换指标（看别的字段）？告诉我方向我就改。",
                    clause,
                    [{"option": "换维度"}, {"option": "换图型"}, {"option": "换指标"}],
                    pending={"intent_type": "change_chart", "chart_title_hint": params.get("chart_title_hint")},
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
        # night13 Item1（K-8 字段匹配失败禁出图）：ADD_CHART 的 metric_name 也按真实字段校验，
        # 覆盖"加一个叫XXX的新指标"这类 explicit_field_tokens 抽不到坏字段名的中文口语。
        if itype == IntentType.ADD_CHART.value and not params.get("target_field"):
            _mn = (params.get("metric_name") or "").strip()
            if _mn and _mn not in ("新增指标", "新增", "指标") and not _field_exists(_mn, field_names):
                missing = missing + [_mn]
        # 2026-09-29 night10 Item1(ISS-039)：轴/字段替换（"把Y轴换成利润"）中"利润"是用户显式指定的目标字段，
        # 不是缺失字段，不应触发"字段不存在"澄清。
        if missing and itype in (IntentType.ADD_CHART.value, IntentType.CHANGE_CHART.value,
                                 IntentType.FILTER_DRILL.value, IntentType.DELETE_CHART.value) \
                and not params.get("target_field"):
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

        # night23 Task B · ISS-042 多轮语义承接（filter 值）——"按地区筛选"已知维度但没说具体值，
        # 且该维度有真实取值候选（categories）时，先澄清"聚焦哪个值"，下一轮"用华南"等短答案接住，
        # 避免把 filter_drill 默认成"筛选全部"或静默落空。无 categories 候选则保持原行为（不破坏单图筛选）。
        if itype == IntentType.FILTER_DRILL.value:
            _ff = params.get("filter_field") or _infer_filter_field(message, context)
            _fv = params.get("filter_value")
            if _ff and not _fv:
                _cats = _dimension_categories(context, _ff)
                if _cats:
                    actions.append(_clarify_action(
                        "which_filter_value",
                        f"按「{_ff}」筛选，要聚焦哪个值？可选：{', '.join(_cats[:8])}"
                        f"（回复具体值即可，例如「华南」）。",
                        clause,
                        [{"value": c, "label": c} for c in _cats],
                        pending={"intent_type": "filter_drill", "filter_field": _ff},
                    ))
                    if primary is None:
                        primary = result
                    continue

        # night13 Item3 K-2：位置/邻近线索（"在X的旁边"）可能被 split_clauses 拆到别的 clause，
        # 必须从整句 message 提取 near_title/position 写入动作参数，避免落位信息丢失。
        if itype == IntentType.ADD_CHART.value:
            _ph = _extract_position_hints_from_message(message)
            if _ph.get("near_title") and not params.get("near_title"):
                params["near_title"] = _ph["near_title"]
            if _ph.get("position") and not params.get("position"):
                params["position"] = _ph["position"]

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
