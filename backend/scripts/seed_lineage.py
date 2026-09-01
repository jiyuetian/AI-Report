"""血缘种子数据：造 datasets/files/clean_rules/charts + 构建六层血缘链路
用于验收时让血缘页渲染真实的六层图谱（文件→字段→清洗→口径→图表）
"""
import asyncio
from sqlalchemy import text, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.models.file import File
from app.models.dataset import Dataset
from app.models.quality import CleanRule
from app.models.chart import Chart
from app.models.dashboard import Dashboard


# ---- 基础数据定义 ----

FILES = [
    {"id": "f_d001", "name": "担保数据.xlsx", "hash": "hash-gw-001", "size": 1248000,
     "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
     "extension": "xlsx", "storage_path": "/data/uploads/guarantee.xlsx"},
    {"id": "f_d002", "name": "贷款逾期数据.xlsx", "hash": "hash-loan-001", "size": 986000,
     "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
     "extension": "xlsx", "storage_path": "/data/uploads/loan_overdue.xlsx"},
    {"id": "f_d003", "name": "企业征信.csv", "hash": "hash-corp-001", "size": 452000,
     "mime_type": "text/csv", "extension": "csv", "storage_path": "/data/uploads/corp_credit.csv"},
]

DATASETS = [
    {
        "id": "ds_001", "file_id": "f_d001", "duckdb_table": "gw_biz_detail",
        "grain": "customer", "row_count": 3560, "quality_score": 92, "status": "ready",
        "name": "担保业务明细",
        "schema_json": {
            "columns": [
                {"name": "担保合同号", "type": "string"},
                {"name": "担保金额", "type": "number",
                 "business_logic": "担保合同签订时约定的最高担保额度之和，单位万元"},
                {"name": "逾期天数", "type": "number"},
                {"name": "逾期率", "type": "rate",
                 "business_logic": "逾期金额 / 在保余额，按月末时点计算"},
                {"name": "不良率", "type": "rate",
                 "business_logic": "五级分类中次级及以下余额 / 在保余额"},
                {"name": "所在区域", "type": "string"},
                {"name": "担保类型", "type": "string"},
            ]
        },
    },
    {
        "id": "ds_002", "file_id": "f_d002", "duckdb_table": "loan_overdue",
        "grain": "row", "row_count": 2100, "quality_score": 88, "status": "ready",
        "name": "贷款逾期明细",
        "schema_json": {
            "columns": [
                {"name": "借据号", "type": "string"},
                {"name": "逾期本金", "type": "number"},
                {"name": "逾期率", "type": "rate",
                 "business_logic": "逾期本金 / 贷款余额，按机构汇总"},
                {"name": "所属机构", "type": "string"},
            ]
        },
    },
    {
        "id": "ds_003", "file_id": "f_d003", "duckdb_table": "corp_credit",
        "grain": "customer", "row_count": 1280, "quality_score": 95, "status": "ready",
        "name": "企业征信变化",
        "schema_json": {
            "columns": [
                {"name": "企业代码", "type": "string"},
                {"name": "征信评分", "type": "number",
                 "business_logic": "征信报告中综合信用评分，分值越高信用越好"},
                {"name": "变动类型", "type": "string"},
            ]
        },
    },
]

CLEAN_RULES = [
    {"dataset_id": "ds_001", "rule_type": "fill_null", "target_field": "担保金额",
     "params": {"method": "median", "fill": 0}, "execution_order": 1},
    {"dataset_id": "ds_001", "rule_type": "remove_duplicate", "target_field": "担保合同号",
     "params": {"keep": "first"}, "execution_order": 2},
    {"dataset_id": "ds_001", "rule_type": "format", "target_field": "所在区域",
     "params": {"trim": True, "upper": False}, "execution_order": 3},
    {"dataset_id": "ds_002", "rule_type": "fill_null", "target_field": "逾期本金",
     "params": {"method": "zeros"}, "execution_order": 1},
]

CHARTS = [
    {"seq": 0, "type": "kpi", "title": "总担保金额", "dataset_id": "ds_001",
     "config_json": {"kpi": "担保金额", "prefix": "¥", "unit": "亿元"}},
    {"seq": 1, "type": "bar", "title": "区域担保金额分布", "dataset_id": "ds_001",
     "config_json": {"x": "所在区域", "y": "担保金额", "aggregate": "sum"}},
    {"seq": 2, "type": "line", "title": "逾期率月度趋势", "dataset_id": "ds_001",
     "config_json": {"x": "月份", "y": "逾期率", "aggregate": "avg"}},
    {"seq": 3, "type": "pie", "title": "担保类型占比", "dataset_id": "ds_001",
     "config_json": {"dimension": "担保类型", "measure": "担保金额"}},
    {"seq": 4, "type": "line", "title": "各机构逾期率对比", "dataset_id": "ds_002",
     "config_json": {"x": "所属机构", "y": "逾期率"}},
    {"seq": 5, "type": "bar", "title": "征信评分分布", "dataset_id": "ds_003",
     "config_json": {"x": "评分区间", "y": "客户数"}},
]


async def ensure_column(session: AsyncSession) -> None:
    """为已存在的空表补充新增列（若缺失）：lineage_nodes.dataset_id、datasets.name"""
    insp = await session.execute(
        text("SELECT count(*) FROM pragma_table_info('lineage_nodes') WHERE name='dataset_id'")
    )
    if not insp.scalar():
        await session.execute(text("ALTER TABLE lineage_nodes ADD COLUMN dataset_id VARCHAR(100)"))
    insp2 = await session.execute(
        text("SELECT count(*) FROM pragma_table_info('datasets') WHERE name='name'")
    )
    if not insp2.scalar():
        await session.execute(text("ALTER TABLE datasets ADD COLUMN name VARCHAR(255)"))
    await session.commit()


async def main() -> None:
    from app.core.lineage_service import LineageService

    async with async_session_factory() as session:
        await ensure_column(session)

        # --- 幂等：基础数据已存在则跳过插入，但血缘始终重建 ---
        has = (await session.execute(select(func.count()).select_from(Dataset))).scalar()

        if not has:
            print("创建 文件/数据集 ...")
            for f in FILES:
                session.add(File(**f))
            await session.flush()

            for d in DATASETS:
                session.add(Dataset(**d))
            await session.flush()

            # 看板（图表归属）
            dash_id = (await session.execute(select(Dashboard.id).limit(1))).scalar()
            if not dash_id:
                raise RuntimeError("没有可用的看板，请先运行 seed_dashboards.py")
            print(f"看板绑定: {dash_id}")

            print("创建 清洗规则 / 图表 ...")
            for r in CLEAN_RULES:
                session.add(CleanRule(
                    dataset_id=r["dataset_id"],
                    rule_type=r["rule_type"],
                    target_field=r["target_field"],
                    params=r["params"],
                    reversible=True,
                    execution_order=r["execution_order"],
                ))
            for c in CHARTS:
                session.add(Chart(
                    dashboard_id=dash_id,
                    dataset_id=c["dataset_id"],
                    type=c["type"],
                    title=c["title"],
                    config_json=c["config_json"],
                    status="ok",
                    sort_order=c["seq"],
                ))
            await session.commit()
        else:
            print(f"基础数据已存在（{has} 条数据集），仅重建血缘 ...")

        # --- 为每个数据集构建并保存六层血缘 ---
        for ds in DATASETS:
            print(f"构建血缘: {ds['id']} ...")
            lineage = await LineageService.build_lineage_for_dataset(
                session, ds["id"], file_id=ds["file_id"]
            )
            await LineageService.save_lineage_to_db(session, ds["id"], lineage)
            print(f"  + {ds['id']}: {lineage['node_count']} 节点, {lineage['edge_count']} 边")

        print("血缘种子数据完成。")


if __name__ == "__main__":
    asyncio.run(main())