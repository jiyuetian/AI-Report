"""
AI 数据质量补充检测
使用LLM分析数据样本，发现规则无法覆盖的潜在问题

功能：
1. 数据分析：检查数据分布异常、语义异常、字段关联矛盾
2. 分级输出：影响进场的阻断，不影响进场的提示
3. 修复方案：AI针对每个问题生成修复选项
"""
import json
import hashlib
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict

from app.core.llm_gateway import get_llm_gateway, LLMRequest, LLMResponse
from app.core.prompt_loader import load_prompt


# Task #724：证据链输出契约。提示词中心可能存有旧版覆盖（不含这些字段），
# 无论覆盖内容如何，_build_prompt() 都会在末尾强制补回这一段，避免能力被旧覆盖悄悄抹掉。
_EVIDENCE_OUTPUT_FORMAT = (
    '{"issues":[{"column":"真实字段名","severity":"warning","message":"一句话概括",'
    '"detail":"影响说明","row_count":2,'
    '"plain_conclusion":"大白话结论：到底哪几条数据不对，不要用术语",'
    '"basis":"判断依据：看到的具体字段值/组合，以及为什么认为不对",'
    '"involved_columns":["真实字段名A","真实字段名B"],'
    '"check_suggestion":"人工核对建议：按什么条件筛选、重点看哪几列、确认什么",'
    '"evidence_filter":[{"column":"真实字段名","op":"eq","value":"样本里出现过的值"}],'
    '"row_numbers":[1,2],'
    '"repair_plan":{"strategy":"keep_as_is","reason":"为什么建议这样处理",'
    '"risk":"改了会有什么风险","target_value":""}}]}'
)

_EVIDENCE_CONTRACT = """
## 证据链输出要求（必须遵守）
- 每条问题必须带 plain_conclusion / basis / involved_columns / check_suggestion / repair_plan。
- plain_conclusion / basis / check_suggestion 用业务人员能看懂的中文短句，禁止只写「语义矛盾」「关联矛盾」。
- involved_columns 是涉及的全部真实字段名，至少含 column，必须来自表结构。
- evidence_filter 可选：op 只能是 eq/neq/gt/lt/in/is_null，value 必须是样本里出现过的值；给不出填空数组。
- row_numbers 可选：可疑行在数据样本里的 1-based 行号（1-8）；给不出填空数组。

## 修复策略输出要求（必须遵守）
- repair_plan.strategy 只能是 replace_with_column_median / replace_with_column_mean /
  winsorize_p1_p99 / set_null / replace_with_constant / keep_as_is 之一，不得自造。
- reason / risk 用中文短句说清依据与风险；replace_with_constant 必须给 target_value。
- 若异常可能是真实业务波动，选 keep_as_is，不要建议覆盖原始值。
- AI 只签发建议，不直接改数据；执行由规则引擎在用户确认后完成。

## 输出形状（强制；违反会判本次检测失败）
- 顶层必须且只能是 {"issues":[...]} 这一个对象；不要包进 result/data/output，不要返回裸数组。
- issues 必须是数组，每个元素都是对象；没有新问题必须返回 {"issues":[]}，
  不要返回 {"issues":null}、{"issues":{}}、字符串或解释文字。
- 不要增删顶层键，不要输出 Markdown 代码块围栏或任何前后缀文字。
"""

_EVIDENCE_OPS = {"eq", "neq", "gt", "lt", "in", "is_null"}


# Task #728/#34：AI 修复策略白名单（后端唯一真相源，前端通过证据端点下发渲染）。
# AI 只能从这 6 个里挑一个，执行端点也只认这 6 个，杜绝 AI 自造 SQL / 任意改数。
AI_REPAIR_STRATEGIES = {
    "replace_with_column_median": {
        "label": "用该列其他正常行的中位数替换这几行",
        "description": "只改 AI 定位到的可疑行；中位数取自未命中行，避免被异常值拉偏。",
        "risk": "会覆盖这几行的原始值，建议先看明细确认确属录入错误。",
        "numeric_only": True,
    },
    "replace_with_column_mean": {
        "label": "用该列其他正常行的均值替换这几行",
        "description": "只改 AI 定位到的可疑行；均值取自未命中行。",
        "risk": "均值对极端值更敏感，可能偏离真实业务水平。",
        "numeric_only": True,
    },
    "winsorize_p1_p99": {
        "label": "把这几行压到该列 P1/P99 边界",
        "description": "按整列 1%/99% 分位数裁剪可疑行，保留排序关系。",
        "risk": "分位数由全表计算，样本少时边界可能不稳定。",
        "numeric_only": True,
    },
    "set_null": {
        "label": "把这几行置为空值（不猜真实值）",
        "description": "确认取值不可信但不掌握正确值时，先置空。",
        "risk": "置空后下游聚合会少算这些行，需评估口径影响。",
        "numeric_only": False,
    },
    "replace_with_constant": {
        "label": "用指定值替换这几行",
        "description": "AI 给出明确正确值（target_value）时按该值替换。",
        "risk": "值由 AI 推断，必须人工核对后再执行。",
        "numeric_only": False,
    },
    "keep_as_is": {
        "label": "AI 建议保留原值，只做人工核对",
        "description": "异常可能是真实业务变化，不建议自动修改数据。",
        "risk": "不改动数据，问题会保持「待修复」直到人工给出结论。",
        "numeric_only": False,
    },
}



def _make_issue_id(idx: int, column: str, message: str,
                   evidence_filter=None, row_numbers=None) -> str:
    """稳定且可跨缓存/DB 对齐的 AI 问题 id。

    #35：不能用 LLM 自由生成的 message 做哈希——同一问题每轮措辞不同会导致 id 漂移，
    用户刚确认过的结论无法继承。优先用「列 + 定位条件 + 可疑行号」这些数据事实；
    完全没有定位条件时才退化到去掉数字/空白的文案前缀。
    """
    parts = [str(column)]
    conds = []
    for f in (evidence_filter or []):
        if isinstance(f, dict):
            conds.append("%s:%s:%s" % (f.get("column"), f.get("op"), f.get("value")))
    parts.extend(sorted(conds))
    rn = sorted(int(x) for x in (row_numbers or []) if isinstance(x, int))
    if rn:
        parts.append("rows:" + ",".join(map(str, rn)))
    if len(parts) == 1:
        norm = "".join(ch for ch in str(message) if not ch.isdigit() and not ch.isspace())[:24]
        parts.append(norm or "generic")
    digest = hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()[:8]
    return "ai-%02d-%s" % (idx, digest)


@dataclass
class AIQualityIssue:
    """AI发现的质检问题（2026-11-13 起带完整证据链，供前端下钻真实明细数据）"""
    severity: str  # "blocking" 或 "warning"
    column: str
    message: str
    detail: str
    type: str = "ai"
    row_count: int = 0
    sample_values: List[str] = field(default_factory=list)
    rule: str = "AI数据质量检测"
    repair_options: List[Dict] = field(default_factory=list)
    # ↓ 证据链：人话结论 / 判断依据 / 涉及字段 / 核对建议 / 可定位条件
    ai_issue_id: str = ""
    plain_conclusion: str = ""
    basis: str = ""
    involved_columns: List[str] = field(default_factory=list)
    check_suggestion: str = ""
    evidence_filter: List[Dict] = field(default_factory=list)
    row_numbers: List[int] = field(default_factory=list)
    # ↓ #34：AI 签发的修复建议（只签 patch，不直接改数据）
    repair_plan: Dict = field(default_factory=dict)


@dataclass
class AIQualityResult:
    """AI质检结果"""
    issues: List[AIQualityIssue]
    summary: Dict[str, Any]
    # AI 判断时真实看到的前 8 行样本 —— 用户可据此核对「AI 到底依据什么下的结论」
    evidence_sample: List[Dict] = field(default_factory=list)
    sample_columns: List[str] = field(default_factory=list)


class AIQualityChecker:
    """
    AI 数据质量补充检测器
    
    规则检测完成后，对数据样本进行AI分析，识别：
    - 数据分布异常（如数值字段存在极端离群值）
    - 语义异常（如字段值不符合业务语义）
    - 字段关联矛盾（如多个字段组合不符合业务规则）
    - 潜在的数据质量问题（如数据倾斜、编码混乱）
    """
    
    def __init__(self, duckdb_manager, table_name: str, columns: List[Dict], config: Optional[Dict] = None):
        self.db = duckdb_manager
        self.table_name = table_name
        self.columns = columns
        self.config = config or {}
    
    def _collect_sample_data(self, max_rows: int = 50) -> List[Dict]:
        """收集数据样本用于AI分析（统计信息用单次STRAIGHT聚合查询合并，避免逐列多次全表扫描）"""
        col_names = [c["name"] for c in self.columns[:10]]  # 最多取10列
        col_str = ', '.join([f'"{c}"' for c in col_names])

        # 获取样本数据（含空值，让AI也看到空值情况）
        rows = self.db.conn.execute(f"""
            SELECT {col_str} 
            FROM {self.table_name} 
            LIMIT {max_rows}
        """).fetchall()

        # 总行数（单次）
        total = self.db.conn.execute(f"SELECT COUNT(*) FROM {self.table_name}").fetchone()[0]

        # 单次聚合查询同时算所有字段的统计，避免每列4次全表扫描
        agg_exprs = []
        for c in self.columns[:10]:
            cname = c["name"]
            agg_exprs.append(f'COUNT("{cname}") AS "nonnull_{cname}"')
            agg_exprs.append(f'COUNT(DISTINCT "{cname}") AS "uniq_{cname}"')
            agg_exprs.append(
                f'SUM(CASE WHEN "{cname}" IS NULL OR CAST("{cname}" AS VARCHAR) = \'\' '
                f'THEN 1 ELSE 0 END) AS "null_{cname}"'
            )
        agg_sql = "SELECT " + ", ".join(agg_exprs) + f" FROM {self.table_name}"
        agg_row = self.db.conn.execute(agg_sql).fetchone()

        stats = {}
        for i, c in enumerate(self.columns[:10]):
            cname = c["name"]
            # 每列固定占3个位置：nonnull / uniq / null，按位置取值最稳（不依赖列名）
            non_null = int(agg_row[i * 3] or 0)
            unique = int(agg_row[i * 3 + 1] or 0)
            null_count = int(agg_row[i * 3 + 2] or 0)
            total = int(total or 0)

            # 取样例值（仅对非空值，DISTINCT 去重）
            samples = self.db.conn.execute(f"""
                SELECT DISTINCT CAST("{cname}" AS VARCHAR) 
                FROM {self.table_name} 
                WHERE "{cname}" IS NOT NULL 
                LIMIT 10
            """).fetchall()

            stats[cname] = {
                "type": c.get("type", "unknown"),
                "total_rows": total,
                "non_null": non_null,
                "null_count": null_count,
                "null_rate": round(null_count / total, 4) if total > 0 else 0,
                "unique_values": unique,
                "sample_values": [str(r[0]) for r in samples[:5]]
            }

        return {
            "columns": [{"name": c["name"], "type": c.get("type", "unknown")} for c in self.columns[:10]],
            "stats": stats,
            # 2026-11-12：样本 20 行→8 行，配合下方 1200 字符截断，把真实 prompt
            # 从 5.3k 压到约 2.3k；推理模型不再把 token 烧在 reasoning 上。
            "sample_rows": [dict(zip(col_names, r)) for r in rows[:8]]
        }
    
    def _build_prompt(self, sample_data: Dict, existing_issues: List[Dict]) -> str:
        """构建 AI 分析提示词（被控版·精简，2026-11-12）。

        背景：原提示词约 5.3k 字符、强制 AI 输出 repair_options（后端其实会按规则
        重算，属于纯浪费 token）、样本 20 行/3000 字符；推理模型在长 prompt 下把
        max_tokens 全部消耗在 reasoning，content 为空 → 质检「AI 补充检测」连续失败。
        精简为约 2.3k 字符、样本 8 行/1200 字符、最多 5 条问题、不要求 repair_options，
        实测首打 provider 2.6–7.4s 返回合法 JSON。
        """
        col_desc = []
        for c in sample_data["columns"]:
            s = sample_data["stats"].get(c["name"], {})
            col_desc.append(
                f"- {c['name']} ({c['type']}): 非空{s.get('non_null', '?')}/{s.get('total_rows', '?')}行, "
                f"空值率{s.get('null_rate', 0)}, 唯一值{s.get('unique_values', '?')}个, "
                f"样例: {s.get('sample_values', [])[:3]}"
            )

        existing_desc = "无"
        if existing_issues:
            existing_desc = "\n".join([
                f"- [{i.get('severity', 'warning')}] {i.get('column', '?')}: {i.get('message', '?')}"
                for i in existing_issues[:8]
            ])

        columns_desc = chr(10).join(col_desc)
        sample_rows_json = json.dumps(sample_data['sample_rows'], ensure_ascii=False, default=str)[:1200]
        _first = next(iter(sample_data.get("stats", {}).values()), {}) or {}
        stats_desc = (
            f"总行数 {_first.get('total_rows', '?')}；字段数 {len(sample_data['columns'])}；"
            "各列空值率/唯一值/样例见上方表结构。"
        )

        # 内置默认（外置文件缺失时的回退）：与 prompts/ai_quality_checker.md 同构
        default_prompt = f"""你是数据质量分析师。规则引擎已完成检测，请只补充规则未覆盖的潜在问题，最多5条，不重复报告已有问题。只返回合法JSON，不要解释文字、不要推理过程、不要代码块围栏。

## 表结构
{columns_desc}

## 数据统计
{stats_desc}

## 数据样本（前8行）
```json
{sample_rows_json}
```

## 规则已发现的问题
{existing_desc}

## 检测角度
数据分布异常、类型一致性（"文本型数字"应转数值；编号/ID 类列虽像数字但语义是标识，必须保持文本、不要误报）、语义异常、字段关联矛盾、编码异常、数据完整性。

## 输出格式（字段名固定）
{_EVIDENCE_OUTPUT_FORMAT}

{_EVIDENCE_CONTRACT}

字段名必须来自表结构；不需要输出 repair_options（由规则引擎按类型自动生成）。无新问题则返回 {{"issues":[]}}。"""

        prompt = load_prompt(
            "ai_quality_checker",
            default_prompt,
            columns=columns_desc,
            stats=stats_desc,
            sample_rows=sample_rows_json,
            existing_issues=existing_desc,
        )
        # 提示词中心若存在管理员旧版覆盖（只要求 message/detail），强制补回证据链契约：
        # 否则「查看明细数据」的证据字段会被旧覆盖静默抹掉。
        # #34：旧覆盖可能已含证据链但缺修复策略，判断条件必须用最新的 repair_plan，
        # 否则「确认属实后没有修复策略」会被旧覆盖静默抹掉。
        if "repair_plan" not in prompt:
            prompt += "\n## 输出格式（证据链 + 修复策略版，覆盖上方旧格式）\n" + _EVIDENCE_OUTPUT_FORMAT + _EVIDENCE_CONTRACT
        return prompt

    async def analyze(self, existing_issues: Optional[List[Dict]] = None) -> AIQualityResult:
        """执行 AI 质检分析（#41：输出形状容错 + 一次确定性 JSON-FIX + 白盒留痕）。

        2026-11-12：精简 prompt + 禁推理 + 恢复 JSON-FIX + 诚实失败信号。
        2026-11-16（#41）：网关只保证「合法 JSON」，不保证形状。旧实现只认顶层
        {"issues":[...]}，模型偶发换成语义等价形状就把一次成功的 AI 调用判成整链失败，
        正是用户反复反馈的「AI 补充检测连续失败」同类根因。现在统一走
        llm_json_contract：等价形状归一 → 无法确定时【重新调用 AI】做一次确定性
        JSON-FIX → 仍不符才诚实判失败，并把真实形状写进 failure_reason / summary。
        绝不把解析失败伪装成「发现 0 个问题」。
        """
        sample_data = self._collect_sample_data()
        prompt = self._build_prompt(sample_data, existing_issues or [])

        # Task #702：预算统一从 ai_budget 单一真相源读取，不再在本文件硬编码
        from app.core.ai_budget import (
            budget_for, chain_budget, chain_summary, green_badge, node_result,
        )
        from app.core.llm_json_contract import (
            coerce_issues_payload, describe_shape, build_json_fix_messages,
        )
        _qb = budget_for("quality")
        gateway = get_llm_gateway()
        request = LLMRequest(
            prompt=prompt,
            json_mode=True,
            max_tokens=int(_qb["max_tokens"]),  # 防止推理模型把额度烧在 reasoning
            temperature=0.3,
            timeout=float(_qb["timeout"]),
        )
        fallback = {"issues": [], "note": "AI质检服务暂不可用，已跳过AI补充检测"}

        import asyncio
        import time
        _chain_s = float(chain_budget("quality"))
        deadline = time.monotonic() + _chain_s

        async def _call_llm(req: LLMRequest, messages=None, retries=None) -> LLMResponse:
            """首调与形状修复共用同一个整链 deadline，防止 FIX 把总预算撑破。"""
            remain = deadline - time.monotonic()
            if remain <= 0.5:
                return LLMResponse(success=False, content="",
                                   error="AI质检总预算已耗尽（含形状修复）")
            # #33：整次调用按「剩余总预算」夹紧，耗尽前停止 failover
            req.total_timeout = remain
            try:
                return await asyncio.wait_for(
                    gateway.chat_complete(
                        req, fallback, messages=messages,
                        max_retries=int(_qb["retries"]) if retries is None else int(retries),
                    ),
                    timeout=remain,
                )
            except asyncio.TimeoutError:
                return LLMResponse(
                    success=False, content="",
                    error="AI质检总时长超%ss（含provider failover + 1次形状修复），规则兜底" % _chain_s,
                )

        first = await _call_llm(request)
        raw_payload = first.response_json if first.success else None
        output_shape = describe_shape(raw_payload)
        issues_raw, provenance = coerce_issues_payload(raw_payload)

        json_fix_attempted = False
        json_fix_succeeded = False
        output_shape_fix = None
        effective = first
        if (issues_raw is None and first.success and not first.fallback_used
                and raw_payload is not None):
            # 一次确定性 JSON-FIX：重新调用 AI，把上次真实输出回灌，要求按契约原样重发。
            # 不是规则补丁、不是静默吞掉；失败就诚实判失败，绝不伪装成 0 个问题。
            json_fix_attempted = True
            fix_req = LLMRequest(
                prompt=prompt, json_mode=True,
                max_tokens=int(_qb["max_tokens"]),
                temperature=0.0,
                timeout=float(_qb["timeout"]),
            )
            fix_msgs = build_json_fix_messages(prompt, raw_payload, output_shape)
            fixed = await _call_llm(fix_req, messages=fix_msgs, retries=0)
            fix_payload = fixed.response_json if fixed.success else None
            output_shape_fix = describe_shape(fix_payload)
            fixed_raw, fixed_prov = coerce_issues_payload(fix_payload)
            if fixed_raw is not None and fixed.success and not fixed.fallback_used:
                issues_raw = fixed_raw
                provenance = "json_fix:" + (fixed_prov or "unknown")
                json_fix_succeeded = True
                effective = fixed

        issues: List[AIQualityIssue] = []
        parse_error: Optional[str] = None
        valid_cols = [str(c["name"]) for c in self.columns]
        if issues_raw is not None:
            for idx, raw in enumerate(issues_raw[:4]):
                if not isinstance(raw, dict):
                    continue
                try:
                    col = str(raw.get("column", "未知"))
                    # 涉及字段只保留表结构里真实存在的列名，杜绝 AI 臆造列导致 SQL 报错
                    inv = [str(x) for x in (raw.get("involved_columns") or [])
                           if str(x) in valid_cols and str(x) not in ()][:6]
                    if col in valid_cols and col not in inv:
                        inv.insert(0, col)
                    if not inv:
                        inv = [col] if col in valid_cols else []

                    # 定位条件白名单：列名必须真实、op 必须在白名单，值交给参数化查询
                    ef: List[Dict] = []
                    for f in (raw.get("evidence_filter") or [])[:4]:
                        if not isinstance(f, dict):
                            continue
                        fc, op = str(f.get("column", "")), str(f.get("op", "eq"))
                        if fc in valid_cols and op in _EVIDENCE_OPS:
                            ef.append({"column": fc, "op": op, "value": f.get("value")})

                    rns: List[int] = []
                    for x in (raw.get("row_numbers") or [])[:8]:
                        try:
                            v = int(x)
                            if 1 <= v <= 8:
                                rns.append(v)
                        except (TypeError, ValueError):
                            pass

                    message = str(raw.get("message", ""))
                    detail = str(raw.get("detail", ""))
                    plain = str(raw.get("plain_conclusion", "")).strip()
                    basis = str(raw.get("basis", "")).strip()
                    suggestion = str(raw.get("check_suggestion", "")).strip()
                    # 诚实兜底：AI 没给证据字段时用已知事实拼可读说明，绝不编造判断依据
                    if not plain:
                        plain = message or detail or "AI 提示该字段可能存在异常，建议查看明细数据核对"
                    if not basis:
                        basis = detail or "AI 未给出具体判断依据，请直接查看下方真实明细数据自行核对"
                    if not suggestion:
                        suggestion = "打开「查看明细数据」，核对涉及字段的真实取值；确认无误可标记「无需处理」。"

                    # #34：AI 修复建议必须落到白名单里；AI 自造策略 / 缺字段时诚实降级为
                    # keep_as_is，绝不把不可信的策略透传给执行端点。
                    rp_raw = raw.get("repair_plan") if isinstance(raw.get("repair_plan"), dict) else {}
                    rp_strategy = str(rp_raw.get("strategy", "")).strip()
                    if rp_strategy not in AI_REPAIR_STRATEGIES:
                        rp_strategy = "keep_as_is"
                    rp_meta = AI_REPAIR_STRATEGIES[rp_strategy]
                    rp_reason = str(rp_raw.get("reason", "")).strip()[:200]
                    rp_risk = str(rp_raw.get("risk", "")).strip()[:200]
                    if rp_strategy == "keep_as_is" and not rp_reason:
                        rp_reason = "AI 未给出可靠的自动修复依据，建议保留原值并在明细中人工核对"
                    if not rp_risk:
                        rp_risk = rp_meta["risk"]
                    repair_plan = {
                        "strategy": rp_strategy,
                        "label": rp_meta["label"],
                        "description": rp_meta["description"],
                        "reason": rp_reason,
                        "risk": rp_risk,
                        "target_value": str(rp_raw.get("target_value", ""))[:100],
                        "numeric_only": rp_meta["numeric_only"],
                        "source": "ai",
                    }

                    issues.append(AIQualityIssue(
                        severity=str(raw.get("severity", "warning")),
                        column=col,
                        message=message,
                        detail=detail,
                        row_count=int(raw.get("row_count", 0) or 0),
                        sample_values=[str(v) for v in (raw.get("sample_values", []) or [])][:5],
                        rule="AI数据质量检测",
                        repair_options=[],
                        ai_issue_id=_make_issue_id(idx, col, message, ef, rns),
                        plain_conclusion=plain,
                        basis=basis,
                        involved_columns=inv,
                        check_suggestion=suggestion,
                        evidence_filter=ef,
                        row_numbers=rns,
                        repair_plan=repair_plan,
                    ))
                except Exception as e:
                    print(f"[AI质检] 解析问题失败: {e}")
        elif first.success:
            _fix_desc = ("已重新调用 AI 做 1 次确定性形状修复（%s）"
                         % ("成功" if json_fix_succeeded else "仍未通过")) \
                if json_fix_attempted else "首调形状即可判定，未触发修复"
            parse_error = (
                "AI 返回 JSON 形状不符合 issues 契约：%s；%s" % (output_shape, _fix_desc)
                if raw_payload is not None else "AI 返回内容无法解析为 JSON"
            )
        # LLM 全链失败时 parse_error 保持 None，由 llm_called=False 触发诚实失败

        llm_called = bool(effective.success and not effective.fallback_used)
        ai_failed = (not llm_called) or parse_error is not None
        failure_reason = None
        if ai_failed:
            failure_reason = parse_error or effective.error or "LLM 全链失败，已使用兜底结果"
            print(f"[AI质检] AI 未真正参与，原因: {failure_reason}")

        blocking_count = sum(1 for i in issues if i.severity == "blocking")
        # #41：AI「真的被调用」不等于 AI「真正把住了质量关」。输出形状不符且
        # 确定性 FIX 仍失败时，本次结果不可用，节点契约与绿标必须诚实降级，
        # 绝不能出现 ai_failed=True 却 ai_governed=True / 绿标点亮的自相矛盾。
        ai_effective = bool(llm_called and not ai_failed)
        # 统一链路契约：质检只有 1 个 AI 节点，AI 未产出可用结果即 rule_fallback
        _q_node = node_result(
            "quality", by="ai" if ai_effective else "rule_fallback",
            llm_called=ai_effective, fallback_used=not ai_effective,
            reason=failure_reason, latency_ms=int(effective.duration_ms or 0),
        )
        _q_gov = chain_summary([_q_node], chain="quality")
        return AIQualityResult(
            issues=issues,
            summary={
                "total_issues": len(issues),
                "blocking_count": blocking_count,
                "warning_count": len(issues) - blocking_count,
                "ai_analyzed": llm_called,   # 原来恒为 True，全链失败也自称「已分析」
                "llm_called": llm_called,
                # 链路级同源：网关降级 或 AI 输出不可用都算规则接管，前端据此处置
                "fallback_used": bool(_q_gov["fallback_used"] or effective.fallback_used),
                "ai_failed": ai_failed,
                "ai_effective": ai_effective,
                "failure_reason": failure_reason,
                "model": effective.model,
                "duration_ms": effective.duration_ms,
                # Task #702 统一口径：AI 覆盖率 / 全链掌权 / 绿标资格 / 链路预算
                "ai_coverage": _q_gov["ai_coverage"],
                "ai_governed": _q_gov["ai_governed"],
                "ai_badge_eligible": green_badge(_q_gov),
                "by_node": _q_gov["by_node"],
                "chain_budget_s": _q_gov["total_budget_s"],
                "node_budget": _qb,
                # #41 白盒：真实形状、归一来源、确定性修复的真实结果
                "output_shape": output_shape,
                "output_shape_after_fix": output_shape_fix,
                "output_contract": provenance or "unresolved",
                "json_fix_attempted": json_fix_attempted,
                "json_fix_succeeded": json_fix_succeeded,
            },
            evidence_sample=sample_data.get("sample_rows", []),
            sample_columns=[str(c["name"]) for c in sample_data["columns"]],
        )
