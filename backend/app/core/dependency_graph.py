"""
指标依赖图（night15-16 Task I：下游重算一致性 C-16）

基于 lineage_service 的「下游影响分析」思想（LineageService.get_impact_analysis 的
downstream BFS 遍历），但作用对象从「数据集字段血缘」换成「派生指标」：
- 每个指标的依赖上游 = 其 data_source（虚拟源节点）+ 显式 metric→metric 边（默认无）。
- 数据修改事件(change_scope) → 解析受影响下游指标(get_affected_metrics)。
- 已解析指标集合 → 拓扑分层(get_execution_order)：同层可并行、跨层需串行。

复用关系：
- 遍历语义对齐 lineage_service.get_impact_analysis（下游 BFS），但为内存、零 DB。
- 不碰任何生产库（红线④）；指标数据由调用方显式提供，本图只管「谁依赖谁」。

使用：
    from app.core.dependency_graph import DependencyGraph
    g = DependencyGraph()
    g.get_affected_metrics({"scope": "risk"})          # → 风控类 4 个指标
    g.get_execution_order(["不良率", "拨备覆盖率"])        # → 分层（此处同层）
"""

from typing import Dict, Any, List, Optional, Set


class DependencyGraph:
    """指标依赖图：上游(源) → 指标；支持受影响解析与拓扑分层。"""

    def __init__(self, metric_registry=None):
        # 延迟导入，避免循环依赖
        if metric_registry is None:
            from app.core.metric_registry import METRIC_REGISTRY
            metric_registry = METRIC_REGISTRY
        self.registry = metric_registry
        self._metrics: List[Dict[str, Any]] = metric_registry.list_metrics()
        # 规范 key → 元信息
        self._by_key: Dict[str, Dict[str, Any]] = {m["key"]: m for m in self._metrics}
        # 别名 → 规范 key（中文名/英文键）
        self._alias: Dict[str, str] = {}
        for m in self._metrics:
            self._alias[m["key"].lower()] = m["key"]
            self._alias[m["name"].lower()] = m["key"]
        # 显式 metric→metric 依赖边（默认空；预留给跨指标推导场景）
        self._edges: Dict[str, Set[str]] = {m["key"]: set() for m in self._metrics}
        # 虚拟源节点：data_source → 指标集合
        self._source_to_metrics: Dict[str, List[str]] = {}
        for m in self._metrics:
            src = m.get("data_source") or ""
            self._source_to_metrics.setdefault(src, []).append(m["key"])

    # ---- 解析 ----
    def _resolve(self, name: str) -> Optional[str]:
        if name is None:
            return None
        return self._alias.get(str(name).strip().lower())

    # ---- 依赖（上游）----
    def get_dependencies(self, metric_name: str) -> Dict[str, Any]:
        """返回某指标的依赖上游：虚拟源节点 + 显式上游指标。"""
        key = self._resolve(metric_name)
        if not key:
            return {"metric": metric_name, "found": False, "sources": [], "upstream_metrics": []}
        m = self._by_key[key]
        upstream = list(self._edges.get(key, set()))
        return {
            "metric": key,
            "name": m["name"],
            "found": True,
            "sources": [m.get("data_source")],
            "upstream_metrics": upstream,
            "category": m["category"],
        }

    # ---- 受影响下游指标 ----
    def get_affected_metrics(self, change: Dict[str, Any]) -> List[str]:
        """根据数据修改事件解析受影响的下游指标 key 列表。

        change 支持三种描述：
          - {"metric_names": [...]}          显式指标（中/英/别名均可）
          - {"scope": "risk"}                按 category（financial/risk/business/other）
          - {"scope": "风控资产表..."}         按 data_source 子串匹配（也兼容 category 名）
        结果再叠加显式 metric→metric 边的下游传递（BFS，对齐 lineage 下游遍历）。
        """
        explicit: Set[str] = set()
        scope = (change or {}).get("scope")
        metric_names = (change or {}).get("metric_names") or []

        if metric_names:
            for nm in metric_names:
                k = self._resolve(nm)
                if k:
                    explicit.add(k)

        if scope:
            scope_low = str(scope).strip().lower()
            # 1) category 精确/包含匹配
            for m in self._metrics:
                if m["category"].lower() == scope_low or scope_low in m["category"].lower():
                    explicit.add(m["key"])
            # 2) data_source 子串匹配
            for m in self._metrics:
                ds = (m.get("data_source") or "").lower()
                if scope_low and scope_low in ds:
                    explicit.add(m["key"])

        if not explicit:
            return []

        # 下游传递（显式边）+ 去重
        affected = set(explicit)
        queue = list(explicit)
        while queue:
            cur = queue.pop()
            # 找出「谁依赖 cur」（即 cur 的下游）
            for mk, ups in self._edges.items():
                if cur in ups and mk not in affected:
                    affected.add(mk)
                    queue.append(mk)
        return sorted(affected)

    # ---- 拓扑分层（执行顺序）----
    def get_execution_order(self, metric_names: List[str]) -> List[List[str]]:
        """对给定指标做拓扑分层：同层可并行、前层先于后层串行。

        返回 list[level]，level 为该层指标 key 列表。无显式依赖时全部同层。
        """
        keys = [self._resolve(n) for n in metric_names if self._resolve(n)]
        keys = sorted(set(keys))
        if not keys:
            return []
        # 仅保留这些 key 内部的依赖关系
        indeg = {k: 0 for k in keys}
        adj: Dict[str, List[str]] = {k: [] for k in keys}
        for k in keys:
            for up in self._edges.get(k, set()):
                if up in indeg:  # 仅统计 key 集合内部的依赖
                    adj[up].append(k)
                    indeg[k] += 1
        # Kahn 分层
        levels: List[List[str]] = []
        remain = dict(indeg)
        ready = [k for k in keys if remain[k] == 0]
        while ready:
            levels.append(sorted(ready))
            nxt = []
            for k in ready:
                for d in adj[k]:
                    remain[d] -= 1
                    if remain[d] == 0:
                        nxt.append(d)
            ready = nxt
        # 理论上无环（默认无边），若有环则把剩余补到最后一层（诚实兜底）
        left = [k for k in keys if remain[k] > 0]
        if left:
            levels.append(sorted(left))
        return levels

    # ---- 可视化导出 ----
    def to_graph_view(self) -> Dict[str, Any]:
        """导出给前端做依赖图可视化的结构。"""
        nodes = []
        for m in self._metrics:
            nodes.append({
                "id": m["key"],
                "name": m["name"],
                "category": m["category"],
                "data_source": m.get("data_source"),
                "upstream": sorted(self._edges.get(m["key"], set())),
            })
        # 源节点
        source_nodes = [
            {"id": f"src::{src}", "name": src or "(未标注来源)", "category": "source"}
            for src in self._source_to_metrics
        ]
        edges = []
        for m in self._metrics:
            if m.get("data_source"):
                edges.append({"from": f"src::{m['data_source']}", "to": m["key"]})
            for up in sorted(self._edges.get(m["key"], set())):
                edges.append({"from": up, "to": m["key"]})
        return {
            "nodes": nodes + source_nodes,
            "edges": edges,
            "categories": sorted({m["category"] for m in self._metrics}),
        }
