"""#5 修复验收：动作执行失败不得静默，必须显式回传错误。

覆盖：
- action_executor 各类不可执行动作返回结构化 success=False + error
- chat._surface_action_error 把失败错误写入响应（action_error + message 提示），
  前端据此展示，不再“以为成功”
"""
from app.core.action_executor import execute_action
from app.api.chat import _surface_action_error


def test_delete_chart_when_empty_fails():
    res = execute_action("delete_chart", {}, {"charts": []}, {})
    assert res["success"] is False
    assert "没有可删除" in res["error"]


def test_delete_nonexistent_chart_fails():
    # 执行器本身不强制“至少保留一张图”（该守卫在可行性检查层），
    # 但删除不存在的图应返回失败而非静默成功
    cfg = {"charts": [{"id": "c1", "chart_type": "bar"}]}
    res = execute_action("delete_chart", {"chart_index": 5}, cfg, {})
    assert res["success"] is False
    assert "未找到" in res["error"]


def test_reorder_when_less_than_two_fails():
    cfg = {"charts": [{"id": "c1"}]}
    res = execute_action("reorder_chart", {"direction": "up"}, cfg, {})
    assert res["success"] is False
    assert "不足" in res["error"]


def test_change_chart_no_target_fails():
    cfg = {"charts": []}
    res = execute_action("change_chart", {"target_type": "pie"}, cfg, {})
    assert res["success"] is False
    assert "未找到" in res["error"]


def test_edit_title_unknown_chart_fails():
    cfg = {"charts": [{"id": "c1"}]}
    res = execute_action("edit_title", {"chart_id": "nope", "new_title": "x"}, cfg, {})
    assert res["success"] is False


def test_surface_action_error_writes_action_error_on_failure():
    response_data = {"message": "已为你执行"}
    failure = {"success": False, "error": "看板已满"}
    out = _surface_action_error(failure, response_data)
    assert out["action_error"] == "看板已满"
    assert "看板已满" in out["message"]
    assert "未成功" in out["message"]


def test_surface_action_error_noop_on_success():
    response_data = {"message": "ok"}
    out = _surface_action_error({"success": True, "new_config": {}}, response_data)
    assert "action_error" not in out
    assert out["message"] == "ok"
