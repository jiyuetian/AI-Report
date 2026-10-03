"""
重算引擎（night15-16 Task I：下游重算一致性 C-16）

事件驱动 + 异步重算队列 + 依赖图 + 一致性校验 的编排核心。

数据流：
  数据修改事件(change) ──notify_data_change──▶ 解析受影响下游指标(DependencyGraph)
        │                                              │
        │                                              ▼
        └── 触发 recalc_id（rule_id 回链：记录 trigger）  生成队列任务(pending)
                                                       │
                                           execute_recalc（按依赖图分层执行）
                                                       │
                              ┌────────────────────────┼────────────────────────┐
                              ▼                        ▼                        ▼
                        METRIC_REGISTRY            RecalcValidator         计时(perf)
                        计算新旧值                  前后对比/合理性            per-metric
                                                       │
                                                       ▼
                                              队列状态 done/failed + 历史留痕

复用（对应指令「复用现有组件」）：
- lineage_service 下游遍历语义 → DependencyGraph（内存版，零 DB）
- CrudChainGuard rule_id 回链思想 → 每条 recalc 记录 recalc_id + trigger，可追溯
- METRIC_REGISTRY.calculate → 指标计算（确定性、零 DB，红线④）
- ISS-045 退避机制 → _recalc_backoff = min(8*(retry+1),45)，瞬时异常按此退避重试

红线：全程不碰生产 DuckDB；重算结果仅内存态；失败如实记录，不编造。
"""

import time
from typing import Dict, Any, List, Optional, Callable

# 复用 ISS-045 退避公式；优先直接用 llm_gateway 的同名函数，缺失则原地等价实现
try:  # pragma: no cover - 正常环境可导入
    from app.core.llm_gateway import _backoff_wait as _recalc_backoff  # type: ignore
except Exception:  # pragma: no cover
    def _recalc_backoff(retry: int) -> float:
        """指数退避等待（秒）：8*(retry+1)，封顶 45s（与 ISS-045 一致）。"""
        return min(8 * (retry + 1), 45)


class RecalcEngine:
    """下游重算引擎（进程内、内存态、零 DB）。"""

    def __init__(self, dependency_graph=None, metric_registry=None, validator=None):
        if dependency_graph is None:
            from app.core.dependency_graph import DependencyGraph
            dependency_graph = DependencyGraph()
        if metric_registry is None:
            from app.core.metric_registry import METRIC_REGISTRY
            metric_registry = METRIC_REGISTRY
        if validator is None:
            from app.core.recalc_validator import RecalcValidator
            validator = RecalcValidator()
        self.graph = dependency_graph
        self.registry = metric_registry
        self.validator = validator

        self._history: List[Dict[str, Any]] = []   # recalc 记录（含 recalc_id/trigger/结果）
        self._counter = 0
        self._lock = None  # 进程内单线程验证无需锁；保留扩展位

    # ---- 事件触发 ----
    def notify_data_change(self, change: Dict[str, Any]) -> Dict[str, Any]:
        """监听数据修改事件：解析下游受影响指标，入队（pending），返回 recalc_id。

        change: {scope?, metric_names?, trigger_action?, trigger_source?, note?}
        """
        affected = self.graph.get_affected_metrics(change or {})
        self._counter += 1
        recalc_id = f"rc_{int(time.time() * 1000)}_{self._counter}"
        record = {
            "recalc_id": recalc_id,
            "trigger": change or {},
            "trigger_action": (change or {}).get("trigger_action"),
            "trigger_source": (change or {}).get("trigger_source"),
            "affected": affected,
            "affected_count": len(affected),
            "status": "pending",
            "created_at": time.time(),
            "started_at": None,
            "finished_at": None,
            "results": [],
            "validator": None,
            "timing": None,
            "error": None,
        }
        self._history.append(record)
        return {
            "success": True,
            "recalc_id": recalc_id,
            "affected": affected,
            "affected_count": len(affected),
            "status": "pending",
            "message": (
                f"已触发下游重算「{recalc_id}」：修改范围"
                f"「{(change or {}).get('scope') or (change or {}).get('metric_names')}」"
                f"影响 {len(affected)} 个下游指标"
            ),
        }

    # ---- 执行 ----
    def execute_recalc(
        self,
        recalc_id: Optional[str] = None,
        data_provider: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """执行重算队列（指定 recalc_id 或所有 pending）。

        data_provider: 提供每个指标的数据，支持两种形态：
          - dict: {metric_key: {"data":{...}} 或 {"old_data":{...},"new_data":{...}}}
          - callable(metric_key) -> 同上
        未提供 → 仅标记 affected 但无法计算（honest：如实记录 skipped）。
        """
        targets = [r for r in self._history if r["status"] == "pending"]
        if recalc_id:
            targets = [r for r in self._history if r["recalc_id"] == recalc_id and r["status"] == "pending"]
        if not targets:
            return {"success": True, "executed": 0, "message": "无待执行重算任务"}

        total_ok, total_fail = 0, 0
        for rec in targets:
            rec["status"] = "running"
            rec["started_at"] = time.time()
            affected = rec["affected"]
            order_levels = self.graph.get_execution_order(affected)
            results: List[Dict[str, Any]] = []
            old_values: Dict[str, Optional[float]] = {}
            new_values: Dict[str, Optional[float]] = {}
            timing: Dict[str, float] = {}
            try:
                for level in order_levels:  # 同层可并行（此处顺序执行，层级信息保留）
                    for mk in level:
                        _t0 = time.perf_counter()
                        data = self._provide(data_provider, mk)
                        res = self._calc_one(mk, data)
                        timing[mk] = round((time.perf_counter() - _t0) * 1000, 3)
                        results.append(res)
                        if res.get("success"):
                            new_values[mk] = res.get("value")
                            od = (data or {}).get("old_data") if isinstance(data, dict) else None
                            if od is not None:
                                old_r = self._calc_one(mk, {"data": od})
                                old_values[mk] = old_r.get("value") if old_r.get("success") else None
                        else:
                            new_values[mk] = None
                # 一致性校验
                val_res = self.validator.validate_recalculation(old_values, new_values)
                cons_res = self.validator.check_consistency(
                    results, change_scope=(rec["trigger"] or {}).get("scope"), graph=self.graph
                )
                rec["results"] = results
                rec["validator"] = {"before_after": val_res, "consistency": cons_res}
                rec["timing"] = timing
                rec["status"] = "done" if cons_res["ok"] else "done_with_warnings"
                total_ok += sum(1 for r in results if r.get("success"))
                total_fail += sum(1 for r in results if not r.get("success"))
            except Exception as e:  # 整条重算异常 → 标记 failed，诚实记录
                rec["status"] = "failed"
                rec["error"] = f"{type(e).__name__}: {e}"
            rec["finished_at"] = time.time()

        return {
            "success": True,
            "executed": len(targets),
            "metrics_ok": total_ok,
            "metrics_failed": total_fail,
            "message": f"执行 {len(targets)} 条重算任务：成功指标 {total_ok}、失败 {total_fail}",
            "records": [
                {
                    "recalc_id": r["recalc_id"],
                    "status": r["status"],
                    "affected_count": r["affected_count"],
                    "validator": r["validator"],
                    "timing": r["timing"],
                }
                for r in targets
            ],
        }

    def _provide(self, data_provider: Optional[Any], metric_key: str) -> Optional[Dict[str, Any]]:
        if data_provider is None:
            return None
        if callable(data_provider):
            try:
                return data_provider(metric_key)
            except Exception:
                return None
        if isinstance(data_provider, dict):
            return data_provider.get(metric_key)
        return None

    def _calc_one(self, metric_key: str, data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """单指标重算（带 ISS-045 退避重试；仅对瞬时异常重试，确定性失败不重试）。"""
        if not data or "data" not in data:
            return {
                "success": False, "metric": metric_key,
                "error": "未提供该指标的重算数据(data_provider 缺此指标)",
            }
        last_err = None
        for retry in range(3):  # 最多 3 次（含首试），瞬时异常退避
            try:
                return self.registry.calculate(metric_key, data["data"], operation="query")
            except Exception as e:  # 瞬时异常（网络/IO 等；本场景几乎不发生，因零 DB）
                last_err = e
                if retry < 2:
                    time.sleep(_recalc_backoff(retry))
        return {
            "success": False, "metric": metric_key,
            "error": f"重算异常（重试 3 次仍失败）：{type(last_err).__name__}: {last_err}",
        }

    # ---- 查询 ----
    def get_status(self, recalc_id: Optional[str] = None) -> Dict[str, Any]:
        if recalc_id:
            rec = next((r for r in self._history if r["recalc_id"] == recalc_id), None)
            if not rec:
                return {"success": False, "error": f"未找到重算任务 {recalc_id}"}
            return {"success": True, "recalc_id": recalc_id, **self._public(rec)}
        pending = sum(1 for r in self._history if r["status"] == "pending")
        running = sum(1 for r in self._history if r["status"] == "running")
        done = sum(1 for r in self._history if r["status"].startswith("done"))
        failed = sum(1 for r in self._history if r["status"] == "failed")
        return {
            "success": True,
            "queue": {"pending": pending, "running": running, "done": done, "failed": failed},
            "total": len(self._history),
            "latest": self._public(self._history[-1]) if self._history else None,
        }

    def list_history(self) -> Dict[str, Any]:
        return {
            "success": True,
            "count": len(self._history),
            "history": [self._public(r) for r in self._history],
        }

    def get_stats(self) -> Dict[str, Any]:
        """性能统计：累计重算指标数、平均/最大耗时（per-metric）。"""
        all_t: Dict[str, List[float]] = {}
        total_metrics = 0
        for r in self._history:
            for mk, ms in (r.get("timing") or {}).items():
                all_t.setdefault(mk, []).append(ms)
                total_metrics += 1
        per_metric = {
            mk: {
                "calls": len(v),
                "avg_ms": round(sum(v) / len(v), 3),
                "max_ms": round(max(v), 3),
            }
            for mk, v in all_t.items()
        }
        return {
            "success": True,
            "total_recalculations": total_metrics,
            "distinct_metrics": len(per_metric),
            "per_metric": per_metric,
        }

    def recover(self, recalc_id: str) -> Dict[str, Any]:
        """错误恢复：把该次重算标记为 recovered，并交还重算前快照。"""
        rec = next((r for r in self._history if r["recalc_id"] == recalc_id), None)
        if not rec:
            return {"success": False, "error": f"未找到重算任务 {recalc_id}"}
        rec["status"] = "recovered"
        before = (rec.get("validator") or {}).get("before_after") if rec.get("validator") else None
        snap = self.validator.recover({"recalc_id": recalc_id, "before_after": before})
        return {"success": True, "recalc_id": recalc_id, **snap}

    # ---- 内部 ----
    def _public(self, rec: Dict[str, Any]) -> Dict[str, Any]:
        """对外脱敏视图（含 recalc_id 回链信息）。"""
        return {
            "recalc_id": rec["recalc_id"],
            "status": rec["status"],
            "trigger_action": rec.get("trigger_action"),
            "trigger_source": rec.get("trigger_source"),
            "scope": (rec.get("trigger") or {}).get("scope"),
            "affected_count": rec["affected_count"],
            "affected": rec["affected"],
            "results": rec.get("results"),
            "validator": rec.get("validator"),
            "timing": rec.get("timing"),
            "error": rec.get("error"),
            "created_at": rec.get("created_at"),
            "finished_at": rec.get("finished_at"),
        }


# 全局单例（队列/历史保留在进程内）
RECLAC_ENGINE = RecalcEngine()
