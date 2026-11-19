# -*- coding: utf-8 -*-
"""叙事事实校验器（通用，不绑定任何数据集）—— #36 通用性方案的核心模块。

问题背景（2026-11-16 取证）：看板 S4b 的 analysis_text 由 LLM 自由生成，
喂给它的只有图表聚合摘要，没有逐期序列；生成后又没有任何事实校验；
S5 评分卡的 accuracy 只看图表配置结构，因此「叙事里写错数值、写反趋势」
仍可拿到 accuracy=100 / 总分 92.55 并判定通过。

本模块提供与数据集无关的通用能力（纯函数、零 LLM、零网络、零写库）：
1. build_fact_pack_from_rows：从真实明细行生成结构化事实包
   （每个数值列的 min/max/mean/median/首末值/极值标签/严格单调性/斜率/逐期序列）。
2. format_fact_section：把事实包转成 LLM 可引用的「唯一数字来源」提示段，
   并可在重生成时回灌上一版的不符项。
3. guard_narrative：把叙事文本里的数值与趋势断言逐项对照事实包，
   输出 unmatched_numbers / failed_claims / failure_count / score_penalty。

设计原则：失败只给事实与扣分建议，不擅自改写用户可见文案；
任何数据集都能复用；调用方异常一律可降级，绝不阻断主链路。
"""
from __future__ import annotations

import re
import statistics
from typing import Any, Dict, List, Optional

# 只捕获「引用具体数据点」的小数（至少 3 位小数），避开年份、序号、百分点
_DATA_NUMBER_RE = re.compile(r"(?<![\d.])(0\.\d{3,})(?![\d])")
_CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6,
           "七": 7, "八": 8, "九": 9, "十": 10, "两": 2}
_TIME_HINT = ("月份", "日期", "年月", "时间", "季度", "期数", "date", "time", "month", "period")


def _to_float(v: Any) -> Optional[float]:
    try:
        f = float(v)
        return f if f == f and abs(f) != float("inf") else None
    except (TypeError, ValueError):
        return None


def _slope(vals: List[float]) -> float:
    n = len(vals)
    if n < 2:
        return 0.0
    mx = (n - 1) / 2.0
    my = sum(vals) / n
    num = sum((i - mx) * (v - my) for i, v in enumerate(vals))
    den = sum((i - mx) ** 2 for i in range(n))
    return num / den if den else 0.0


def guess_time_column(columns: List[str]) -> Optional[str]:
    """通用时间列识别：按列名提示词匹配，找不到返回 None（事实包仍能工作）。"""
    for c in columns or []:
        low = str(c).lower()
        if any(h in low for h in _TIME_HINT):
            return c
    return None


def build_fact_pack_from_rows(
    rows: List[Dict[str, Any]],
    numeric_columns: Optional[List[str]] = None,
    time_column: Optional[str] = None,
) -> Dict[str, Any]:
    """从真实数据行构造事实包。rows 为 [{"月份": "2025-06", "合规率": 0.97}, ...]。"""
    if not rows:
        return {"columns": {}, "allowed_numbers": [], "row_count": 0,
                "time_column": time_column}
    if time_column is None:
        time_column = guess_time_column(list(rows[0].keys()))
    if not numeric_columns:
        numeric_columns = []
        for k in rows[0].keys():
            if k == time_column:
                continue
            if all(_to_float(r.get(k)) is not None for r in rows if r.get(k) is not None):
                numeric_columns.append(k)

    pack: Dict[str, Any] = {
        "columns": {}, "allowed_numbers": [], "row_count": len(rows),
        "time_column": time_column,
    }
    allowed = set()
    for col in numeric_columns[:8]:
        vals, labels = [], []
        for i, r in enumerate(rows, 1):
            f = _to_float(r.get(col))
            if f is None:
                continue
            vals.append(f)
            labels.append(str(r.get(time_column) or i))
        if not vals:
            continue
        mn, mx = min(vals), max(vals)
        inc = all(vals[i] < vals[i + 1] for i in range(len(vals) - 1))
        dec = all(vals[i] > vals[i + 1] for i in range(len(vals) - 1))
        info = {
            "values": [round(v, 6) for v in vals],
            "labels": labels,
            "min": mn, "max": mx,
            "mean": sum(vals) / len(vals),
            "median": statistics.median(vals),
            "first": vals[0], "last": vals[-1],
            "argmin_label": labels[vals.index(mn)],
            "argmax_label": labels[vals.index(mx)],
            "strictly_increasing": inc,
            "strictly_decreasing": dec,
            "trend": "严格逐期递增" if inc else ("严格逐期递减" if dec else "波动（非单调）"),
            "slope": _slope(vals),
            "distinct_count": len(set(vals)),
        }
        pack["columns"][col] = info
        for v in vals + [info["min"], info["max"], info["mean"], info["median"],
                         info["first"], info["last"]]:
            allowed.add(round(float(v), 4))
    pack["allowed_numbers"] = sorted(allowed)
    return pack


def extract_data_numbers(text: str) -> List[float]:
    return [float(x) for x in _DATA_NUMBER_RE.findall(text or "")]


def check_numbers(text: str, pack: Dict[str, Any], tol: float = 5e-5) -> Dict[str, Any]:
    """叙事里出现的每个数据小数，必须能在事实包里找到（单元格值或统计量）。"""
    allowed = pack.get("allowed_numbers") or []
    nums = extract_data_numbers(text)
    unmatched = sorted({v for v in nums
                        if not any(abs(v - a) <= tol for a in allowed)})
    matched = sorted({v for v in nums if v not in unmatched})
    return {"checked": len(nums), "matched": matched, "unmatched": unmatched,
            "passed": not unmatched}


def _window_below(vals: List[float], threshold: float, n: int) -> bool:
    if n <= 0:
        return False
    run = 0
    for v in vals:
        run = run + 1 if v < threshold else 0
        if run >= n:
            return True
    return False


_TIME_RANGE_RE = re.compile(
    r"(\d{4})年(\d{1,2})月\s*(?:至|到|-|~)\s*(?:(\d{4})年)?(\d{1,2})月"
)


def _norm_ym(x: Any) -> Optional[tuple]:
    m = re.match(r"(\d{4})[-年/](\d{1,2})", str(x))
    return (int(m.group(1)), int(m.group(2))) if m else None


def _window_indices(d: Dict[str, Any], start: str, end: str) -> List[int]:
    """把「YYYY-MM ~ YYYY-MM」映射到事实包逐期序列的下标。"""
    a, b = _norm_ym(start), _norm_ym(end)
    if not a or not b:
        return []
    out = []
    for i, lb in enumerate(d.get("labels") or []):
        t = _norm_ym(lb)
        if t and a <= t <= b:
            out.append(i)
    return out


def check_trend_claims(text: str, pack: Dict[str, Any]) -> Dict[str, Any]:
    """核验「持续攀升 / 逐步下滑 / 连续 N 个月低于 X」这类可验算的断言。

    通用性：若叙事点名了某个数值列，就只按该列的事实判定；没点名才退化为
    「任一列满足即可」，避免 A 列单调就把 B 列的错误趋势断言放行。
    """
    failed: List[Dict[str, str]] = []
    cols = pack.get("columns") or {}
    text = text or ""
    mentioned = [c for c in cols if c and c in text]
    scope = {c: cols[c] for c in mentioned} if mentioned else cols

    up_claims = bool(re.search(r"持续(?:攀升|上升|增长|走高)|逐月(?:上升|攀升)", text))
    down_claims = bool(re.search(r"(?:逐步|持续|连续)(?:下滑|下降|走低|降低|降至)", text))
    if up_claims and not any(d.get("strictly_increasing") for d in scope.values()):
        failed.append({
            "claim": "持续攀升/逐月上升",
            "fact": "涉及列（%s）均非严格逐期递增" % (", ".join(scope) or "全部数值列"),
            "scope": list(scope),
        })
    if down_claims and not any(d.get("strictly_decreasing") for d in scope.values()):
        failed.append({
            "claim": "逐步/持续下滑",
            "fact": "涉及列（%s）均非严格逐期递减，属波动而非单调下滑" % (", ".join(scope) or "全部数值列"),
            "scope": list(scope),
        })

    for m in re.finditer(r"连续\s*([一二三四五六七八九十两\d]+)\s*个?月[^。；;]{0,24}?低于\s*(0?\.\d+)", text):
        raw_n, raw_t = m.group(1), m.group(2)
        n = _CN_NUM.get(raw_n)
        if n is None:
            try:
                n = int(raw_n)
            except ValueError:
                continue
        try:
            threshold = float(raw_t)
        except ValueError:
            continue
        # 通用：断言若自带「YYYY年M月至M月」时间窗，就只在该窗口内验算；
        # 否则退化为整列检查。没有时间窗时不能拿全表任意窗口替用户圆场。
        ctx = text[max(0, m.start() - 90):m.start()]
        tm = None
        for _tm in _TIME_RANGE_RE.finditer(ctx):
            tm = _tm
        window = None
        if tm:
            window = ("%s-%02d" % (tm.group(1), int(tm.group(2))),
                      "%s-%02d" % (tm.group(3) or tm.group(1), int(tm.group(4))))
        hit = False
        for d in scope.values():
            vals = d.get("values") or []
            if window:
                idx = _window_indices(d, window[0], window[1])
                if not idx:
                    continue
                seq = [vals[i] for i in idx if 0 <= i < len(vals)]
            else:
                seq = vals
            if _window_below(seq, threshold, n):
                hit = True
                break
        if not hit:
            failed.append({
                "claim": "连续%s个月低于%s" % (raw_n, raw_t),
                "fact": ("时间窗 %s~%s 内，" % window if window else "涉及列（%s）" % (", ".join(scope) or "全部数值列"))
                        + "均不存在长度 >= %d 的连续低于该阈值的窗口" % n,
                "scope": list(scope),
                "time_window": window,
            })
    return {"failed": failed, "passed": not failed}


def format_fact_section(pack: Dict[str, Any], guard: Optional[Dict[str, Any]] = None,
                        compact: bool = False) -> str:
    """把事实包转成 LLM 提示段：唯一可引用数字来源 + 趋势事实（+ 逐期序列）。

    compact=True 用于主 prompt：省略逐期序列，只给白名单、每列趋势结论与红线，
    把 token 代价压到约 1/3；逐期序列留给「校验失败后的重生成」完整版。
    guard 非空且未通过时，追加上一版叙事的具体不符项，供重生成时逐条改正。
    """
    cols = pack.get("columns") or {}
    if not cols:
        return ""
    lines = ["## 事实包（唯一可引用数字来源，禁止使用本节之外的任何小数）",
             "- 可引用数值：" + ", ".join(
                 "%.4f" % v for v in (pack.get("allowed_numbers") or [])[:60 if compact else 120]),
             "- 数据行数：%d；时间列：%s" % (pack.get("row_count") or 0,
                                          pack.get("time_column") or "未识别")]
    for col, d in cols.items():
        lines.append(
            "- %s：首 %.4f → 末 %.4f；最小 %.4f（%s）；最大 %.4f（%s）；均值 %.4f；中位数 %.4f；趋势 %s"
            % (col, d["first"], d["last"], d["min"], d["argmin_label"],
               d["max"], d["argmax_label"], d["mean"], d["median"], d["trend"])
        )
        if not compact:
            seq = ", ".join("%s=%.4f" % (lb, v)
                            for lb, v in list(zip(d["labels"], d["values"]))[:24])
            lines.append("  逐期序列：" + seq)
    lines.append("## 写作红线（基于事实包，通用适用于任何数据集）")
    lines.append("1. 数字只能逐字引用上面的可引用数值，不得四舍五入到别的值，不得自行推算新小数。")
    lines.append("2. 只有该列标注『严格逐期递增/递减』时才能写『持续攀升/逐步下滑』；"
                 "标注『波动（非单调）』时必须写波动并说明反弹。")
    lines.append("3. 『连续 N 个月低于 X』必须与逐期序列逐项核对，不能凭印象写。")
    lines.append("4. 没有阈值配置或口径依据时，不要写『超过 X 个百分点自动触发』等机制性结论。")
    if guard and not guard.get("passed"):
        lines.append("## 上一版分析摘要的事实错误（必须全部改正，不得再出现）")
        for v in (guard.get("numbers") or {}).get("unmatched") or []:
            lines.append("- 数字 %.4f 不在真实数据中，删除或替换为事实包内的数值" % v)
        for f in (guard.get("trends") or {}).get("failed") or []:
            lines.append("- 断言「%s」不成立：%s" % (f.get("claim"), f.get("fact")))
    return "\n".join(lines)


def guard_narrative(text: str, pack: Dict[str, Any]) -> Dict[str, Any]:
    """主入口：返回可直接接入 S5 评分卡的事实校验结论。"""
    if not (pack.get("columns") or {}):
        return {"passed": True, "failure_count": 0, "score_penalty": 0,
                "numbers": {"checked": 0, "matched": [], "unmatched": [], "passed": True},
                "trends": {"failed": [], "passed": True},
                "skipped": "no_fact_pack",
                "recommendation": "无可校验事实包（数据源不可用），本次跳过叙事事实闸门"}
    numbers = check_numbers(text, pack)
    trends = check_trend_claims(text, pack)
    failures = len(numbers["unmatched"]) + len(trends["failed"])
    return {
        "passed": failures == 0,
        "failure_count": failures,
        "numbers": numbers,
        "trends": trends,
        # 供评分卡使用：每处事实错误扣 8 分，最多扣 40 分
        "score_penalty": min(40, failures * 8),
        "recommendation": ("叙事与原始数据一致" if failures == 0 else
                           "叙事含与原始数据的不符项：把 failure_count 计入 accuracy / overall，"
                           "判不通过，并触发一次基于事实包的重生成"),
    }
