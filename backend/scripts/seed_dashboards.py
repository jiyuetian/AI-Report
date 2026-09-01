"""种子数据脚本：为本地 SQLite 插入示例看板，供前后端打通验收
用法：cd backend && python scripts/seed_dashboards.py
"""
import asyncio
import sys
import os

# 确保能从 backend 目录找到 app 包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, func
from app.core.database import async_session_factory
from app.models.dashboard import Dashboard, DashboardVersion


OWNER = "anonymous"  # 列表接口 user_id 默认值，故种子归属此用户

SEED_DASHBOARDS = [
    {
        "name": "担保风控看板",
        "description": "展示担保业务核心风险指标，含总担保金额、在保笔数、逾期率、不良率",
        "status": "published",
        "score": 85,
        "passed": 1,
        "dataset_ids": ["ds_001", "ds_002"],
        "config": {"theme": "default", "tags": ["风控"]},
    },
    {
        "name": "贷款逾期分析",
        "description": "贷款逾期率趋势与分布分析看板",
        "status": "draft",
        "score": 72,
        "passed": 1,
        "dataset_ids": ["ds_003"],
        "config": {"theme": "default", "tags": ["信贷"]},
    },
    {
        "name": "企业征信监控",
        "description": "企业征信变化监控看板，跟踪最新征信变动",
        "status": "draft",
        "score": None,
        "passed": 0,
        "dataset_ids": [],
        "config": {"theme": "default", "tags": ["征信"]},
    },
    {
        "name": "反欺诈检测",
        "description": "异常交易检测与欺诈风险分析看板",
        "status": "published",
        "score": 90,
        "passed": 1,
        "dataset_ids": ["ds_001"],
        "config": {"theme": "default", "tags": ["反欺诈"]},
    },
    {
        "name": "渠道业绩分析",
        "description": "各渠道业绩对比分析看板",
        "status": "archived",
        "score": 65,
        "passed": 0,
        "dataset_ids": [],
        "config": {"theme": "default", "tags": ["渠道"]},
    },
]


async def main():
    async with async_session_factory() as session:
        existing = (await session.execute(select(func.count()).select_from(Dashboard))).scalar()
        if existing and existing > 0:
            print(f"已有 {existing} 条看板，跳过种子（如需重新插入请先清空 dashboards 表）")
            return

        for i, item in enumerate(SEED_DASHBOARDS, start=1):
            dash = Dashboard(
                name=item["name"],
                description=item["description"],
                status=item["status"],
                score=item["score"],
                passed=item["passed"],
                dataset_ids=item["dataset_ids"],
                config=item["config"],
                created_by=OWNER,
                updated_by=OWNER,
            )
            session.add(dash)
            # 先 flush 让 dash.id 生成，再建立版本关联
            await session.flush()
            # 插入一个初始版本，供版本列表使用
            session.add(DashboardVersion(
                dashboard_id=dash.id,
                version_number=1,
                name="初始版本",
                description="看板创建时的初始存档",
                config_snapshot={"layout": {}, "config": item["config"]},
                created_by=OWNER,
            ))
            print(f"  + {item['name']}")

        await session.commit()
        print("种子数据插入完成。")


if __name__ == "__main__":
    asyncio.run(main())