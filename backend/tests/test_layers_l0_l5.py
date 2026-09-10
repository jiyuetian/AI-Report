"""L0–L5 六层架构验收（对齐 PRD 4.9）。

分层约定（来自 DuckDBManager.get_layer_table_name）：
  L0 raw      ds_{id}            原始解析层（建表时即有）
  L1 norm     ds_{id}_norm       字段标准化层（类型转换）
  L2 cleaned  ds_{id}_cleaned    数据清洗层（质量修复）
  L3 processed ds_{id}_processed 业务加工层（灰色预留，按需不强制）
  L4 agg      ds_{id}_agg        聚合计算层（best-effort 预聚合）
  L5 output   ds_{id}_output     看板输出层（生成看板时落 Dashboard.config）
"""
from app.core.duckdb_manager import DuckDBManager


def test_l0_raw_created_on_dataset_table(duck_mgr, layer_df):
    ds = "loan001"
    tbl = duck_mgr.create_dataset_table(ds, layer_df)
    assert tbl == "ds_loan001"
    assert duck_mgr.table_exists("ds_loan001")


def test_layer_table_naming_six_layers(duck_mgr):
    ds = "loan002"
    assert duck_mgr.get_layer_table_name(ds, "raw") == "ds_loan002"
    assert duck_mgr.get_layer_table_name(ds, "norm") == "ds_loan002_norm"
    assert duck_mgr.get_layer_table_name(ds, "cleaned") == "ds_loan002_cleaned"
    assert duck_mgr.get_layer_table_name(ds, "processed") == "ds_loan002_processed"
    assert duck_mgr.get_layer_table_name(ds, "agg") == "ds_loan002_agg"
    assert duck_mgr.get_layer_table_name(ds, "output") == "ds_loan002_output"


def test_dashed_dataset_id_normalized(duck_mgr, layer_df):
    ds = "loan-xyz-9"
    duck_mgr.create_dataset_table(ds, layer_df)
    assert duck_mgr.table_exists("ds_loan_xyz_9")


def test_l1_l2_l4_materialized(duck_mgr, layer_df):
    ds = "loan003"
    duck_mgr.create_dataset_table(ds, layer_df)
    res = duck_mgr.materialize_layers(ds)
    assert set(res.keys()) == {"norm", "cleaned", "agg"}
    assert res["norm"] == "ds_loan003_norm"
    assert res["cleaned"] == "ds_loan003_cleaned"
    assert res["agg"] == "ds_loan003_agg"
    assert duck_mgr.table_exists("ds_loan003_norm")
    assert duck_mgr.table_exists("ds_loan003_cleaned")
    assert duck_mgr.table_exists("ds_loan003_agg")
    # L1/L2 行数与原始一致（原始层表名为 ds_{id} 即 base，非 ds_{id}_raw）
    n = duck_mgr.conn.execute("SELECT COUNT(*) FROM ds_loan003").fetchone()[0]
    assert duck_mgr.conn.execute("SELECT COUNT(*) FROM ds_loan003_norm").fetchone()[0] == n
    assert duck_mgr.conn.execute("SELECT COUNT(*) FROM ds_loan003_cleaned").fetchone()[0] == n


def test_l3_processed_not_auto_created(duck_mgr, layer_df):
    """L3 业务加工层为灰色预留，materialize_layers 不应强制建表。"""
    ds = "loan004"
    duck_mgr.create_dataset_table(ds, layer_df)
    duck_mgr.materialize_layers(ds)
    assert not duck_mgr.table_exists("ds_loan004_processed")


def test_l4_agg_absent_for_text_only(duck_mgr, text_only_df):
    """纯文本数据集无数值指标列，L4 聚合应 best-effort 跳过返回 None。"""
    ds = "txt001"
    duck_mgr.create_dataset_table(ds, text_only_df)
    res = duck_mgr.materialize_layers(ds)
    assert res["agg"] is None
    assert not duck_mgr.table_exists("ds_txt001_agg")


def test_l5_output_naming_convention(duck_mgr):
    """L5 看板输出层命名约定（生成时落 Dashboard.config）。"""
    assert duck_mgr.get_layer_table_name("any", "output") == "ds_any_output"


def test_materialize_idempotent(duck_mgr, layer_df):
    ds = "loan005"
    duck_mgr.create_dataset_table(ds, layer_df)
    r1 = duck_mgr.materialize_layers(ds)
    r2 = duck_mgr.materialize_layers(ds)
    assert r1 == r2
    assert duck_mgr.table_exists("ds_loan005_agg")
