# -*- coding: utf-8 -*-
"""B2 回归（night42）：build_fact_pack 应跳过 distinct_count > max_cardinality 的分类字段。

真实代码缺陷（TASK0_AUDIT B2 / night37 遗留）：max_cardinality 参数声明但未使用，
高基数字段（如 user_id、订单号）会进入 category_facts，既带来噪声又浪费 SQL 探查。
修复后：distinct_count > max_cardinality 的分类字段在探查前直接跳过。
"""
import asyncio
import duckdb

from app.core.data_fact_pack import build_fact_pack


class _StubDB:
    """仅提供 .conn（真实内存 DuckDB 连接）+ table_exists，满足 build_fact_pack 的只读需求。"""

    def __init__(self, conn):
        self.conn = conn

    def table_exists(self, table_name):
        return True


def _make_table(conn):
    conn.execute(
        """
        CREATE TABLE t (
            id INTEGER,
            low_cat VARCHAR,
            high_cat VARCHAR,
            amount DOUBLE
        )
        """
    )
    rows = []
    for i in range(300):
        low = ["A", "B", "C"][i % 3]
        high = "H%d" % (i % 100)
        rows.append((i, low, high, float(i)))
    conn.executemany("INSERT INTO t VALUES (?, ?, ?, ?)", rows)


def test_max_cardinality_filters_high_cardinality():
    conn = duckdb.connect(":memory:")
    _make_table(conn)
    db = _StubDB(conn)
    profiles = [
        {"name": "low_cat", "distinct_count": 3},
        {"name": "high_cat", "distinct_count": 100},
    ]
    pack = asyncio.run(build_fact_pack(db, "t", field_profiles=profiles, max_cardinality=30))
    cats = pack["category_facts"]
    assert "low_cat" in cats, "低基数字段应进入 category_facts"
    assert "high_cat" not in cats, "高基数字段(distinct>max)应被过滤掉"
    assert cats["low_cat"]["distinct"] == 3


def test_no_profiles_includes_all_low_cardinality():
    """无 field_profiles 时（prof_idx 空），过滤条件不触发，不误杀任何分类字段。"""
    conn = duckdb.connect(":memory:")
    _make_table(conn)
    db = _StubDB(conn)
    pack = asyncio.run(build_fact_pack(db, "t", field_profiles=None, max_cardinality=30))
    cats = pack["category_facts"]
    assert "low_cat" in cats
    assert "high_cat" in cats
