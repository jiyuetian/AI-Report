"""
一致性校验器（night15-16 Task I：下游重算一致性 C-16）

职责（对应指令「一致性校验」小节）：
- 重算前后数据对比(validate_recalculation)：标记变化/未变/回归(None 退化)。
- 指标值合理性检查(check_consistency)：有限值、无 None/NaN/Inf；比率类宽松区间。
- 依赖关系验证：被重算指标的上游是否落在本次修改范围内（范围完整性）。
- 错误恢复机制(recover)：把历史快照原样交还，供引擎回滚。

全部为纯函数式确定性检查，不碰任何 DB（红线④）。
"""

from typing import Dict, Any, List, Optional


def _is_finite(x: Any) -> bool:
    try:
        f = float(x)
    except (TypeError, ValueError):
        return False
    return f == f and f not in (float("inf"), float("-inf"))


class RecalcValidator:
    """重算一致性校验。"""

    # 比率类指标的宽松合理性区间（诚实：仅排除明显异常，不误杀高 ROI 等真实值）
    _RATIO_LO = -1000.0   # %
    _RATIO_HI = 1_000_000.0  # %

    def validate_recalculation(
        self,
        old_values: Dict[str, Optional[float]],
        new_values: Dict[str, Optional[float]],
    ) -> Dict[str, Any]:
        """重算前后对比。

        old_values/new_values: {metric_key: value|None}
        - changed：前后都有值且不同
        - unchanged：前后值相同（或都为 None）
        - regressions：旧有值、新为 None（计算退化，属不一致）
        - missing_both：新旧都缺（无法计算）
        """
        keys = sorted(set(old_values) | set(new_values))
        changed, unchanged, regressions, missing_both = [], [], [], []
        for k in keys:
            o = old_values.get(k)
            n = new_values.get(k)
            if o is None and n is None:
                missing_both.append(k)
            elif o is not None and n is None:
                regressions.append(k)
            elif (o is None) != (n is None):
                changed.append({"metric": k, "old": o, "new": n})
            else:
                try:
                    if abs(float(o) - float(n)) < 1e-9:
                        unchanged.append(k)
                    else:
                        changed.append({"metric": k, "old": o, "new": n})
                except (TypeError, ValueError):
                    regressions.append(k)
        consistent = (len(regressions) == 0)
        return {
            "consistent": consistent,
            "total": len(keys),
            "changed": changed,
            "unchanged": unchanged,
            "regressions": regressions,
            "missing_both": missing_both,
            "message": (
                f"重算前后对比：{len(keys)} 个指标，变化 {len(changed)}、未变 {len(unchanged)}、"
                f"退化 {len(regressions)}、双缺 {len(missing_both)}"
                + ("" if consistent else "；存在计算退化（旧有值→None），一致性被破坏")
            ),
        }

    def check_consistency(
        self,
        recalculated: List[Dict[str, Any]],
        change_scope: Optional[str] = None,
        graph=None,
    ) -> Dict[str, Any]:
        """对一批重算结果做合理性 + 依赖完整性检查。

        recalculated: metric_registry.calculate 返回的列表（含 success/value/aggregation 等）。
        """
        violations = []
        ok_count = 0
        for r in recalculated:
            if not r.get("success"):
                # 确定性失败（缺字段/除零）——记为违例但非崩溃
                violations.append({
                    "metric": r.get("metric"),
                    "type": "compute_failed",
                    "detail": r.get("error"),
                })
                continue
            val = r.get("value")
            if not _is_finite(val):
                violations.append({"metric": r.get("metric"), "type": "non_finite", "detail": str(val)})
                continue
            agg = r.get("aggregation")
            if agg == "ratio":
                if not (self._RATIO_LO <= float(val) <= self._RATIO_HI):
                    violations.append({
                        "metric": r.get("metric"), "type": "ratio_out_of_range",
                        "detail": f"{val}% 超出合理区间 [{self._RATIO_LO}, {self._RATIO_HI}]",
                    })
                    continue
            ok_count += 1

        # 依赖完整性：若提供了图与修改范围，校验被重算指标上游是否覆盖
        scope_note = None
        if graph is not None and change_scope:
            affected = set(graph.get_affected_metrics({"scope": change_scope}))
            recalc_keys = {r.get("metric") for r in recalculated if r.get("metric")}
            missing = sorted(affected - recalc_keys)
            if missing:
                scope_note = f"修改范围「{change_scope}」下应重算 {len(affected)} 个，实际缺失：{missing}"
            else:
                scope_note = f"修改范围「{change_scope}」下 {len(affected)} 个下游指标均已重算"

        return {
            "ok": len(violations) == 0,
            "ok_count": ok_count,
            "violation_count": len(violations),
            "violations": violations,
            "scope_note": scope_note,
            "message": (
                f"合理性检查：{ok_count} 个通过，{len(violations)} 个违例"
                + (f"；{scope_note}" if scope_note else "")
            ),
        }

    def recover(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """错误恢复：原样交还快照（引擎据此回滚到重算前状态）。

        诚实说明：指标本身是「按需计算」、无持久值，恢复语义 = 把本次重算标记为已回滚，
        并交还调用方在重算前持有的数据快照，由调用方决定后续（如还原上游源数据）。
        """
        return {
            "recovered": True,
            "snapshot": snapshot,
            "message": "已生成恢复快照；指标为按需计算、无持久状态，请据此还原上游源数据。",
        }
