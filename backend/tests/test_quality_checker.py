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


def test_unique_row_count_reflects_total_duplicate_rows():
    """
    修复回归：唯一性校验的 row_count 不应再固定为 0（BLOCKING 路径）。

    说明：2026-09-17 引入 UNIQ_KEY_RATIO=0.95 唯一度复核——只有"形似主键且实际
    唯一度≥95%"的列才按唯一键 BLOCKING 处理；形似主键但唯一度偏低（如 1:N 业务外键）
    会降级为 WARNING（row_indices=[]，intentional，非原 bug）。本测试改用"真实主键
    偶发重复"场景（唯一度≥95%）以真正走到 BLOCKING 路径，验证 row_count 修复仍有效。
    """
    con = duckdb.connect(":memory:")
    # 真实主键场景：id=1..20 各 1 行，外加 1 个重复值 id=1（共 21 行，20 个不同）
    # 唯一度 = 20/21 ≈ 95.2% ≥ 0.95 → 走 BLOCKING；重复行共 2（两个 id=1）
    con.execute("CREATE TABLE pk (id INT)")
    con.executemany(
        "INSERT INTO pk VALUES (?)",
        [(i,) for i in list(range(1, 21)) + [1]],
    )
    qc = QualityChecker(_DB(con), None)
    res = qc.check_table("pk", [{"name": "id", "type": "INTEGER"}])
    unique_issues = [i for i in res["issues"] if i["type"] == "unique"]
    assert unique_issues, "未触发唯一性阻断项"
    issue = unique_issues[0]
    # 核心断言：BLOCKING 路径的 row_count 必须真实反映"涉及行数"，不能再是 0
    assert issue["row_count"] == 2, (
        f"唯一性问题(BLOCKING) row_count 应为 2（实际重复行数），实际 {issue['row_count']}。"
        "原 bug：_check_unique 把 row_indices 留空 → 前端数量列恒为 0"
    )
    # message 文案要前后一致
    assert "涉及 2 行" in issue["message"]
    # row_indices 要为修复提供全部重复行号（去重/标记/删除都用得上）
    assert len(issue.get("row_indices") or []) == 2
    con.close()
