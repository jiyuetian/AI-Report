"""pytest 公共 fixtures：后端依赖的测试基础设施。

运行方式（在 backend/ 目录）：
    python -m pytest tests/ -q
"""
import os
import sys

import pandas as pd
import pytest

# 确保 backend 目录在 sys.path，使 `app` 包可导入
BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.core.duckdb_manager import DuckDBManager  # noqa: E402


@pytest.fixture
def duck_mgr(tmp_path):
    """每个测试一个独立的 DuckDB 实例（落盘到 pytest 临时目录，自动清理）。"""
    db_file = str(tmp_path / "test.duckdb")
    mgr = DuckDBManager(db_path=db_file)
    yield mgr
    mgr.close()


@pytest.fixture
def layer_df():
    """含有 数值/分类/日期 字段的样例数据集（可支撑 L1/L2/L4 物化）。"""
    return pd.DataFrame({
        "id": [1, 2, 3, 4, 5],
        "amount": [100.0, 200.0, 150.0, 300.0, 250.0],
        "region": ["华东", "华北", "华南", "华东", "华北"],
        "d": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"],
    })


@pytest.fixture
def text_only_df():
    """纯文本数据集（无数值/分类/日期字段，用于验证 L4 聚合跳过与 0 图提示）。"""
    return pd.DataFrame({
        "备注": ["a", "b", "c"],
        "序号": ["1", "2", "3"],
    })
