"""端到端冒烟：验证本轮优化（LLM 不可达短路降级 / 图表消毒单值维度 / 主题默认兜底 / 附录四件套）。

运行前置：必须先停掉后端进程（释放 DuckDB 单进程锁），再跑本脚本，最后重启后端。
  cd backend && python _selftest_optimizations.py

覆盖：
  1) detect_theme(use_llm=False) 离线不抛、theme_tag 不为「未知」
  2) _sanitize_charts 丢弃单值维度图表（性别唯一值=1 被丢，状态=3 保留）
  3) brain_run_pipeline 真实跑通：LLM 不可达时走规则兜底、不应挂起 600s；生成看板
  4) appendix_service.build_appendix 返回四件套有数据
  5) 清理冒烟产物（看板 + 运行痕迹）
"""
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))

from app.core.database import async_session_factory
from app.core.brain_modules.s1_theme_detector import detect_theme
from app.api.brain_run_sse import _sanitize_charts, brain_run_pipeline, _check_llm_reachable
from app.core.appendix_service import build_appendix
from app.models.dashboard import Dashboard
from app.models.brain import BrainTrace
from sqlalchemy import select, delete

DATASET_ID = "3b8723d1-a7d2-42fd-a9ed-50f4856a5a0d"


async def smoke():
    # 0) LLM 可达性现状（仅展示，不影响其它断言）
    try:
        probe = await _check_llm_reachable()
        print(f"[SMOKE] LLM reachable={probe.get('reachable')} reason={probe.get('reason')}")
    except Exception as e:
        print(f"[SMOKE] LLM 探测异常: {e}")

    # 1) 主题离线识别
    async with async_session_factory() as db:
        theme = await detect_theme(
            db=db,
            fields=["客户名称", "担保余额", "抵押物评估价值", "贷款金额", "逾期天数"],
            use_llm=False,
        )
    assert theme.get("theme_tag") and theme["theme_tag"] != "未知", theme
    print(f"[SMOKE] detect_theme(offline) -> {theme['theme_tag']} (method={theme.get('method')})")

    # 2) 图表消毒：单值维度过滤
    charts = [
        {"chart_type": "bar", "x_field": "性别", "y_field": "担保余额", "config": {"aggregation": "sum"}},
        {"chart_type": "pie", "x_field": "状态", "y_field": "", "config": {}},
    ]
    cleaned = _sanitize_charts(charts, ["性别", "状态", "担保余额"], {}, {"性别": 1, "状态": 3})
    assert len(cleaned) == 1 and cleaned[0]["x_field"] == "状态", cleaned
    print("[SMOKE] _sanitize_charts 单值维度过滤 OK（保留1张，丢弃单值维度1张）")

    # 3) 端到端流水线
    run_id = "smoke_" + os.urandom(4).hex()
    t0 = time.time()
    async for _ev in brain_run_pipeline(run_id, DATASET_ID, "smoke"):
        pass
    elapsed = time.time() - t0

    async with async_session_factory() as db:
        res = (await db.execute(
            select(Dashboard).where(Dashboard.id.like(f"dash_{DATASET_ID[:8]}%")).order_by(Dashboard.id.desc())
        )).scalars().all()
        dash_id = res[0].id if res else None
    print(f"[SMOKE] 流水线耗时 {elapsed:.1f}s dashboard={dash_id}")
    assert dash_id, "未生成看板"
    assert elapsed < 180, f"耗时异常 {elapsed:.1f}s（疑似挂起，短路降级未生效）"

    # 4) 附录四件套
    async with async_session_factory() as db:
        ap = await build_appendix(db, dash_id)
    fdc = sum(len(d.get("columns", [])) for d in (ap.get("field_dict") or []))
    ln = ap.get("lineage") or {}
    print(
        f"[SMOKE] 附录 field_dict列={fdc} clean_log={len(ap.get('clean_log') or [])} "
        f"metrics={len(ap.get('metrics') or [])} lineage节点={len(ln.get('nodes', []))} 边={len(ln.get('edges', []))}"
    )
    assert fdc > 0 and len(ap.get("metrics") or []) > 0, "附录数据缺失"

    # 5) 清理
    async with async_session_factory() as db:
        await db.execute(delete(Dashboard).where(Dashboard.id == dash_id))
        await db.execute(delete(BrainTrace).where(BrainTrace.run_id == run_id))
        await db.commit()
    print("[SMOKE] 清理完成")


if __name__ == "__main__":
    asyncio.run(smoke())
    print("ALL SMOKE PASSED")
