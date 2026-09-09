"""
字段语义增强（AI 协同） - M2 补强
行业通用做法：schema-aware column annotation（如 DataDoc/DataHub 的字段语义标注、NatSQL 的 schema linking）。
用 LLM 结合"字段名 + 主题(可选抽样值)"给每个字段做业务语义标注，产出比规则更懂中文业务字段的类型/用途，
再与规则推断融合：AI 权威、ID/时间等低风险硬规则保底。按数据集缓存一次，LLM 失败自动回退规则。
"""
import hashlib
import json
from typing import Dict, List, Optional, Any

from app.core.llm_gateway import llm_chat
from app.core.prompt_loader import load_prompt
from app.core.brain_modules.s3_chart_engine_v2 import FieldAnalyzer, FieldType

# 字段标注缓存：hash(fields+theme) -> [{name,type,...}]（进程内，按数据集一次）
_CACHE: Dict[str, List[Dict[str, Any]]] = {}

_VALID_TYPES = {t.value for t in FieldType}  # {"date","number","category","geo","text"}

# 内置默认提示词（外置 prompts/schema_enricher.md 缺失时的回退，与被控版保持同构）
_PROMPT_TPL = """你是一位资深数据建模/BI 专家。请为一张数据表的字段做语义标注，供系统自动生成报表/看板。

【表主题】
{theme}

【字段列表】
{fields}

【任务】
对每个字段输出：
- type: 取值为 category(枚举/分类，适合做分布/对比)、number(数值/指标)、date(时间)、geo(地区)、text(文本标识)
- business_role: 一句话业务含义（面向建看板）
- distribution_ok: 布尔，是否值得做分布/占比/对比（如低基数枚举、或可分组数值）
- chart_hint: 简短图表建议（如"饼图/柱状分布""柱状按取值分布""KPI汇总""散点相关"）
- cardinality: low/mid/high（取值基数，值种类数）
- priority: 0-100 数字，越大越值得优先作为分析维度或指标（避免选主键/明细标识）

【约束】
1. name 必须逐字等于字段列表中的原名，严禁造新字段或加后缀
2. type 要贴合数据实际特征（低基数枚举→category；连续整数/小数→number）
3. 只输出JSON：
{"fields":[{"name":"xx","type":"category","business_role":"","distribution_ok":true,"chart_hint":"","cardinality":"low","priority":80}]}

只输出JSON，不要多余文字。"""


def _cache_key(fields: List[str], theme: str, sample_map: Optional[Dict[str, List]]) -> str:
    raw = json.dumps([fields, theme or "", sample_map or None], ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _fallback_field_annotation(field: str) -> Dict[str, Any]:
    """规则-兜底标注：用 FieldAnalyzer 推断类型，作为 AI 不可用时的降级"""
    t = FieldAnalyzer.infer_field_type(field)
    return {"name": field, "type": t.value, "ai": False}


def enrich_fields(
    fields: List[str],
    theme: str,
    sample_map: Optional[Dict[str, List[Any]]] = None,
    batch_size: int = 14,
) -> Optional[List[Dict[str, Any]]]:
    """
    同步版：尝试用缓存返回；若未缓存且能走 LLM 则异步调用。
    注意：本工具为 async 编排准备，同步入口仅供无 LLM 逻辑自测。
    """
    key = _cache_key(fields, theme, sample_map)
    if key in _CACHE:
        return _CACHE[key]
    return None


async def enrich_fields_async(
    fields: List[str],
    theme: str,
    sample_map: Optional[Dict[str, List[Any]]] = None,
    batch_size: int = 14,
) -> Optional[List[Dict[str, Any]]]:
    """
    LLM 字段语义标注。按数据集缓存一次；失败/字段校验失败返回 None（由调用方规则保底）。
    支持分批调用（LLM 一次看一批字段，避免超长）。
    """
    if not fields:
        return []
    key = _cache_key(fields, theme, sample_map)
    if key in _CACHE:
        return _CACHE[key]

    batches = [fields[i:i + batch_size] for i in range(0, len(fields), batch_size)]
    merged: List[Dict[str, Any]] = []
    ok = True

    def _build_batch_prompt(batch: List[str]) -> str:
        field_lines = "\n".join(f"  - {f}" + (f"（样例: {sample_map[f][:5]}）" if sample_map and sample_map.get(f) else "") for f in batch)
        # 外置被控提示词优先（prompts/schema_enricher.md），缺失回退内置默认
        return load_prompt("schema_enricher", _PROMPT_TPL, theme=theme or "未知", fields=field_lines)

    for batch in batches:
        try:
            resp = await llm_chat(
                prompt=_build_batch_prompt(batch),
                json_mode=True,
                user_id="schema_enricher",
            )
            if not resp.success or not resp.response_json:
                ok = False
                break
            data = resp.response_json
            batch_result = data.get("fields") if isinstance(data, dict) else None
            if not isinstance(batch_result, list):
                ok = False
                break
            merged.extend(batch_result)
        except Exception as e:
            print(f"[SchemaEnricher] LLM 标注失败: {e}")
            ok = False
            break

    if not ok:
        return None

    # 校验/补齐：name 必须是真实字段、type 合法；缺失的用规则兜底
    real = set(fields)
    annotations: List[Dict[str, Any]] = []
    for it in merged:
        name = it.get("name")
        if name not in real:
            continue
        t = it.get("type")
        if t not in _VALID_TYPES:
            t = FieldAnalyzer.infer_field_type(name).value
        annotations.append({
            "name": name,
            "type": t,
            "business_role": it.get("business_role", ""),
            "distribution_ok": bool(it.get("distribution_ok", False)),
            "chart_hint": it.get("chart_hint", ""),
            "cardinality": it.get("cardinality", "mid"),
            "priority": int(it.get("priority", 50)),
            "ai": True,
        })
    covered = {a["name"] for a in annotations}
    for f in fields:
        if f not in covered:
            annotations.append(_fallback_field_annotation(f))

    _CACHE[key] = annotations
    print(f"[SchemaEnricher] 已标注 {len(annotations)} 个字段（主题={theme}），命中缓存后复用")
    return annotations


async def build_semantics(
    fields: List[str],
    theme: str,
    sample_map: Optional[Dict[str, List[Any]]] = None,
) -> Dict[str, Any]:
    """
    融合层：AI 权威 + 规则硬规则保底。
    返回:
      type_map: {field: FieldType}  融合后的字段类型
      meta: {field: {business_role,chart_hint,priority,distribution_ok,cardinality,ai}}
      dim_order: [field,...] 建议优先做分布/对比的维度（按 priority 降序）
      enriched: 是否成功走 AI（False 表示纯规则降级）
    """
    rule_types = {f: FieldAnalyzer.infer_field_type(f) for f in fields}
    enriched = await enrich_fields_async(fields, theme, sample_map)

    type_map: Dict[str, FieldType] = {}
    meta: Dict[str, Dict[str, Any]] = {f: {"business_role": "", "chart_hint": "", "priority": 50,
                                           "distribution_ok": False, "cardinality": "mid", "ai": False}
                                       for f in fields}

    ann_by_name = {a["name"]: a for a in (enriched or [])} if enriched else {}
    for f in fields:
        rule_t = rule_types[f]
        ann = ann_by_name.get(f)
        final_t = rule_t
        if ann:
            # 硬规则保底：ID/编号之类规则判 TEXT 且确为标识，AI 也不可覆盖；时间列规则判 DATE 也保留
            if rule_t in (FieldType.TEXT, FieldType.DATE):
                if _is_hard_id(f) or rule_t == FieldType.DATE:
                    final_t = rule_t
                else:
                    final_t = FieldType(ann["type"]) if ann["type"] in _VALID_TYPES else rule_t
            else:
                final_t = FieldType(ann["type"]) if ann["type"] in _VALID_TYPES else rule_t
        type_map[f] = final_t
        meta[f]["name"] = f

    if ann_by_name:
        for f, ann in ann_by_name.items():
            if f in meta:
                for k in ("business_role", "chart_hint", "priority", "cardinality", "distribution_ok"):
                    if k in ann:
                        meta[f][k] = ann[k]
                meta[f]["ai"] = True

    id_and_date = {f for f in fields if (type_map[f] == FieldType.TEXT and _is_hard_id(f)) or type_map[f] == FieldType.DATE}
    dim_order = [
        f for f in sorted(fields, key=lambda x: -int(meta[x].get("priority", 50)))
        if type_map[f] in (FieldType.CATEGORY, FieldType.GEO) and f not in id_and_date
    ]
    return {"type_map": type_map, "meta": meta, "dim_order": dim_order, "enriched": bool(enriched)}


def _is_hard_id(field: str) -> bool:
    import re
    return any(re.search(p, field, re.IGNORECASE) for p in FieldAnalyzer.ID_PATTERNS)