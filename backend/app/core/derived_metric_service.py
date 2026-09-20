"""
派生指标识别服务 - 2026-09-17

目标：让血缘的「业务加工层」能白盒展示跨列派生指标的加工公式，
例如：抵押率 = 担保余额 ÷ 抵押物评估价值（×100）

做法：在 DuckDB 数据上做四则运算反推——
对每对数值列 (A, B)，检验是否等于某个候选列 C（含 A/B、A/B×100、A−B、A+B、A×B），
若命中行占比 ≥ 阈值（默认 95%），则认定 C 为派生指标并给出表达式。

为什么不用 LLM 猜：公式是确定性事实，必须可验证。识别结果带 match_ratio，
用户能在血缘页看到"匹配率 100%"，可自行判断是否采信。
"""

from typing import Any, Dict, List, Optional

import numpy as np

# 候选目标列的命名提示（命中提示优先检测，用于控制组合规模）
RATIO_HINTS = ("率", "占比", "比例", "比值", "比重", "比率", "百分比")
DIFF_HINTS = ("差额", "差值", "净额", "净利", "增速", "增幅", "余额差")
AMOUNT_HINTS = ("金额", "总额", "合计", "小计", "总价", "均值", "均价", "单价")

# 参与检测的运算符
OPS = ("div", "div_pct", "sub", "add", "mul")

OP_SYMBOL = {
    "div": "÷",
    "div_pct": "÷ ... ×100",
    "sub": "−",
    "add": "+",
    "mul": "×",
}

NUMERIC_TOKENS = ("DECIMAL", "DOUBLE", "FLOAT", "INT", "BIGINT", "NUMERIC", "REAL")


def _is_numeric(col_type: str) -> bool:
    t = (col_type or "").upper()
    return any(tok in t for tok in NUMERIC_TOKENS)


def _q(name: str) -> str:
    """DuckDB 标识符引号"""
    return '"' + str(name).replace('"', '""') + '"'


def detect_derived_metrics(
    duck: Any,
    table_name: str,
    columns: List[Dict],
    max_rows: int = 5000,
    max_cols: int = 20,
    max_candidates: int = 8,
    min_ratio: float = 0.95,
    rtol: float = 2e-3,
    atol: float = 1e-6,
) -> List[Dict[str, Any]]:
    """
    在给定表上反推派生指标。

    返回：
      [{"metric": "抵押率", "op": "div_pct", "expression": "担保余额 ÷ 抵押物评估价值 × 100",
        "formula": "抵押率 = 担保余额 ÷ 抵押物评估价值 × 100",
        "components": ["担保余额", "抵押物评估价值"],
        "match_ratio": 1.0, "sample_rows": 1000, "valid_rows": 1000}, ...]
    """
    # 不按 schema 声明类型过滤：数值列常被识别成 VARCHAR，会漏掉真正的比率列。
    # 改为对全部列 TRY_CAST 成 DOUBLE 实测，能转出行数的才留下。
    cand_cols = list(columns)[:max_cols]
    if len(cand_cols) < 3:
        return []
    names = [c["name"] for c in cand_cols]
    if not duck.table_exists(table_name):
        return []

    # 只取需要的列，行数截断，避免大表拖慢血缘构建
    sel = ", ".join(f"TRY_CAST({_q(n)} AS DOUBLE) AS {_q(n)}" for n in names)
    try:
        df = duck.conn.execute(
            f"SELECT {sel} FROM {_q(table_name)} LIMIT {int(max_rows)}"
        ).fetchdf()
    except Exception:
        return []
    if df is None or len(df) == 0:
        return []

    mat = df.to_numpy(dtype=float, na_value=np.nan)
    n_rows = mat.shape[0]
    finite = np.isfinite(mat)
    # 有效值过半的列才算"数值列"（日期/文本列 TRY_CAST 后全为 NULL，会被自然淘汰）
    keep = [i for i in range(len(names)) if finite[:, i].mean() >= 0.5]
    if len(keep) < 3:
        return []
    mat = mat[:, keep]
    names = [names[i] for i in keep]
    finite = finite[:, keep]
    stds = np.nanstd(np.where(finite, mat, np.nan), axis=0)

    # 候选目标列：优先命名提示（率/占比/差额…），无提示则全量（截断）
    hinted = [i for i, n in enumerate(names)
              if any(h in str(n) for h in RATIO_HINTS + DIFF_HINTS + AMOUNT_HINTS)]
    candidates = (hinted or list(range(len(names))))[:max_candidates]

    results: List[Dict[str, Any]] = []
    for c in candidates:
        cname = names[c]
        cv = mat[:, c]
        if not np.isfinite(cv).any() or stds[c] == 0 or not np.isfinite(stds[c]):
            continue  # 目标列全空或为常量，无法判定
        best: Optional[Dict[str, Any]] = None

        for a in range(len(names)):
            if a == c:
                continue
            av = mat[:, a]
            if stds[a] == 0 or not np.isfinite(stds[a]):
                continue  # 常量列参与运算无信息量
            for b in range(len(names)):
                if b in (a, c):
                    continue
                bv = mat[:, b]
                if stds[b] == 0 or not np.isfinite(stds[b]):
                    continue

                valid = finite[:, a] & finite[:, b] & finite[:, c]
                n_valid = int(valid.sum())
                if n_valid < 10:
                    continue

                a2, b2, c2 = av[valid], bv[valid], cv[valid]
                tol = atol + rtol * np.abs(c2)

                trials: List[tuple] = []
                if np.count_nonzero(b2) == len(b2):   # 分母无 0 才做除法
                    trials.append(("div", a2 / b2))
                    trials.append(("div_pct", a2 / b2 * 100.0))
                trials.append(("sub", a2 - b2))
                trials.append(("add", a2 + b2))
                trials.append(("mul", a2 * b2))

                for op, pred in trials:
                    if not np.all(np.isfinite(pred)):
                        continue
                    if float(np.std(pred)) == 0.0:
                        continue  # 结果恒定，不构成派生关系
                    ratio = float(np.count_nonzero(np.abs(c2 - pred) <= tol) / n_valid)
                    if ratio < min_ratio:
                        continue
                    # 提示词加权：列名像"率"时优先除法口径
                    score = ratio + (0.02 if (op in ("div", "div_pct")
                                              and any(h in str(cname) for h in RATIO_HINTS)) else 0.0)
                    if best is None or score > best["_score"]:
                        best = {
                            "_score": score,
                            "op": op,
                            "components": [names[a], names[b]],
                            "match_ratio": ratio,
                            "valid_rows": n_valid,
                        }

        if best:
            op = best["op"]
            x, y = best["components"]
            sym = OP_SYMBOL.get(op, "?")
            expression = f"{x} {sym} {y}" if op != "div_pct" else f"{x} ÷ {y} × 100"
            results.append({
                "metric": cname,
                "op": op,
                "expression": expression,
                "formula": f"{cname} = {expression}",
                "components": [x, y],
                "match_ratio": round(best["match_ratio"], 4),
                "sample_rows": n_rows,
                "valid_rows": best["valid_rows"],
            })

    # 同一恒等式只保留一条：A ÷ B = C 与 B × C = A 是同一个关系，
    # 优先保留"列名像比率（率/占比/比重）"的那条，因为那才是业务上要的指标口径
    results = _dedupe(results)

    # 匹配率高的排前面
    results.sort(key=lambda r: -r["match_ratio"])
    return results


def to_map(results: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """把 detect 结果转成 {列名: 指标信息}，便于 S3 / 血缘按字段快速查用"""
    return {r["metric"]: r for r in (results or []) if r.get("metric")}


def recommended_agg(metric_info: Dict[str, Any]) -> str:
    """
    派生指标的安全聚合方式：
      - 比率类（率/占比/比值）求和无业务意义 → 必须 avg
      - 差额/合计类（A−B、A+B）可加总 → sum
    S3 选指标与前端汇总都要遵守，否则「抵押率求和」这类错误口径会直接误导决策。
    """
    op = (metric_info or {}).get("op", "")
    if op in ("div", "div_pct", "mul"):
        return "avg"
    return "sum"


def is_ratio_metric(metric_info: Dict[str, Any]) -> bool:
    return (metric_info or {}).get("op") in ("div", "div_pct", "mul")


def annotate_fields(
    fields_desc: str, derived: Dict[str, Dict[str, Any]]
) -> str:
    """在 S3 的字段描述串里给派生指标追加口径标注（供 LLM 感知加工逻辑）"""
    if not derived:
        return fields_desc
    out = []
    for line in (fields_desc or "").splitlines():
        hit = None
        for name, info in derived.items():
            if name and name in line:
                hit = info
                break
        if hit:
            out.append(
                f"{line.rstrip()}｜派生指标：{hit.get('formula', '')}"
                f"（匹配率 {hit.get('match_ratio', 0):.0%}，安全汇总方式：{recommended_agg(hit)}）"
            )
        else:
            out.append(line)
    return "\n".join(out)


# 互为逆运算的分组：组内视为同一恒等式
_OP_GROUP = {
    "div": "divmul",
    "div_pct": "divmul",
    "mul": "divmul",
    "sub": "addsub",
    "add": "addsub",
}


def _dedupe(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """同一组列的恒等式只保留一条最符合业务语义的公式"""
    groups: Dict[tuple, List[Dict[str, Any]]] = {}
    for r in results:
        # 三列恒等式 A = B × C 会产出三种写法（C = A ÷ B / A = B × C / B = A ÷ C），
        # 涉及的是同一组列，必须按"全部涉及列"分组，否则会重复展示
        involved = frozenset(list(r["components"]) + [r["metric"]])
        key = (involved, _OP_GROUP.get(r["op"], r["op"]))
        groups.setdefault(key, []).append(r)

    kept: List[Dict[str, Any]] = []
    for items in groups.values():
        if len(items) == 1:
            kept.append(items[0])
            continue
        # 1) 目标列名像比率且用的是除法口径 → 最优先
        ratio_like = [r for r in items
                      if r["op"] in ("div", "div_pct")
                      and any(h in str(r["metric"]) for h in RATIO_HINTS)]
        if ratio_like:
            kept.append(max(ratio_like, key=lambda r: r["match_ratio"]))
            continue
        # 2) 否则取匹配率最高的一条
        kept.append(max(items, key=lambda r: r["match_ratio"]))
    return kept
