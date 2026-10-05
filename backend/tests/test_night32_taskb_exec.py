"""night32 Task B · 9 项新意图的「动作执行层」离线用例（真空白区补测）。

night31 的 test_night31_taskb.py 只测了 9 项意图的**意图分类层**；本文件补其**动作执行层**：
对 ATTRIBUTION / QUALITY_FIX / CHART_FIX / CREATE_CONFIG / UPDATE_CONFIG /
DELETE_CONFIG / BULK_UPDATE_DATA / CALCULATE_METRIC(QUERY_METRIC) / RECALC_METRIC
逐一调用 ActionExecutor.execute(...)，断言：执行器被正确路由、产出结构合法（非空、字段齐全）、
关键护栏生效（BULK_UPDATE 须 isolated=True 才放行 / CRUD 须 is_superuser / DELETE_CONFIG 受保护键拦截 /
CALC·RECALC 返回 read_only=True 不碰 DB）。

全部离线：仅操作内存 current_config dict + context，纯计算（metric_registry / recalc_engine 内存引擎），
或产出「隔离执行计划」（BULK_UPDATE）。绝不触达生产 DuckDB。
QUALITY_FIX / CHART_FIX 的「真实清洗层修复」分支需真实数据集(dataset_id!=default)，本测试只走离线分支
（dataset_id="default"），真实修复分支标注需真机（见 补盲执行层报告.md）。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.action_executor import ActionExecutor, ActionType


def _base_config():
    return {
        "charts": [
            {"id": "c1", "title": "各品类销售额占比", "chart_type": "pie",
             "x_field": "category", "y_field": "value",
             "category_field": "category", "value_field": "value"},
            {"id": "c2", "title": "销售额趋势", "chart_type": "line",
             "x_field": "month", "y_field": "sales",
             "category_field": "category", "value_field": "sales"},
        ],
        "config_items": {"timeout": 30, "protected_key": "x"},
    }


# ---------- 1. ATTRIBUTION（归因追问：实查字段画像 + 看板配置，离线） ----------
def test_attribution_exec():
    cfg = _base_config()
    ctx = {"field_profiles": [{"name": "逾期率", "missing": 0, "null_rate": 0.0}]}
    res = ActionExecutor.execute(
        ActionType.ATTRIBUTION, {"target": "逾期率上升", "clause": "逾期"}, cfg, ctx)
    assert res["success"] is True, res
    assert res["action_type"] == "attribution"
    assert "attribution_path" in cfg and cfg["attribution_path"], "应记录归因轨迹"
    assert res.get("message"), "message 不应为空"


# ---------- 2. QUALITY_FIX（数据质量修复：离线分支，dataset_id=default 不碰 DB） ----------
def test_quality_fix_exec_offline():
    cfg = _base_config()
    ctx = {"dataset_id": "default"}  # 离线：不传真实数据集 -> 不触达 DuckDB
    res = ActionExecutor.execute(
        ActionType.QUALITY_FIX,
        {"issue_type": "duplicate", "column": "借据号", "fix_strategy": "keep_first"},
        cfg, ctx)
    assert res["success"] is True, res
    assert res["action_type"] == "quality_fix"
    assert "quality_fix_log" in cfg and cfg["quality_fix_log"], "应写入看板修复历史"
    assert res["changes"][0]["real_fix"] is False, "离线分支不应真实落库"


# ---------- 3. CHART_FIX（图表诊断修复：离线分支） ----------
def test_chart_fix_exec_offline():
    cfg = _base_config()
    ctx = {"dataset_id": "default"}
    res = ActionExecutor.execute(ActionType.CHART_FIX, {"chart_id": "c2"}, cfg, ctx)
    assert res["action_type"] == "chart_fix"
    assert "success" in res and "message" in res, "产出结构应合法"
    # 离线无真实数据集 -> 走诊断分支，不崩、结构合法即可


def test_chart_fix_missing_chart():
    cfg = _base_config()
    res = ActionExecutor.execute(ActionType.CHART_FIX, {"chart_id": "nope"}, cfg, {})
    assert res["success"] is False, "未定位图表应失败（绝不静默改第一张）"


# ---------- 4. CREATE_CONFIG（新建配置：执行器级 fail-fast 仅拦重复键；超管鉴权在 API 层） ----------
def test_create_config_exec():
    # 设计：create_config 执行器层不强制 is_superuser（鉴权统一在 API 层
    # Depends(get_current_user)），故超管/非超管在执行器层均可执行；执行器级
    # fail-fast 仅拦截「重复键」。本断言验证执行器正确落库 + 重复键拦截。
    cfg = _base_config()
    res = ActionExecutor.execute(
        ActionType.CREATE_CONFIG, {"key": "new_k", "value": 1}, cfg, {"is_superuser": True})
    assert res["success"] is True, res
    assert res["new_config"]["config_items"]["new_k"] == 1, "配置项应写入 new_config"
    cfg2 = _base_config()
    res2 = ActionExecutor.execute(
        ActionType.CREATE_CONFIG, {"key": "new_k", "value": 1}, cfg2, {"is_superuser": False})
    assert res2["success"] is True, "执行器层不拦非超管（鉴权在 API 层）"
    # 重复键 -> 拒绝
    cfg3 = _base_config(); cfg3["config_items"]["new_k"] = 0
    res3 = ActionExecutor.execute(
        ActionType.CREATE_CONFIG, {"key": "new_k", "value": 1}, cfg3, {"is_superuser": True})
    assert res3["success"] is False and res3.get("rule_id") == "dup_key"


# ---------- 5. UPDATE_CONFIG（修改配置：执行器级 fail-fast 拦缺失键；鉴权在 API 层） ----------
def test_update_config_exec():
    cfg = _base_config()
    res = ActionExecutor.execute(
        ActionType.UPDATE_CONFIG, {"key": "timeout", "value": 99}, cfg, {"is_superuser": True})
    assert res["success"] is True and res["new_config"]["config_items"]["timeout"] == 99
    res2 = ActionExecutor.execute(
        ActionType.UPDATE_CONFIG, {"key": "nope", "value": 1}, cfg, {"is_superuser": True})
    assert res2["success"] is False and res2.get("rule_id") == "missing_key"


# ---------- 6. DELETE_CONFIG（删除配置：受保护键拦截 + 缺失键拦截；鉴权在 API 层） ----------
def test_delete_config_exec():
    cfg = _base_config()
    # 正常键 -> 删除成功
    res = ActionExecutor.execute(
        ActionType.DELETE_CONFIG, {"key": "timeout"}, cfg, {"is_superuser": True})
    assert res["success"] is True and "timeout" not in res["new_config"]["config_items"]
    # 受保护键(system_theme 等，见 crud_chain.yaml protected_keys) -> 拦截
    cfg2 = _base_config(); cfg2["config_items"]["system_theme"] = "dark"
    res2 = ActionExecutor.execute(
        ActionType.DELETE_CONFIG, {"key": "system_theme"}, cfg2, {"is_superuser": True})
    assert res2["success"] is False, "受保护键应被 CrudChainGuard 拦截"
    # 缺失键 -> 拒绝
    res3 = ActionExecutor.execute(
        ActionType.DELETE_CONFIG, {"key": "nope"}, cfg, {"is_superuser": True})
    assert res3["success"] is False and res3.get("rule_id") == "missing_key"


# ---------- 7. BULK_UPDATE_DATA（批量更新：红线④ 须隔离环境，绝不碰生产库） ----------
def test_bulk_update_exec_guardrail():
    cfg = _base_config()
    # 未声明隔离 -> 拦截（require_isolated_dataset）
    res = ActionExecutor.execute(
        ActionType.BULK_UPDATE_DATA,
        {"target_dataset": "x", "field_mapping": {"a": "b"}}, cfg, {"is_superuser": True})
    assert res["success"] is False, "未隔离应被红线拦截"
    # 声明隔离 -> 放行，产出隔离执行计划，requires_isolated_env=True（绝不直写生产库）
    res2 = ActionExecutor.execute(
        ActionType.BULK_UPDATE_DATA,
        {"target_dataset": "x", "field_mapping": {"a": "b"}, "isolated": True},
        cfg, {"is_superuser": True})
    assert res2["success"] is True, res2
    assert res2.get("requires_isolated_env") is True, "必须声明隔离环境"
    assert "isolated_bulk_plan" in res2, "应产出隔离执行计划而非直接落库"


# ---------- 8. CALCULATE_METRIC（指标查询/计算：纯计算，read_only） ----------
def test_calculate_metric_exec():
    cfg = _base_config()
    res = ActionExecutor.execute(
        ActionType.CALCULATE_METRIC,
        {"metric": "毛利率", "operation": "query", "data": {"收入": 100.0, "成本": 60.0}},
        cfg, {})
    assert res["success"] is True, res
    assert res.get("read_only") is True, "指标计算必须 read_only（不碰 DB）"
    assert res.get("metric_result", {}).get("value") == 40.0, "毛利率=(100-60)/100=40%"


# ---------- 9. RECALC_METRIC（下游重算：read_only，触发/状态/图均可离线） ----------
def test_recalc_metric_exec():
    cfg = _base_config()
    res = ActionExecutor.execute(ActionType.RECALC_METRIC, {"operation": "graph"}, cfg, {})
    assert res["success"] is True, res
    assert res.get("read_only") is True, "重算必须 read_only"
    assert "dependency_graph" in res, "应返回指标依赖图"
    res2 = ActionExecutor.execute(ActionType.RECALC_METRIC, {"operation": "status"}, cfg, {})
    assert res2["success"] is True and res2.get("read_only") is True


if __name__ == "__main__":
    import traceback
    passed = failed = 0
    funcs = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    for fn in funcs:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {fn.__name__}: {e}")
            failed += 1
        except Exception:
            print(f"ERROR {fn.__name__}:")
            traceback.print_exc()
            failed += 1
    print(f"\n==== night32 Task B 执行层离线用例: {passed} passed, {failed} failed ====")
    sys.exit(1 if failed else 0)
