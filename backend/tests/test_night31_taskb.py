"""
night31 Task B · 9 项「无对话用例」意图的最小可执行离线用例

覆盖 `docs/project_record/34项功能完成度矩阵.md` 中标记为 ❌ 无用例的 9 项：
  #6  ATTRIBUTION      归因追问
  #9  QUALITY_FIX       数据质量修复
  #10 CHART_FIX         图表诊断修复
  #14 CREATE_CONFIG     新建配置
  #15 UPDATE_CONFIG     修改配置
  #16 DELETE_CONFIG     删除配置
  #17 BULK_UPDATE_DATA  批量更新
  #19 QUERY_METRIC      指标查询
  #20 RECALC_METRIC     下游重算触发

运行方式（离线、不依赖真 LLM）：
    cd backend && python tests/test_night31_taskb.py
或：pytest tests/test_night31_taskb.py

设计说明：
- 意图分类走规则路径（INTENT_PATTERNS + _extract_params），仅在「无任何规则命中」时
  才回退 LLM。本用例全部消息均确定性命中规则，context={} 无 field_profiles，
  **绝不触发 LLM 网络调用**，沙箱可离线真跑。
- 断言为「运行时断言」（非关键词 grep）：既断言 intent_type，也对关键 extracted_params
  做结构断言（如批量更新必须标 isolated=True、配置 CRUD 必须抽到 key、指标查询必须解析出 metric）。
- 命名 `test_*.py` 而非 `_verify_*.py`：仓库 `.gitignore` 全局忽略 `_*.py`（含 _verify_*.py），
  本文件需随 Task B 提交，故选用不被忽略的 `test_*.py`。
"""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.intent_classifier import classify_intent  # noqa: E402


def _clf(msg, ctx=None):
    return classify_intent(msg, ctx or {})


# 每条意图：候选消息 + 期望 intent_type + 可选参数断言（callable 接收 analysis["extracted_params"]）
CASES = [
    ("ATTRIBUTION", [
        ("为什么坏账率上升了", None),
        ("分析一下下降的原因",
         lambda ep: ep.get("analysis_type") == "attribution" and ep.get("requires_lineage") is True),
    ]),
    ("QUALITY_FIX", [
        ("帮我把数据里的重复值去重",
         lambda ep: ep.get("issue_type") == "duplicate" and ep.get("fix_strategy") == "keep_first"),
        ("清洗缺失的空值",
         lambda ep: ep.get("issue_type") == "null"),
    ]),
    ("CHART_FIX", [
        ("这张图是空的", None),
        ("《销售趋势》这张图是空的",
         lambda ep: ep.get("chart_title") == "销售趋势"),
    ]),
    ("CREATE_CONFIG", [
        ("新建一个风控规则", None),
        ("创建配置项 timeout",
         lambda ep: ep.get("key") == "timeout"),
    ]),
    ("UPDATE_CONFIG", [
        ("修改配置 timeout",
         lambda ep: ep.get("key") == "timeout"),
        ("更新规则阈值", None),
    ]),
    ("DELETE_CONFIG", [
        ("删除这个配置", None),
        ("删掉风控规则 y",
         lambda ep: ep.get("key") == "y"),
    ]),
    ("BULK_UPDATE_DATA", [
        ("批量更新客户数据",
         lambda ep: ep.get("isolated") is True),  # 红线④：默认走隔离临时库
        ("成批修改数据", None),
    ]),
    ("QUERY_METRIC", [
        ("毛利率是多少",
         lambda ep: bool(ep.get("metric"))),
        ("解释一下净资产收益率",
         lambda ep: ep.get("operation") == "explain"),
    ]),
    ("RECALC_METRIC", [
        ("重新计算下游指标",
         lambda ep: ep.get("operation") == "trigger"),
        ("重算进度怎么样了",
         lambda ep: ep.get("operation") == "status"),
    ]),
]


def test_all_nine_intents_classified_offline():
    """9 意图 × 2 样本 = 18 条，意图识别 + 参数结构全断言（离线、零 LLM）。"""
    total = 0
    for intent, samples in CASES:
        for msg, param_assert in samples:
            total += 1
            r = _clf(msg)
            it = r["intent_type"]
            assert it == intent.lower(), (
                f"[{intent}] 消息「{msg}」分类为 {it!r}，期望 {intent.lower()!r}（疑似规则顺序/优先级漂移）")
            if param_assert is not None:
                assert param_assert(r["analysis"].get("extracted_params") or {}), (
                    f"[{intent}] 消息「{msg}」参数断言失败: {r['analysis'].get('extracted_params')}")
    assert total == 18, f"用例数应为 18，实际 {total}"


def test_precedence_query_metric_beats_attribution():
    """「解释毛利率的变化」必须命中 QUERY_METRIC，而非被 ATTRIBUTION 抢走（矩阵 #19 优先级）。"""
    r = _clf("解释毛利率的变化")
    assert r["intent_type"] == "query_metric"


def test_precedence_recalc_beats_query():
    """「下游指标一致性对不对」必须命中 RECALC_METRIC，而非被 QUERY_METRIC 抢走（矩阵 #20 优先级）。"""
    r = _clf("下游指标一致性对不对")
    assert r["intent_type"] == "recalc_metric"


def test_precedence_create_config_over_add_chart():
    """「新建一个风控规则」必须命中 CREATE_CONFIG 而非 ADD_CHART（CRUD 意图排最前）。"""
    r = _clf("新建一个风控规则")
    assert r["intent_type"] == "create_config"


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
    print(f"\n==== night31 Task B 离线用例: {passed} passed, {failed} failed ====")
    sys.exit(1 if failed else 0)
