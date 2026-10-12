"""Task A · 对话动作分支运行时回归测试（add / change / delete 真跑 generate_stream）。

回归目标（对应 P0-A/B/C，登记于 ISS-096 / ISS-095）：
  - P0-A/B（ISS-096，潜在缺陷）：generate_stream 内原先对闭包变量 `context` / `current_config`
    赋值，导致前方引用触发 UnboundLocalError，使所有对话请求 ~515ms 即 stream_error。
    修复后改用 `_exec_ctx = dict(context)` / `_fresh_config = dashboard.config or {}`（只读副本）。
  - P0-C（ISS-095，回归）：ISS-025 把 current_user 改为 user_id 字符串，但 1101/1192 两处仍按
    dict 调 `.get`，导致 `'str' object has no attribute 'get'`，所有动作轮 100% 崩。
    修复后 current_user 统一用 `_auth["user_id"]`（str），动作落库 `updated_by = current_user`。

本测试不依赖真实 LLM / 审核 / 可行性服务（全部 mock），直接驱动真实的
`send_message_stream` → `safe_stream` → `generate_stream` → `execute_action` 链路，逐事件收集 SSE，
断言：
  1) 流中不出现 "error" 事件（safe_stream 会吞掉 UnboundLocalError/AttributeError 并转为 error 事件，
     因此"无 error 事件"即证明闭包陷阱与 current_user 类型回归已消除）；
  2) 产出 complete 事件且动作 success=True；
  3) current_user 作为 str 使用（dashboard.updated_by 落库值 == user_id 字符串）不崩；
  4) add / change / delete 三个动作分支均成功，且 dashboard.config 真实落库变更。

运行（在 backend/ 目录，锁 Python 3.12）：
    py -3.12 -m pytest tests/test_chat_action_p0.py -q
"""
import asyncio
import inspect
import json
import os
import sys

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from fastapi import BackgroundTasks
from unittest.mock import AsyncMock, patch

# 确保 backend 在 sys.path（与 conftest 一致）
BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.models.base import Base  # noqa: E402
from app.models.dashboard import Dashboard  # noqa: E402
from app.api.chat import ChatMessageRequest, send_message_stream  # noqa: E402
import app.api.chat as chatmod  # noqa: E402
import app.core.database as dbmod  # noqa: E402


@pytest.fixture
def temp_db(tmp_path):
    """隔离的临时 SQLite：重定向 app.core.database 的 engine / session 工厂。"""
    db_path = tmp_path / "chat_p0_test.db"
    url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(url, future=True)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _create():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    asyncio.run(_create())

    orig_engine = dbmod.engine
    orig_factory = dbmod.async_session_factory
    dbmod.engine = engine
    dbmod.async_session_factory = factory
    try:
        yield factory
    finally:
        dbmod.engine = orig_engine
        dbmod.async_session_factory = orig_factory
        asyncio.run(engine.dispose())


def _plan(actions, intent_type):
    """构造 plan_actions 的 mock 返回值（与 action_planner.plan_actions 返回结构对齐）。"""
    return {
        "primary_intent": {
            "intent_type": intent_type,
            "confidence": 0.95,
            "analysis": {"extracted_params": {}},
            "is_confident": True,
            "classified_by": "rule",
        },
        "is_compound": False,
        "clauses": ["x"],
        "unparsed_clauses": [],
        "actions": actions,
    }


async def _read_config(factory, dash_id="dash1"):
    async with factory() as s:
        dash = (await s.execute(select(Dashboard).where(Dashboard.id == dash_id))).scalar_one()
        return dict(dash.config or {}), dash.updated_by


def test_chat_action_p0_add_change_delete(temp_db):
    """真跑 generate_stream 的 add / change / delete 分支，断言无闭包崩溃且 config 落库。"""
    factory = temp_db
    auth = {"user_id": "test-user", "is_superuser": False}

    async def _drive(actions, intent_type, message):
        """驱动一次真实对话流，返回收集到的 SSE 事件列表（已解析）。"""
        req = ChatMessageRequest(
            message=message, dashboard_id="dash1", session_id=None,
            dataset_id=None, override=False, force_rule_fallback=False)
        async with factory() as db:
            resp = await send_message_stream(req, BackgroundTasks(), db=db, _auth=auth)
            events = []
            async for chunk in resp.body_iterator:
                if not isinstance(chunk, str):
                    chunk = chunk.decode("utf-8")
                if chunk.startswith("data: "):
                    payload = chunk[len("data: "):].strip()
                    if not payload or payload == "[DONE]":
                        continue
                    try:
                        events.append(json.loads(payload))
                    except Exception:
                        continue
        return events

    async def _run():
        with patch("app.core.moderation.check_moderation",
                   return_value={"should_block": False, "boundary_type": None,
                                 "response": {}, "deduct_tokens": True}), \
             patch("app.core.feasibility_checker.check_feasibility",
                   return_value={"feasible": True, "issues": [], "suggestion": "",
                                 "can_override": False, "overridden_issues": []}), \
             patch("app.core.event_logger.log_user_action", lambda *a, **k: None), \
             patch.object(chatmod, "log_ai_action", AsyncMock()):
            # ---- 种子看板：含一张已知图 c1，供 change / delete 定位 ----
            async with factory() as s:
                s.add(Dashboard(
                    id="dash1", name="回归测试看板",
                    config={"charts": [{
                        "id": "c1", "title": "各品类销售额占比", "chart_type": "pie",
                        "x_field": "category", "y_field": "value",
                        "category_field": "category", "value_field": "value",
                    }]},
                    primary_dataset_id=None, dataset_ids=[],
                    created_by="seed", updated_by="seed",
                ))
                await s.commit()

            # ---- 分支 1：add_chart（KPI 单值卡，显式 metric_field，无需数据集字段画像）----
            with patch("app.core.action_planner.plan_actions",
                       return_value=_plan(
                           [{"type": "add_chart",
                             "params": {"chart_type": "kpi", "metric_field": "amount",
                                        "metric_name": "总担保余额"},
                             "clause": "新增总担保余额单值卡"}],
                           "add_chart")):
                events = await _drive(
                    _plan([{"type": "add_chart",
                            "params": {"chart_type": "kpi", "metric_field": "amount",
                                       "metric_name": "总担保余额"}}], "add_chart"),
                    "add_chart", "新增总担保余额单值卡")
                _assert_no_error(events, "add")
                _assert_action_success(events, "add")
                cfg, updated_by = await _read_config(factory)
                charts = cfg.get("charts", [])
                assert len(charts) == 2, f"[add] 应新增 1 图（c1 + 新 KPI），实际={charts}"
                assert updated_by == "test-user", \
                    f"[add] updated_by 应为 str user_id，实际={updated_by!r}（current_user 类型回归）"

            # ---- 分支 2：change_chart（把 c1 由 pie 改成 line）----
            with patch("app.core.action_planner.plan_actions",
                       return_value=_plan(
                           [{"type": "change_chart",
                             "params": {"chart_id": "c1", "target_type": "line"},
                             "clause": "把 c1 改成折线图"}],
                           "change_chart")):
                events = await _drive(
                    _plan([{"type": "change_chart",
                            "params": {"chart_id": "c1", "target_type": "line"}}], "change_chart"),
                    "change_chart", "把各品类销售额占比改成折线图")
                _assert_no_error(events, "change")
                _assert_action_success(events, "change")
                cfg, updated_by = await _read_config(factory)
                charts = cfg.get("charts", [])
                c1 = next((c for c in charts if c["id"] == "c1"), None)
                assert c1 is not None, "[change] c1 应仍存在"
                assert c1["chart_type"] == "line", f"[change] c1 应改为 line，实际={c1['chart_type']}"
                assert len(charts) == 2, f"[change] 图数量应不变（2），实际={charts}"
                assert updated_by == "test-user", \
                    f"[change] updated_by 应为 str user_id，实际={updated_by!r}（current_user 类型回归）"

            # ---- 分支 3：delete_chart（删除 c1）----
            with patch("app.core.action_planner.plan_actions",
                       return_value=_plan(
                           [{"type": "delete_chart",
                             "params": {"chart_id": "c1"},
                             "clause": "删除 c1"}],
                           "unknown")):
                events = await _drive(
                    _plan([{"type": "delete_chart",
                            "params": {"chart_id": "c1"}}], "unknown"),
                    "unknown", "删除各品类销售额占比图")
                _assert_no_error(events, "delete")
                _assert_action_success(events, "delete")
                cfg, updated_by = await _read_config(factory)
                charts = cfg.get("charts", [])
                assert all(c["id"] != "c1" for c in charts), "[delete] c1 应被删除"
                assert len(charts) == 1, f"[delete] 删除后应剩 1 图，实际={charts}"
                assert updated_by == "test-user", \
                    f"[delete] updated_by 应为 str user_id，实际={updated_by!r}（current_user 类型回归）"

    asyncio.run(_run())


def _assert_no_error(events, branch):
    errs = [e for e in events if e.get("event") == "error"]
    assert not errs, f"[{branch}] 流中出现 error 事件（闭包/current_user 回归）：{errs}"


def _assert_action_success(events, branch):
    complete = next((e for e in events if e.get("event") == "complete"), None)
    assert complete is not None, f"[{branch}] 应产出 complete 事件"
    data = complete.get("data")
    if isinstance(data, str):
        data = json.loads(data)
    results = (data or {}).get("action_results") or []
    assert results and results[0].get("success") is True, \
        f"[{branch}] 动作应成功，实际={results}"


def test_chat_p0_closure_fix_present():
    """静态守卫：确认闭包陷阱修复标记仍在（防止回归重新对 context/current_config 赋值）。"""
    src = inspect.getsource(chatmod.send_message_stream)
    assert '_fresh_config = dashboard.config or {}' in src, \
        "P0-B 修复缺失：应使用 _fresh_config 只读副本，而非对闭包变量 current_config 赋值"
    assert '_exec_ctx = dict(context)' in src, \
        "P0-A 修复缺失：应使用 _exec_ctx 副本，而非对闭包变量 context 赋值"
    assert 'current_user = _auth["user_id"]' in src, \
        "P0-C 修复缺失：current_user 应取自 _auth['user_id']（str），而非 dict current_user"
    # 动作执行必须传入只读副本，而不是已变成局部变量的 context / current_config
    assert 'execute_action(' in src
    assert '_fresh_config,' in src and '_exec_ctx' in src, \
        "execute_action 应接收 _fresh_config / _exec_ctx 副本"
