"""3.5 实查版归因 — 单元测试（6 用例）
验证 _execute_attribution 不再返回"请先刷新看板页面"，而是给出基于真实字段画像的结论。
"""
import sys, os, json
# 本文件在 <repo>/defect_fix_evidence/final_fixes/ → 上两级到 repo 根，再进 backend
_REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, os.path.join(_REPO, 'backend'))
print("[path] backend =", os.path.join(_REPO, 'backend'))

from app.core.action_executor import ActionExecutor  # noqa: E402

BASE_FIELDS = [
    {"name": "贷款金额", "type": "number", "null_count": 0, "null_rate": 0.0},
    {"name": "地区", "type": "string", "null_count": 2, "null_rate": 0.02},
    {"name": "担保类型", "type": "string", "null_count": 0, "null_rate": 0.0},
]


def run(name, params, config, context):
    r = ActionExecutor._execute_attribution(params, config, context)
    msg = r.get("message", "")
    print("=" * 78)
    print("[%s]" % name)
    print("  message:", msg.replace("\n", "\n           "))
    print("  check_result:", json.dumps(r.get("check_result", {}), ensure_ascii=False))
    has_refresh_blanket = "请先刷新看板页面" in msg
    print("  含'请先刷新看板页面'(旧话术):", has_refresh_blanket)
    return r, msg, has_refresh_blanket


fails = 0

# 用例1：字段不在数据集 → 应报 missing 并列出真实字段
cfg = {"charts": [{"chart_type": "bar", "title": "抵押率分布", "x_field": "地区", "y_field": "抵押率"}]}
ctx = {"dataset_info": {"field_profiles": BASE_FIELDS}}
r, m, bad = run("用例1 字段缺失(y_field=抵押率 不存在)", {"target": "抵押率"}, cfg, ctx)
assert r["check_result"]["fields"]["抵押率"] == "missing", "用例1 应判定 missing"
assert r["check_result"]["fields"]["地区"] == "ok"
if bad: fails += 1
print("  -> PASS")

# 用例2：字段存在但被清洗置空（null_rate=1.0）→ 应报 emptied
fields2 = BASE_FIELDS + [{"name": "抵押率", "type": "number", "null_count": 1020, "null_rate": 1.0}]
cfg = {"charts": [{"chart_type": "bar", "title": "抵押率分布", "x_field": "地区", "y_field": "抵押率"}]}
r, m, bad = run("用例2 清洗置空(null_rate=1.0)", {"target": "抵押率"}, cfg, {"dataset_info": {"field_profiles": fields2}})
assert r["check_result"]["fields"]["抵押率"] == "emptied", "用例2 应判定 emptied"
if bad: fails += 1
print("  -> PASS")

# 用例3：高缺失率（0.8）→ 应报 high_null
fields3 = BASE_FIELDS + [{"name": "抵押率", "type": "number", "null_count": 800, "null_rate": 0.8}]
cfg = {"charts": [{"chart_type": "bar", "title": "抵押率分布", "x_field": "地区", "y_field": "抵押率"}]}
r, m, bad = run("用例3 高缺失率(0.8)", {"target": "抵押率"}, cfg, {"dataset_info": {"field_profiles": fields3}})
assert r["check_result"]["fields"]["抵押率"] == "high_null", "用例3 应判定 high_null"
if bad: fails += 1
print("  -> PASS")

# 用例4：字段都正常 → 应报 ok，并建议重新生成（而非让刷新）
fields4 = BASE_FIELDS + [{"name": "抵押率", "type": "number", "null_count": 0, "null_rate": 0.0}]
cfg = {"charts": [{"chart_type": "bar", "title": "抵押率分布", "x_field": "地区", "y_field": "抵押率"}]}
r, m, bad = run("用例4 字段均正常", {"target": "抵押率"}, cfg, {"dataset_info": {"field_profiles": fields4}})
assert r["check_result"]["fields"]["抵押率"] == "ok", "用例4 应判定 ok"
if bad: fails += 1
print("  -> PASS")

# 用例5：扁平 context（会话链路 chat.py:359 的写法）也要能取到
cfg = {"charts": [{"chart_type": "bar", "title": "抵押率分布", "x_field": "地区", "y_field": "抵押率"}]}
r, m, bad = run("用例5 扁平 context(field_profiles 顶层)", {"target": "抵押率"}, cfg, {"field_profiles": BASE_FIELDS})
assert r["check_result"]["checkable"] is True, "用例5 扁平 context 应可实查"
if bad: fails += 1
print("  -> PASS")

# 用例6：无字段画像 → 应诚实说"无法实查"并说明原因，而不是让刷新
cfg = {"charts": [{"chart_type": "bar", "title": "抵押率分布", "x_field": "地区", "y_field": "抵押率"}]}
r, m, bad = run("用例6 无字段画像(不可实查)", {"target": "抵押率"}, cfg, {})
assert r["check_result"]["checkable"] is False, "用例6 应标记不可实查"
assert "无法在这里实查" in m, "用例6 应说明无法实查"
if bad: fails += 1
print("  -> PASS")

print("=" * 78)
print("仍出现旧话术'请先刷新看板页面'的用例数 =", fails)
print("RESULT:", "ALL PASS" if fails == 0 else "FAIL")
