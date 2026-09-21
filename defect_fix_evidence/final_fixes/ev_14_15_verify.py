"""1.4 / 1.5 实测脚本（离线、不依赖真实 LLM）。

覆盖：
- 1.4：模拟 buggy LLM（把 5 字段合并成 1 张），验证 _extract_add_charts 现在返回 5 张（规则优先）。
- 1.4：用原截图那句话 MSG5 走 plan_actions，验证识别 5 字段全保留。
- 1.5：charts_spec 含「无真实字段的垃圾 spec（bar, 空字段）」时，执行器跳过而非臆造「新增bar」。
- 1.5：混合 4 真实 + 1 垃圾 → 建 4，跳过 1。
"""
import os, sys, types
sys.path.insert(0, r"C:/Users/Asus009/Desktop/临时/ai大赛/AI-Report/backend")

from app.core.intent_classifier import IntentClassifier
from app.core.action_planner import plan_actions, split_clauses
from app.core import action_executor

FIELD_PROFILES = [
    {"name": "业务流程合规率", "type": "number"},
    {"name": "抵押登记合规率", "type": "number"},
    {"name": "档案管理合规率", "type": "number"},
    {"name": "制度执行到位率", "type": "number"},
    {"name": "内部审计问题整改率", "type": "number"},
    {"name": "地区", "type": "string"},
    {"name": "月份", "type": "string"},
]
CONTEXT = {"dataset_info": {"field_profiles": FIELD_PROFILES}, "dataset_id": "ds_x"}

MSG5 = ("我想要顶部的汇总看板加上每个：业务流程合规率，抵押登记合规率，"
        "档案管理合规率，制度执行到位率，内部审计问题整改率的平均值汇总")

ok = True
def check(name, cond, detail=""):
    global ok
    print(("PASS " if cond else "FAIL ") + name + ((" | " + detail) if detail else ""))
    if not cond: ok = False

# ---- 1.4：模拟 buggy LLM 返回 1 张合并图 ----
def fake_llm_merged(cls, message, field_profiles):
    # 模拟 LLM 把「A,B,C,D,E 平均值」合并成 1 张汇总图
    return [{"title": "合规率平均值汇总", "chart_type": "kpi",
             "dimension_field": "", "metric_field": "业务流程合规率"}]

IntentClassifier._llm_extract_add_charts = classmethod(fake_llm_merged)
charts = IntentClassifier._extract_add_charts(MSG5, FIELD_PROFILES)
check("1.4 规则优先覆盖 buggy LLM（5字段→5图）", len(charts) == 5,
      f"实际 {len(charts)} 张: {[c['metric_field'] for c in charts]}")
metrics = {c["metric_field"] for c in charts}
check("1.4 5 个 metric_field 均为真实字段", metrics == {
    "业务流程合规率", "抵押登记合规率", "档案管理合规率",
    "制度执行到位率", "内部审计问题整改率"}, str(metrics))

# ---- 1.4：原截图那句话走 plan_actions ----
plan = plan_actions(MSG5, CONTEXT)
check("1.4 plan_actions 产出 add_chart 动作", plan["actions"] and plan["actions"][0]["type"] == "add_chart")
plan_charts = plan["actions"][0]["params"].get("charts") or []
check("1.4 plan_actions 识别 5 张图", len(plan_charts) == 5, f"实际 {len(plan_charts)} 张")

# ---- 1.5：垃圾 spec（bar, 空字段）被跳过 ----
garbage_spec = [{"title": "", "chart_type": "bar", "dimension_field": "", "metric_field": ""}]
cfg = {"charts": []}
res = action_executor.ActionExecutor._execute_add_chart(
    {"charts": garbage_spec}, cfg, CONTEXT)
check("1.5 全垃圾 spec 不产生图表", len(res.get("render_updates", [])) == 0,
      f"render_updates={len(res.get('render_updates', []))}")

# ---- 1.5：混合 4 真实 + 1 垃圾 → 建 4 跳 1 ----
mixed = [
    {"title": "业务流程合规率", "chart_type": "kpi", "dimension_field": "", "metric_field": "业务流程合规率"},
    {"title": "抵押登记合规率", "chart_type": "kpi", "dimension_field": "", "metric_field": "抵押登记合规率"},
    {"title": "档案管理合规率", "chart_type": "kpi", "dimension_field": "", "metric_field": "档案管理合规率"},
    {"title": "制度执行到位率", "chart_type": "kpi", "dimension_field": "", "metric_field": "制度执行到位率"},
    {"title": "", "chart_type": "bar", "dimension_field": "", "metric_field": ""},  # 垃圾
]
cfg2 = {"charts": []}
res2 = action_executor.ActionExecutor._execute_add_chart(
    {"charts": mixed}, cfg2, CONTEXT)
added = len(res2.get("render_updates", []))
msg = res2.get("message", "")
check("1.5 混合 4真实+1垃圾 → 建4跳1", added == 4, f"实际建 {added} 张")
check("1.5 message 提示已跳过 1 个", "已跳过" in msg, msg)

# ---- 1.5：metric 无法解析（真垃圾）即跳过，不臆造 ----
# title 非空但 metric 为空且无真实字段可匹配 → 跳过（旧逻辑会用首个指标臆造「新增bar」）
no_metric = [{"title": "随便起的名字", "chart_type": "bar", "dimension_field": "", "metric_field": ""}]
cfg3 = {"charts": []}
res3 = action_executor.ActionExecutor._execute_add_chart({"charts": no_metric}, cfg3, CONTEXT)
check("1.5 metric 为空→跳过不臆造", len(res3.get("render_updates", [])) == 0,
      f"render_updates={len(res3.get('render_updates', []))}")

print("\nRESULT:", "ALL PASS" if ok else "HAS FAILURE")
sys.exit(0 if ok else 1)
