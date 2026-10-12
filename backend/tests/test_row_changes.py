"""night45 附录 B 行级明细：_build_row_changes 纯函数单测（无需 DB）。

覆盖：①普通值变更 ②行删除（keep_first/drop）③无变更（mark_*）④多行批量。
统一验证「原始文件行/字段/数据问题/清洗策略/清洗前/清洗后/状态」逐行产出正确。
"""
from app.api.quality import _build_row_changes


def test_value_change_and_no_change():
    before = {2: "2023/1/5", 3: "其它", 4: "x"}
    after = {2: "2023-01-05", 3: "其他", 4: "x"}  # 4 未变
    ch = _build_row_changes(before, after, "ds1", "format", "日期", "date_normalize")
    # 仅 2、3 变化；4 不变不产出
    assert len(ch) == 2
    by_row = {c.src_row: c for c in ch}
    assert by_row[2].before_value == "2023/1/5" and by_row[2].after_value == "2023-01-05"
    assert by_row[3].before_value == "其它" and by_row[3].after_value == "其他"
    assert all(c.status == "done" and c.stage == "apply" for c in ch)
    assert all(c.dataset_id == "ds1" and c.field_name == "日期" for c in ch)


def test_row_deleted():
    before = {5: "A001", 12: "A001", 9: "B"}
    after = {5: "A001", 9: "B"}  # 12 被删除
    ch = _build_row_changes(before, after, "ds1", "duplicate", "客户ID", "keep_first")
    assert len(ch) == 1
    assert ch[0].src_row == 12
    assert ch[0].before_value == "A001"
    assert ch[0].after_value == "(整行已删除)"


def test_no_change_mark():
    before = {1: "v", 2: "w"}
    after = {1: "v", 2: "w"}  # mark_* 不改数据
    ch = _build_row_changes(before, after, "ds1", "null", "col", "mark_anomaly")
    assert ch == []


def test_null_before_roundtrip():
    before = {8: None, 9: "3"}
    after = {8: "3450.0", 9: "3"}  # 8 由空值填充
    ch = _build_row_changes(before, after, "ds1", "null", "销售额", "fill_median")
    assert len(ch) == 1
    assert ch[0].src_row == 8
    assert ch[0].before_value is None
    assert ch[0].after_value == "3450.0"
