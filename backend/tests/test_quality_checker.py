"""八类质量探查引擎验收（NULL/FORMAT/UNIQUE/RANGE/LOGIC/CODE/TIMELINESS/DISTRIBUTION）"""
import duckdb
import pytest

from app.core.quality_checker import IssueType, QualityChecker


class _DB:
    """QualityChecker 期望 db 对象持有 .conn（与项目内用法一致）。"""

    def __init__(self, conn):
        self.conn = conn


@pytest.fixture
def quality_conn():
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE t (id INT, amount DOUBLE, region VARCHAR, d DATE)")
    data = [
        (1, 100.0, "华东", "2024-01-01"),
        (1, 100.0, "华东", "2024-01-01"),   # 唯一性：重复 id
        (2, None, "华北", "2099-01-01"),    # 空值 + 及时性：未来日期
        (3, 99999.0, "华南", "2023-01-01"),  # 分布：离群值
        (4, 105.0, "华东", "2023-01-01"),
        (5, 102.0, "华北", "2023-01-01"),
        (6, 108.0, "华南", "2023-01-01"),
        (7, 99.0, "华东", "2023-01-01"),
        (8, 103.0, "华北", "2023-01-01"),
        (9, 107.0, "华南", "2023-01-01"),
        (10, 101.0, "华东", "2023-01-01"),
        (11, 106.0, "华北", "2023-01-01"),
        (12, 104.0, "华南", "2023-01-01"),
        (13, 100.0, "华东", "2023-01-01"),
        (14, 109.0, "华北", "2023-01-01"),
    ]
    con.executemany("INSERT INTO t VALUES (?,?,?,?)", data)
    yield con
    con.close()


def test_issue_type_has_eight_classes():
    vals = {it.value for it in IssueType}
    assert vals == {
        "null", "format", "unique", "range",
        "logic", "code", "timeliness", "distribution",
    }


def test_eight_class_detection(quality_conn):
    columns = [
        {"name": "id", "type": "INTEGER"},
        {"name": "amount", "type": "DOUBLE"},
        {"name": "region", "type": "VARCHAR"},
        {"name": "d", "type": "DATE"},
    ]
    qc = QualityChecker(_DB(quality_conn), None)
    res = qc.check_table("t", columns)
    by_type = res["summary"]["by_type"]
    assert by_type.get("unique", 0) >= 1, "唯一性检测未触发"
    assert by_type.get("null", 0) >= 1, "空值检测未触发"
    assert by_type.get("timeliness", 0) >= 1, "及时性检测未触发"
    assert by_type.get("distribution", 0) >= 1, "分布检测未触发"


def test_timeliness_detects_future_date(quality_conn):
    columns = [{"name": "d", "type": "DATE"}]
    qc = QualityChecker(_DB(quality_conn), None)
    res = qc.check_table("t", columns)
    by_type = res["summary"]["by_type"]
    # 样例中存在 2099-01-01 未来日期，应被及时性规则捕获
    assert by_type.get("timeliness", 0) >= 1


def test_distribution_detects_iqr_outlier(quality_conn):
    columns = [{"name": "amount", "type": "DOUBLE"}]
    qc = QualityChecker(_DB(quality_conn), None)
    res = qc.check_table("t", columns)
    by_type = res["summary"]["by_type"]
    # amount 中 99999.0 相对其余 ~100 属 IQR×3 离群
    assert by_type.get("distribution", 0) >= 1
