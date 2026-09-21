"""
问题2 回归测试（防截断 + 多字段匹配）—— 不联网、不依赖真实 LLM。

覆盖：
1. Layer1 防截断：「加上每个：A，B，C，D，E 的平均值汇总」拆句后仍是 1 子句，5 字段全保留。
2. 多字段匹配：该消息被识别为 add_chart，且提取出 5 张图（metric_field 均为真实字段名）。
3. 复合指令回归：「删掉A图，新增B图」仍拆成 2 个动作（delete_chart + add_chart），不被 Layer1 误合并。
"""
import pytest

from app.core.action_planner import split_clauses, plan_actions
from app.core.intent_classifier import IntentClassifier


FIELD_PROFILES = [
    {"name": "业务流程合规率", "type": "number"},
    {"name": "抵押登记合规率", "type": "number"},
    {"name": "档案管理合规率", "type": "number"},
    {"name": "制度执行到位率", "type": "number"},
    {"name": "内部审计问题整改率", "type": "number"},
    {"name": "地区", "type": "string"},
    {"name": "月份", "type": "string"},
]
CONTEXT = {"dataset_info": {"field_profiles": FIELD_PROFILES}}

MSG5 = ("我想要顶部的汇总看板加上每个：业务流程合规率，抵押登记合规率，"
        "档案管理合规率，制度执行到位率，内部审计问题整改率的平均值汇总")
MSG_DELADD = "删掉转化率那张图，新增一张地区分布柱状图"


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch):
    # 规则兜底路径验证：跳过 LLM 提取（避免真实联网/超时），强制走 _rule_extract_add_charts
    monkeypatch.setattr(
        IntentClassifier, "_llm_extract_add_charts",
        classmethod(lambda cls, message, field_profiles: None),
    )


def test_layer1_no_truncation():
    clauses = split_clauses(MSG5)
    assert len(clauses) == 1, f"5字段消息应合并为1子句，实际: {clauses}"
    assert "业务流程合规率" in clauses[0]
    assert "内部审计问题整改率" in clauses[0]


def test_multifield_extraction():
    plan = plan_actions(MSG5, CONTEXT)
    assert plan["actions"], "应至少产出1个动作"
    act = plan["actions"][0]
    assert act["type"] == "add_chart", f"应识别为 add_chart，实际: {act['type']}"
    charts = act["params"].get("charts") or []
    assert len(charts) == 5, f"应提取5张图，实际: {charts}"
    metrics = {c["metric_field"] for c in charts}
    assert metrics == {
        "业务流程合规率", "抵押登记合规率", "档案管理合规率",
        "制度执行到位率", "内部审计问题整改率",
    }, f"metric_field 应为5个真实字段，实际: {metrics}"


def test_compound_delete_add_regression():
    # 复合指令回归：删A + 新增B 必须拆成2个动作，不被 Layer1 误合并
    clauses = split_clauses(MSG_DELADD)
    assert len(clauses) == 2, f"复合指令应拆2子句，实际: {clauses}"
    plan = plan_actions(MSG_DELADD, CONTEXT)
    types = {a["type"] for a in plan["actions"]}
    assert types == {"delete_chart", "add_chart"}, f"应含删图+加图，实际: {types}"
    assert plan["is_compound"] is True
