"""
回归测试：brain_run status 端点对"后端重启/中断"与"自动恢复"语义的处理。

覆盖三类场景：
1. summary 标 running 但 updated_at > 3 分钟 → 视为 interrupted → status=unknown
2. summary 标 running 且未超时 → 透传返回 running
3. run_id 完全查不到但前端给了 dataset_id → 反查最近 published dashboard
"""
import asyncio
import uuid
from datetime import datetime, timedelta
from sqlalchemy import delete

from app.core.database import async_session_factory
from app.models.brain import BrainTraceSummary
from app.models.dashboard import Dashboard
from app.api.brain_run_sse import get_run_status


async def _seed_running_summary(run_id: str, dataset_id: str, minutes_ago: int):
    async with async_session_factory() as s:
        row = BrainTraceSummary(
            run_id=run_id,
            dataset_id=dataset_id,
            user_id='test',
            overall_status='running',
            current_stage='S3',
        )
        row.updated_at = datetime.now() - timedelta(minutes=minutes_ago)
        row.created_at = datetime.now() - timedelta(minutes=minutes_ago)
        s.add(row)
        await s.commit()


async def _seed_published_dashboard(dataset_id: str, dash_id: str, name: str = 'auto-recovered'):
    async with async_session_factory() as s:
        row = Dashboard(
            id=dash_id,
            name=name,
            primary_dataset_id=dataset_id,
            config={"chart_count": 3},
            status='published',
            score=88.0,
        )
        s.add(row)
        await s.commit()


async def _cleanup_summary(run_id: str):
    async with async_session_factory() as s:
        await s.execute(delete(BrainTraceSummary).where(BrainTraceSummary.run_id == run_id))
        await s.commit()


async def _cleanup_dashboard(dash_id: str):
    async with async_session_factory() as s:
        await s.execute(delete(Dashboard).where(Dashboard.id == dash_id))
        await s.commit()


def test_status_stale_running_is_interrupted():
    """回归：后端重启后，DB summary 显示 running 但超过 3 分钟没动 → 应识别为 interrupted"""
    run_id = f"run-stale-{uuid.uuid4().hex[:8]}"
    dataset_id = f"ds-stale-{uuid.uuid4().hex[:8]}"
    asyncio.run(_seed_running_summary(run_id, dataset_id, minutes_ago=5))
    try:
        res = asyncio.run(get_run_status(run_id))
        assert res["status"] == "unknown", f"stale running 应被识别为 unknown，实际 {res['status']}"
        assert res["detail"].get("interrupted") is True
        assert "已被服务端清理" in res["message"] or "已被清除" in res["message"]
    finally:
        asyncio.run(_cleanup_summary(run_id))


def test_status_recent_running_passes_through():
    """回归：summary 是 running 且刚更新 → 应透传为 running（继续轮询）"""
    run_id = f"run-fresh-{uuid.uuid4().hex[:8]}"
    dataset_id = f"ds-fresh-{uuid.uuid4().hex[:8]}"
    asyncio.run(_seed_running_summary(run_id, dataset_id, minutes_ago=0))
    try:
        res = asyncio.run(get_run_status(run_id))
        assert res["status"] == "running", f"新鲜 running 应透传，实际 {res['status']}"
    finally:
        asyncio.run(_cleanup_summary(run_id))


def test_status_dataset_id_recovers_latest_dashboard():
    """
    回归：run_id 完全找不到 + 前端传了 dataset_id → 反查最近 published 看板 → completed
    这是用户实际遇到的"未找到该后台任务"问题的根因修复。
    """
    dataset_id = f"ds-recov-{uuid.uuid4().hex[:8]}"
    dash_id = f"dash-{uuid.uuid4().hex[:8]}"
    asyncio.run(_seed_published_dashboard(dataset_id, dash_id))
    try:
        fake_run = f"run-ghost-{uuid.uuid4().hex[:8]}"
        res = asyncio.run(get_run_status(fake_run, dataset_id=dataset_id))
        assert res["status"] == "completed", f"按 dataset 应自动恢复为 completed，实际 {res['status']}"
        assert res["detail"]["dashboard_id"] == dash_id
        assert res["detail"]["recovered_by_dataset"] is True
    finally:
        asyncio.run(_cleanup_dashboard(dash_id))