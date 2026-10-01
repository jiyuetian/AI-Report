"""链路规则引擎 - night14 Task C。

用一份 YAML 描述一组有序的数据清洗规则（链路），逐条执行：
- **fail-fast**：任一规则抛异常（或返回非 success 状态且开启 fail-fast）即停止整条链路，
  并回链到出错的 rule_id，便于定位「链路断在哪一条」；
- **rule_id 回链**：每条规则必须带唯一 rule_id，执行结果逐条标注 rule_id，
  与 DataCleaner 的随机 8 位 id 不同，这里用 YAML 里可读、可复现的 id；
- **改 schema/数据前备份**：每条规则执行前对目标表做快照
  `<table>_chainbak_<rule_id>`，使按 rule_id 的真回滚成为可能
  （替代 DataCleaner.rollback 里「建议重新导入原始数据」的 TODO 占位）。

不依赖生产 DuckDB：调用方传入 DataCleaner（其 `.db.conn` 为 DuckDB 连接）。
"""
from __future__ import annotations

import yaml
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, asdict


@dataclass
class ChainRule:
    """链路中的单条规则（来自 YAML）。"""
    rule_id: str
    table: str
    issue_type: str
    column: str
    strategy: str
    params: Dict[str, Any] = field(default_factory=dict)
    fail_fast: Optional[bool] = None  # 单条覆盖整条链路的 fail_fast

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ChainRule":
        rid = d.get("rule_id")
        if not rid:
            raise ValueError("每条链路规则必须带唯一 rule_id")
        return cls(
            rule_id=str(rid),
            table=d["table"],
            issue_type=d.get("issue_type", "unknown"),
            column=d["column"],
            strategy=d["strategy"],
            params=d.get("params") or {},
            fail_fast=d.get("fail_fast"),
        )


class CleanChainEngine:
    """按 YAML 链路顺序执行清洗规则，fail-fast + rule_id 回链 + 改前备份。"""

    def __init__(self, cleaner, backup_prefix: str = "_chainbak"):
        """
        Args:
            cleaner: DataCleaner 实例（其 .db.conn 为 DuckDB 连接）
            backup_prefix: 备份表名前缀
        """
        self.cleaner = cleaner
        self.conn = cleaner.db.conn
        self.backup_prefix = backup_prefix

    # ---- YAML 加载 ----
    @staticmethod
    def load_yaml_text(text: str) -> Dict[str, Any]:
        spec = yaml.safe_load(text)
        if not isinstance(spec, dict):
            raise ValueError("链路 YAML 顶层必须是 mapping（含 rules 列表）")
        return spec

    @staticmethod
    def load_yaml_file(path: str) -> Dict[str, Any]:
        with open(path, "r", encoding="utf-8") as f:
            return CleanChainEngine.load_yaml_text(f.read())

    def _parse_rules(self, spec: Dict[str, Any]) -> List[ChainRule]:
        raw = spec.get("rules")
        if not isinstance(raw, list) or not raw:
            raise ValueError("链路必须包含非空的 rules 列表")
        rules = [ChainRule.from_dict(r) for r in raw]
        ids = [r.rule_id for r in rules]
        if len(ids) != len(set(ids)):
            dup = sorted({i for i in ids if ids.count(i) > 1})
            raise ValueError(f"rule_id 必须唯一，发现重复: {dup}")
        return rules

    def _backup(self, table: str, rule_id: str) -> Optional[str]:
        """apply 前对目标表做快照（改 schema/数据前备份）。返回备份表名，失败返回 None。"""
        bak = f"{table}{self.backup_prefix}_{rule_id}"
        try:
            self.conn.execute(f'DROP TABLE IF EXISTS "{bak}"')
            self.conn.execute(f'CREATE TABLE "{bak}" AS SELECT * FROM "{table}"')
            return bak
        except Exception:
            return None

    def run(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """执行整条链路，返回带 rule_id 回链的结果。"""
        chain_fail_fast = bool(spec.get("fail_fast", True))
        rules = self._parse_rules(spec)

        applied: List[Dict[str, Any]] = []
        failed_rule_id: Optional[str] = None
        failed_error: Optional[str] = None

        for rule in rules:
            rule_fail_fast = chain_fail_fast if rule.fail_fast is None else rule.fail_fast
            bak = self._backup(rule.table, rule.rule_id)
            try:
                res = self.cleaner.execute_fix(
                    table_name=rule.table,
                    issue_type=rule.issue_type,
                    column=rule.column,
                    strategy=rule.strategy,
                    params=rule.params,
                )
                entry = {
                    "rule_id": rule.rule_id,
                    "strategy": rule.strategy,
                    "table": rule.table,
                    "affected_rows": res.get("affected_rows"),
                    "status": res.get("status", "success"),
                    "backup_table": bak,
                }
                applied.append(entry)
                # 策略显式返回非成功状态且开启 fail-fast → 停下
                if entry["status"] not in ("success",) and rule_fail_fast:
                    failed_rule_id = rule.rule_id
                    failed_error = f"rule {rule.rule_id} 返回状态 {entry['status']}"
                    break
            except Exception as e:  # fail-fast：异常即停，回链 rule_id
                applied.append({
                    "rule_id": rule.rule_id,
                    "strategy": rule.strategy,
                    "table": rule.table,
                    "status": "error",
                    "error": str(e),
                    "backup_table": bak,
                })
                if rule_fail_fast:
                    failed_rule_id = rule.rule_id
                    failed_error = str(e)
                    break

        return {
            "success": failed_rule_id is None,
            "applied": applied,
            "failed_rule_id": failed_rule_id,
            "error": failed_error,
            "message": (
                "链路执行完成"
                if failed_rule_id is None
                else f"fail-fast 在 rule_id={failed_rule_id} 处停止: {failed_error}"
            ),
        }

    def run_yaml_text(self, text: str) -> Dict[str, Any]:
        return self.run(self.load_yaml_text(text))

    def run_yaml_file(self, path: str) -> Dict[str, Any]:
        return self.run(self.load_yaml_file(path))

    def rollback_rule(self, rule_id: str, applied: List[Dict[str, Any]]) -> Dict[str, Any]:
        """按 rule_id 用备份表真回滚（恢复该规则改动前的表，替代 DataCleaner.rollback 的占位）。"""
        match = next(
            (a for a in applied if a.get("rule_id") == rule_id and a.get("backup_table")),
            None,
        )
        if not match:
            return {"status": "error", "message": f"未找到 rule_id={rule_id} 的备份快照（可能未执行或备份失败）"}
        bak = match["backup_table"]
        table = match["table"]
        try:
            self.conn.execute(f'DROP TABLE IF EXISTS "{table}"')
            self.conn.execute(f'ALTER TABLE "{bak}" RENAME TO "{table}"')
            return {"status": "rolled_back", "rule_id": rule_id, "restored_from": bak}
        except Exception as e:
            return {"status": "error", "message": str(e)}
