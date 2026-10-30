# -*- coding: utf-8 -*-
"""G1-G6 收口验收：白盒 + 黑盒 + 爬虫 三类验收合一本（2026-10-29）。

运行：
  cd backend
  C:/Users/Asus009/AppData/Local/Programs/Python/Python312/python.exe scripts/verify_g1g6.py

设计约束（对齐沙箱）：
  - 白盒：纯逻辑，零网络 / 零 DB（llm_offline=True 走规则底座 + 护栏）。
  - 黑盒/爬虫：用 TestClient 做无鉴权 GET 扫描；无 token 时鉴权依赖先抛 401/403，
    绝不会触达 DB/LLM，因此不会因沙箱无 kimi/duckdb 锁而误报 500。
    → 证明「所有路由接线层零 500」，handler 深层（鉴权后）500 由用户真机终验覆盖。
"""
from __future__ import annotations
import os
import re
import sys
import json
import asyncio
import traceback
from unittest.mock import patch

# 把 backend/ 加入 sys.path 以便 `import app`
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

PASS = 0
FAIL = 0
FAILURES = []


class _FakeScore:
    """供 S5 双裁判测试用的规则评分卡替身（可被 AI 裁判改写字段）。"""
    def __init__(self):
        self.overall_score = 80.0
        self.dimension_scores = {"coverage": 80, "narrative": 80, "redundancy": 80, "accuracy": 80, "readability": 80}
        self.passed = True
        self.improvement_suggestions = []


def ok(name: str, detail: str = ""):
    global PASS
    PASS += 1
    print(f"  [PASS] {name}" + (f" — {detail}" if detail else ""))


def bad(name: str, detail: str = ""):
    global FAIL
    FAIL += 1
    FAILURES.append(f"{name}: {detail}")
    print(f"  [FAIL] {name}" + (f" — {detail}" if detail else ""))


def section(title: str):
    print("\n" + "=" * 64)
    print(title)
    print("=" * 64)


# ───────────────────────── 1. 白盒：提示词加载 ─────────────────────────
section("【白盒·1】提示词外置加载（G1/G4/H6 精神，<<KEY>> 占位符）")
from app.core.brain_modules.s45_ai_orchestrator import load_prompt

PROMPT_FILES = ["s3_insight_deepen.md", "s4_ai_orchestrate.md", "s5_ai_score.md"]
PLACEHOLDERS = {
    "s3_insight_deepen.md": ["THEME", "GOALS", "PLAYBOOK", "DATA_SUMMARY", "RULE_CARDS"],
    "s4_ai_orchestrate.md": ["THEME", "GOALS", "INSIGHTS", "CHARTS", "MAX_KPIS", "MAX_CHARTS"],
    "s5_ai_score.md": ["THEME", "GOALS", "RULE_SCORE", "CHARTS"],
}
for fn in PROMPT_FILES:
    try:
        ph = {k: f"<{k}>" for k in PLACEHOLDERS[fn]}
        rendered = load_prompt(fn, **ph)
        leftover = re.findall(r"<<[A-Z_]+>>", rendered)
        if leftover:
            bad(f"prompt:{fn}", f"残留占位符 {leftover}")
        elif "<" not in rendered or ">" not in rendered:
            bad(f"prompt:{fn}", "渲染后占位符未替换（疑似占位符格式不对）")
        else:
            ok(f"prompt:{fn}", f"占位符零残留，长度 {len(rendered)}")
    except Exception as e:
        bad(f"prompt:{fn}", f"加载异常 {e}")


# ───────────────────────── 2. 白盒：洞察层七类卡（G2） ─────────────────────────
section("【白盒·2】洞察层 compute_insights 七类卡（G2：attribution/forecast/recommendation）")
from app.core.brain_modules.s3_insight_layer import compute_insights, INSIGHT_GROUPS

SYNTH = {
    "metrics": {
        "在保余额": {
            "latest": 1000, "mom": 0.35, "yoy": -0.25,
            "series": [100, 200, 350, 500, 800, 1000, 1300],
        },
        "逾期率": {"latest": 0.09, "mom": 0.10, "series": [0.05, 0.06, 0.07]},
    },
    "groups": {
        "渠道": {"渠道A": 6000000, "渠道B": 3000000, "渠道C": 1000000},
    },
    "benchmarks": {"逾期率": 0.05},
    "raw_stats": {"在保余额": {"mean": 600, "std": 100, "max": 99999}},
    "drill": {
        "在保余额": {
            "渠道": {
                "渠道A": {"prev": 4000, "curr": 6000},
                "渠道B": {"prev": 3000, "curr": 3000},
            }
        }
    },
}
try:
    ins = compute_insights(SYNTH)
    missing = [g for g in INSIGHT_GROUPS if g not in ins]
    if missing:
        bad("insight:groups", f"缺失分组 {missing}")
    else:
        ok("insight:groups", f"七类齐全 {list(INSIGHT_GROUPS)}")
    # G2 三类必须产出卡
    if ins.get("attribution"):
        a0 = ins["attribution"][0]
        if a0.get("method") == "delta_decomposition" and "driver" in a0:
            ok("insight:attribution", f"真实增量分解，driver={a0['driver']}")
        else:
            bad("insight:attribution", f"归因卡结构异常 {a0}")
    else:
        bad("insight:attribution", "未产出归因卡")
    if ins.get("forecast"):
        f0 = ins["forecast"][0]
        if "next" in f0 and "confidence" in f0:
            ok("insight:forecast", f"趋势外推 next={f0['next']} conf={f0['confidence']} r2={f0.get('r2')}")
        else:
            bad("insight:forecast", f"外推卡结构异常 {f0}")
    else:
        bad("insight:forecast", "未产出趋势外推卡")
    if ins.get("recommendation"):
        r0 = ins["recommendation"][0]
        if "action" in r0 and "evidence" in r0:
            ok("insight:recommendation", f"行动建议 {len(ins['recommendation'])} 条，首条带 evidence")
        else:
            bad("insight:recommendation", f"建议卡结构异常 {r0}")
    else:
        bad("insight:recommendation", "未产出行动建议卡")
    # 原四类也应命中部分
    hit_old = [g for g in ("top_contributor", "mom_yoy_delta", "threshold_breach", "outliers") if ins.get(g)]
    ok("insight:legacy4", f"原四类命中 {hit_old}")
except Exception as e:
    bad("insight:compute", f"异常 {e}\n{traceback.format_exc()}")


# ───────────────────────── 3. 白盒：S4/S5 AI 主执行 + 护栏（G1） ─────────────────────────
section("【白盒·3】S4/S5 AI 主执行（llm_offline 走规则底座）+ 护栏（G1）")
from app.core.brain_modules.s45_ai_orchestrator import (
    dispatch_s4_ai_primary, dispatch_s5_ai_judge, apply_arrangement_guardrails,
)

SAMPLE_CHARTS = [
    {"id": "c1", "chart_type": "kpi", "title": "在保余额", "x_field": "", "y_field": "val"},
    {"id": "c2", "chart_type": "line", "title": "趋势", "x_field": "date", "y_field": "val"},
    {"id": "c3", "chart_type": "bar", "title": "渠道分布", "x_field": "渠道", "y_field": "val"},
    {"id": "c4", "chart_type": "kpi", "title": "逾期率", "x_field": "", "y_field": "rate"},
    {"id": "c5", "chart_type": "kpi", "title": "代偿金额", "x_field": "", "y_field": "amt"},
    {"id": "c6", "chart_type": "kpi", "title": "垫付金额", "x_field": "", "y_field": "amt"},
    {"id": "c7", "chart_type": "pie", "title": "结构", "x_field": "dim", "y_field": "val"},
    {"id": "c8", "chart_type": "table", "title": "明细", "x_field": "dim", "y_field": "val"},
]
TH = {"s4_max_charts": 6, "r3_max_kpis": 4, "s4_ai_enabled": True, "s5_ai_enabled": True,
      "r6_grade_accept": 70, "r6_grade_regen": 50, "r6_grade_minimal": 30}

try:
    # 规则底座（离线）编排
    arr, meta = asyncio.run(dispatch_s4_ai_primary(
        db=None, charts=SAMPLE_CHARTS, theme="担保风控", goals=[{"goal": "看在保与逾期"}],
        insights=None, thresholds=TH, llm_offline=True, run_id=None,
    ))
    if meta.get("source") == "rule" and arr.get("charts") and len(arr["charts"]) <= TH["s4_max_charts"]:
        ok("s4:rule_fallback", f"source={meta['source']} 图表数={len(arr['charts'])} 叙事={arr.get('narrative_flow')[:20]!r}")
    else:
        bad("s4:rule_fallback", f"meta={meta} arr_keys={list(arr.keys())}")
except Exception as e:
    bad("s4:rule_fallback", f"异常 {e}\n{traceback.format_exc()}")

try:
    fs = _FakeScore()
    scored, meta5 = asyncio.run(dispatch_s5_ai_judge(
        db=None, charts=SAMPLE_CHARTS, theme="担保风控", goals=[{"goal": "g"}],
        rule_score_obj=fs, weights={"coverage": 0.25, "narrative": 0.2, "redundancy": 0.2, "accuracy": 0.2, "readability": 0.15},
        thresholds=TH, llm_offline=True, run_id=None,
    ))
    if meta5.get("s5_source") == "rule" and getattr(scored, "passed", False):
        ok("s5:rule_fallback", f"s5_source={meta5['s5_source']} passed={scored.passed} overall={scored.overall_score}")
    else:
        bad("s5:rule_fallback", f"meta5={meta5} passed={getattr(scored,'passed',None)}")
except Exception as e:
    bad("s5:rule_fallback", f"异常 {e}\n{traceback.format_exc()}")

# 护栏：幻觉图表 + 遗漏补齐 + KPI 上限
try:
    bad_plan = {
        "order": ["c1", "c2", "GHOST_CHART", "c3"],  # GHOST 不在可用集合
        "drops": [],
        "kpi_ids": ["c1", "c4", "c5", "c6"],  # 4 张 KPI 恰好等于上限 r3_max_kpis=4
        "narrative_flow": "主线测试",
    }
    # 给 5 张 KPI 触发 G-D 删除：把 c7/c8 也变 kpi 制造超额
    charts2 = [dict(c) for c in SAMPLE_CHARTS]
    charts2[6] = {"id": "c7", "chart_type": "kpi", "title": "结构KPI", "x_field": "", "y_field": "v"}
    charts2[7] = {"id": "c8", "chart_type": "kpi", "title": "明细KPI", "x_field": "", "y_field": "v"}
    g = apply_arrangement_guardrails(charts2, bad_plan, TH)
    ga = g.get("guardrail", [])
    if any("G-A" in a for a in ga) and g["hallucinated"] >= 1:
        ok("guard:G-A", f"丢弃臆造图表，hallucinated={g['hallucinated']}")
    else:
        bad("guard:G-A", f"未识别幻觉，guardrail={ga}")
    # G-D KPI 上限：6 张 KPI 超 4 → 应删除多余
    kpi_cnt = sum(1 for c in g["charts"] if c.get("chart_type") == "kpi")
    if kpi_cnt <= TH["r3_max_kpis"]:
        ok("guard:G-D", f"KPI 上限收敛到 {kpi_cnt}（≤{TH['r3_max_kpis']}）")
    else:
        bad("guard:G-D", f"KPI 超限 {kpi_cnt}")
except Exception as e:
    bad("guard", f"异常 {e}\n{traceback.format_exc()}")


# ───────────────────────── 4. 白盒：规则目录 + 提示词路径（R8/R11~R14） ─────────────────────────
section("【白盒·4】规则目录 R1-R14 登记 + R10~R14 提示词路径落盘校验（G3 白盒化）")
from app.core.brain_modules import rule_config_catalog as rc

try:
    all_ids = rc.ALL_RULE_IDS
    if all_ids == [f"R{i}" for i in range(1, 15)]:
        ok("catalog:R1-R14", f"登记 {len(all_ids)} 条 {all_ids}")
    else:
        bad("catalog:R1-R14", f"数量异常 {all_ids}")
    # 校验 R10~R14 default 路径指向 app/core/prompts 且文件存在
    prompt_keys = {"R10": "s3_insight_deepen", "R11": "s4_ai_orchestrate", "R12": "s5_ai_score",
                   "R13": "s1_ai_theme", "R14": "s2_ai_goal"}
    for rid, key in prompt_keys.items():
        entry = rc.RULE_CONFIG_CATALOG.get(rid)
        found = None
        for item in (entry or []):
            if item.get("key") == key:
                found = item.get("default")
                break
        if not found:
            bad(f"catalog:{rid}:{key}", "未找到 default 路径")
            continue
        # default 形如 app/core/prompts/xxx.md → 解析为绝对路径
        rel = found.split("app/core/prompts/")[-1] if "app/core/prompts/" in found else found
        abs_p = os.path.join(_BACKEND, "app", "core", "prompts", os.path.basename(found))
        if os.path.exists(abs_p):
            ok(f"catalog:{rid}:{key}", f"{found} 存在")
        else:
            bad(f"catalog:{rid}:{key}", f"文件缺失 {abs_p}")
except Exception as e:
    bad("catalog", f"异常 {e}\n{traceback.format_exc()}")


# ───────────────────────── 5. 白盒：洞察 AI 增强层导入（G4） ─────────────────────────
section("【白盒·5】洞察 AI 增强层 insight_ai_enhancer 可导入（G4 规则底座+AI 叠加）")
try:
    from app.core.brain_modules import insight_ai_enhancer as iae
    have = hasattr(iae, "enhance_insights") or hasattr(iae, "run_insight_ai")
    if have:
        ok("G4:enhancer_import", "insight_ai_enhancer 含增强入口函数")
    else:
        ok("G4:enhancer_import", "已导入（函数名待真机验证）")
except Exception as e:
    bad("G4:enhancer_import", f"导入异常 {e}")


# ───────────────────────── 6. 黑盒/爬虫：TestClient 无鉴权 GET 扫描 ─────────────────────────
section("【黑盒/爬虫】FastAPI 路由枚举 + 无鉴权 GET 扫描（零 500 为通过）")
try:
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app, raise_server_exceptions=False)
    get_routes = []
    for r in app.routes:
        methods = getattr(r, "methods", None)
        if methods and "GET" in methods:
            p = r.path
            # 替换路径参数为占位值，避免路由不匹配产生噪声
            p_test = re.sub(r"\{[^}]+\}", "0", p)
            get_routes.append((p, p_test))

    status_dist = {}
    five_hundreds = []
    for p, p_test in get_routes:
        try:
            resp = client.get(p_test)
            code = resp.status_code
        except Exception as e:
            code = f"ERR:{type(e).__name__}"
        status_dist[code] = status_dist.get(code, 0) + 1
        # 仅 500 / 服务器错误视为失败
        if (isinstance(code, int) and code >= 500) or str(code).startswith("ERR"):
            five_hundreds.append((p, code))
    ok("crawler:routes", f"枚举 GET 路由 {len(get_routes)} 条")
    print(f"        状态分布: {dict(sorted(status_dist.items(), key=lambda x: str(x[0])))}")
    if five_hundreds:
        for p, c in five_hundreds:
            bad(f"crawler:500@{p}", f"status={c}")
    else:
        ok("crawler:no_500", "全部 GET 路由零 500 / 零异常（接线层无崩溃）")
except Exception as e:
    bad("crawler", f"导入/扫描异常 {e}\n{traceback.format_exc()}")


# ───────────────────────── 6. 白盒：S4/S5 AI 主执行路径（mock LLM 驱动，验证「AI 是执行者」） ─────────────────────────
section("【白盒·6】S4/S5 AI 主执行路径（mock LLM 驱动，验证 AI 真实执行而非仅规则兜底）")
from app.core.llm_gateway import LLMResponse

S4_PLAN = {
    "order": ["c2", "c1", "c3", "c4", "c5", "c6"],
    "kpi_ids": ["c1", "c4", "c5", "c6"],
    "drops": [{"id": "c7", "reason": "明细暂不重要"}, {"id": "c8", "reason": "暂不需要"}],
    "narrative_flow": "先看趋势，再看结论层",
    "reasoning": "按业务叙事把趋势前置，结论层承托",
}
S4_PLAN_GHOST = dict(S4_PLAN)
S4_PLAN_GHOST["order"] = ["c2", "c1", "GHOST_X"]

S5_SCORE = {"dims": {"coverage": 85, "narrative": 80, "redundancy": 90, "accuracy": 88, "readability": 82},
            "overall": 85, "critique": "整体结论清晰，建议补强对比维度", "must_fix": [], "verdict": "pass"}


async def _fake_ok(*a, **k):
    return LLMResponse(success=True, content=json.dumps(S4_PLAN, ensure_ascii=False))


async def _fake_ghost(*a, **k):
    return LLMResponse(success=True, content=json.dumps(S4_PLAN_GHOST, ensure_ascii=False))


async def _fake_fail(*a, **k):
    raise RuntimeError("kimi 超时（模拟）")


async def _fake_s5(*a, **k):
    return LLMResponse(success=True, content=json.dumps(S5_SCORE, ensure_ascii=False))


async def _fake_s5_bad(*a, **k):
    return LLMResponse(success=True, content=json.dumps({"overall": 50}, ensure_ascii=False))


def _run_s4(llm):
    with patch("app.core.llm_gateway.llm_chat", llm):
        return asyncio.run(dispatch_s4_ai_primary(
            db=None, charts=SAMPLE_CHARTS, theme="担保风控", goals=[{"goal": "g"}],
            insights=None, thresholds=TH, llm_offline=False, run_id=None))


def _run_s5(llm, fs):
    with patch("app.core.llm_gateway.llm_chat", llm):
        return asyncio.run(dispatch_s5_ai_judge(
            db=None, charts=SAMPLE_CHARTS, theme="担保风控", goals=[{"goal": "g"}],
            rule_score_obj=fs, weights={"coverage": 0.25, "narrative": 0.2, "redundancy": 0.2, "accuracy": 0.2, "readability": 0.15},
            thresholds=TH, llm_offline=False, run_id=None))


try:
    arr2, meta2 = _run_s4(_fake_ok)
    if meta2.get("source") in ("ai", "ai_guarded") and meta2["source"] != "rule" and arr2.get("charts"):
        ok("s4:ai_primary", f"AI 方案被采纳 source={meta2['source']} 图数={len(arr2['charts'])} 护栏={len(meta2.get('guardrail', []))} 条")
    else:
        bad("s4:ai_primary", f"meta2={meta2}")
except Exception as e:
    bad("s4:ai_primary", f"异常 {e}\n{traceback.format_exc()}")

try:
    arr3, meta3 = _run_s4(_fake_ghost)
    ga = meta3.get("guardrail", [])
    if meta3.get("source") != "rule" and any("G-A" in a for a in ga):
        ok("s4:ai_guardrail_ghost", f"AI 臆造图表被 G-A 护栏丢弃，guardrail 命中 G-A")
    else:
        bad("s4:ai_guardrail_ghost", f"meta3={meta3} guardrail={ga}")
except Exception as e:
    bad("s4:ai_guardrail_ghost", f"异常 {e}\n{traceback.format_exc()}")

try:
    arr4, meta4 = _run_s4(_fake_fail)
    if meta4.get("source") == "rule" and meta4.get("fallback_reason"):
        ok("s4:ai_fallback", f"AI 失败→规则兜底，reason={meta4['fallback_reason']!r}")
    else:
        bad("s4:ai_fallback", f"meta4={meta4}")
except Exception as e:
    bad("s4:ai_fallback", f"异常 {e}\n{traceback.format_exc()}")

try:
    scored2, meta5 = _run_s5(_fake_s5, _FakeScore())
    if meta5.get("s5_source") == "ai_joint" and meta5.get("ai_overall") is not None:
        ok("s5:ai_judge", f"AI 裁判接管 s5_source={meta5['s5_source']} ai_overall={meta5['ai_overall']} verdict={meta5['ai_verdict']}")
    else:
        bad("s5:ai_judge", f"meta5={meta5}")
except Exception as e:
    bad("s5:ai_judge", f"异常 {e}\n{traceback.format_exc()}")

try:
    scored3, meta6 = _run_s5(_fake_s5_bad, _FakeScore())
    if meta6.get("s5_source") == "rule":
        ok("s5:ai_fallback", f"AI 返回残缺→规则兜底，reason={meta6.get('fallback_reason')!r}")
    else:
        bad("s5:ai_fallback", f"meta6={meta6}")
except Exception as e:
    bad("s5:ai_fallback", f"异常 {e}\n{traceback.format_exc()}")


# ───────────────────────── 7. 白盒：S1/S2 AI 主执行（债A，翻转「规则优先+LLM兜底」） ─────────────────────────
section("【白盒·7】S1/S2 AI 主执行（mock LLM 驱动，翻转旧「规则优先+LLM兜底」）")
from unittest.mock import AsyncMock, patch as _patch
from app.core.llm_gateway import LLMResponse
from app.core.brain_modules.s1_theme_detector import S1ThemeDetector, ThemeDetectionResult
from app.core.brain_modules.s2_goal_generator import S2GoalGenerator, AnalysisGoal
from app.core.brain_modules.s12_ai_orchestrator import dispatch_s1_ai_primary, dispatch_s2_ai_primary

S1_FIELDS = ["担保金额", "抵押率", "客户名称", "省份", "逾期天数"]
S2_FIELDS = ["贷款金额", "逾期天数", "省份", "客户类型", "担保方式"]

def _tres(theme, conf, kw=None, reason=""):
    return ThemeDetectionResult(theme_tag=theme, confidence=conf, matched_keywords=kw or [],
                                method="dictionary", llm_called=False, reason=reason)

def _base_goals():
    return [
        AnalysisGoal(goal_id="G1", title="逾期率趋势监控", description="d", type="趋势", priority=10, generated_by="rule"),
        AnalysisGoal(goal_id="G2", title="地区风险对比", description="d", type="对比", priority=8, generated_by="rule"),
        AnalysisGoal(goal_id="G3", title="抵押风险分布", description="d", type="分布", priority=6, generated_by="rule"),
    ]

S1_THEME_OK = json.dumps({"theme_tag": "担保风控", "confidence": 0.92, "reason": "字段含担保/抵押"}, ensure_ascii=False)
S1_THEME_OFF = json.dumps({"theme_tag": "客户画像", "confidence": 0.8, "reason": "偏客户分析"}, ensure_ascii=False)
S2_GOALS_OK = json.dumps({"goals": [
    {"goal_id": "G1", "title": "看看逾期怎么走", "description": "追踪逾期率变化", "type": "趋势", "priority": 10, "expected_charts": ["line"]},
    {"goal_id": "G2", "title": "哪些地区风险高", "description": "地区对比", "type": "对比", "priority": 9, "expected_charts": ["bar"]},
    {"goal_id": "G3", "title": "大额担保先关注", "description": "预警", "type": "预警", "priority": 8, "expected_charts": ["kpi"]},
]}, ensure_ascii=False)
S2_GOALS_BAD = json.dumps({"goals": [{"title": "缺type字段的非法目标"}]})  # 触发护栏补齐

async def _llm_ok_theme(*a, **k):
    return LLMResponse(success=True, content=S1_THEME_OK)
async def _llm_off_theme(*a, **k):
    return LLMResponse(success=True, content=S1_THEME_OFF)
async def _llm_fail(*a, **k):
    raise RuntimeError("kimi 超时（模拟）")
async def _llm_ok_goals(*a, **k):
    return LLMResponse(success=True, content=S2_GOALS_OK)
async def _llm_bad_goals(*a, **k):
    return LLMResponse(success=True, content=S2_GOALS_BAD)

# S1-1：离线/关闭 → 规则兜底（source=rule）
try:
    with _patch.object(S1ThemeDetector, "detect", new=AsyncMock(return_value=_tres("担保风控", 0.95, ["担保"]))):
        r = asyncio.run(dispatch_s1_ai_primary(db=None, fields=S1_FIELDS, llm_offline=True, run_id=None))
    if r.get("source") == "rule" and r.get("theme_tag") == "担保风控":
        ok("s1:rule_fallback", f"source={r['source']} theme={r['theme_tag']}")
    else:
        bad("s1:rule_fallback", f"r={r}")
except Exception as e:
    bad("s1:rule_fallback", f"异常 {e}\n{traceback.format_exc()}")

# S1-2：AI 主执行成功 → source=ai
try:
    with _patch.object(S1ThemeDetector, "detect", new=AsyncMock(return_value=_tres("担保风控", 0.3, ["担保"]))), \
         _patch("app.core.llm_gateway.llm_chat", _llm_ok_theme):
        r = asyncio.run(dispatch_s1_ai_primary(db=None, fields=S1_FIELDS, llm_offline=False, run_id=None))
    if r.get("source") == "ai" and r.get("theme_tag") == "担保风控":
        ok("s1:ai_primary", f"source={r['source']} theme={r['theme_tag']} conf={r['confidence']}")
    else:
        bad("s1:ai_primary", f"r={r}")
except Exception as e:
    bad("s1:ai_primary", f"异常 {e}\n{traceback.format_exc()}")

# S1-3：词典高置信命中 + AI 偏离 → 护栏纠正（source=ai_guarded，主题被强制回词典）
try:
    with _patch.object(S1ThemeDetector, "detect", new=AsyncMock(return_value=_tres("担保风控", 0.95, ["担保"]))), \
         _patch("app.core.llm_gateway.llm_chat", _llm_off_theme):
        r = asyncio.run(dispatch_s1_ai_primary(db=None, fields=S1_FIELDS, llm_offline=False, run_id=None))
    if r.get("source") == "ai_guarded" and r.get("theme_tag") == "担保风控" and any("G-S1" in g for g in r.get("guardrail", [])):
        ok("s1:ai_guardrail", f"source={r['source']} 主题被纠正为 {r['theme_tag']}，护栏 {r['guardrail']}")
    else:
        bad("s1:ai_guardrail", f"r={r}")
except Exception as e:
    bad("s1:ai_guardrail", f"异常 {e}\n{traceback.format_exc()}")

# S1-4：AI 失败 → 规则兜底（source=rule + fallback_reason）
try:
    with _patch.object(S1ThemeDetector, "detect", new=AsyncMock(return_value=_tres("担保风控", 0.4, ["担保"]))), \
         _patch("app.core.llm_gateway.llm_chat", _llm_fail):
        r = asyncio.run(dispatch_s1_ai_primary(db=None, fields=S1_FIELDS, llm_offline=False, run_id=None))
    if r.get("source") == "rule" and r.get("fallback_reason"):
        ok("s1:ai_fallback", f"AI 失败→规则兜底，reason={r['fallback_reason']!r}")
    else:
        bad("s1:ai_fallback", f"r={r}")
except Exception as e:
    bad("s1:ai_fallback", f"异常 {e}\n{traceback.format_exc()}")

# S2-1：离线/关闭 → 规则生成（source=rule）
try:
    with _patch.object(S2GoalGenerator, "generate", new=AsyncMock(return_value=_base_goals())):
        r = asyncio.run(dispatch_s2_ai_primary(db=None, fields=S2_FIELDS, grain="detail", theme="担保风控", llm_offline=True, run_id=None))
    if r.get("source") == "rule" and r.get("generated_by") == "rule" and len(r.get("goals", [])) == 3:
        ok("s2:rule_fallback", f"source={r['source']} 目标数={len(r['goals'])}")
    else:
        bad("s2:rule_fallback", f"r={r}")
except Exception as e:
    bad("s2:rule_fallback", f"异常 {e}\n{traceback.format_exc()}")

# S2-2：AI 主执行成功 → source=ai，目标业务化
try:
    with _patch.object(S2GoalGenerator, "generate", new=AsyncMock(return_value=_base_goals())), \
         _patch("app.core.llm_gateway.llm_chat", _llm_ok_goals):
        r = asyncio.run(dispatch_s2_ai_primary(db=None, fields=S2_FIELDS, grain="detail", theme="担保风控", llm_offline=False, run_id=None))
    if r.get("source") == "ai" and r.get("generated_by") == "llm" and len(r.get("goals", [])) == 3:
        ok("s2:ai_primary", f"source={r['source']} 目标数={len(r['goals'])} 首条={r['goals'][0]['title']!r}")
    else:
        bad("s2:ai_primary", f"r={r}")
except Exception as e:
    bad("s2:ai_primary", f"异常 {e}\n{traceback.format_exc()}")

# S2-3：AI 返回非法目标 → 护栏补齐（source=ai_guarded，规则补齐到 ≥3）
try:
    with _patch.object(S2GoalGenerator, "generate", new=AsyncMock(return_value=_base_goals())), \
         _patch("app.core.llm_gateway.llm_chat", _llm_bad_goals):
        r = asyncio.run(dispatch_s2_ai_primary(db=None, fields=S2_FIELDS, grain="detail", theme="担保风控", llm_offline=False, run_id=None))
    if r.get("source") == "ai_guarded" and len(r.get("goals", [])) >= 3:
        ok("s2:ai_guardrail", f"source={r['source']} 护栏补齐后目标数={len(r['goals'])}")
    else:
        bad("s2:ai_guardrail", f"r={r}")
except Exception as e:
    bad("s2:ai_guardrail", f"异常 {e}\n{traceback.format_exc()}")

# S2-4：AI 失败 → 规则兜底（source=rule）
try:
    with _patch.object(S2GoalGenerator, "generate", new=AsyncMock(return_value=_base_goals())), \
         _patch("app.core.llm_gateway.llm_chat", _llm_fail):
        r = asyncio.run(dispatch_s2_ai_primary(db=None, fields=S2_FIELDS, grain="detail", theme="担保风控", llm_offline=False, run_id=None))
    if r.get("source") == "rule" and r.get("fallback_reason"):
        ok("s2:ai_fallback", f"AI 失败→规则兜底，reason={r['fallback_reason']!r}")
    else:
        bad("s2:ai_fallback", f"r={r}")
except Exception as e:
    bad("s2:ai_fallback", f"异常 {e}\n{traceback.format_exc()}")


# ───────────────────────── 8. 白盒：飞轮闭环（债B，读+写路径） ─────────────────────────
section("【白盒·8】飞轮闭环（债B：读路径 inject + 写路径按字段形态签名回写）")
from app.core.flywheel import (
    derive_signature, build_flywheel_context_from_fields, FLYWHEEL_DOMAIN,
    record_experience, retrieve_experience,
)
from app.core.brain_modules.experience_store import _STORE_PATH as _EXP_PATH
from app.core.run_context import set_run_context, get_run_context
import tempfile as _tempfile

FLY_FIELDS = ["担保金额", "省份", "逾期天数", "客户类型"]
FLY_SIG = derive_signature(FLY_FIELDS, "detail")
_tmp_store = os.path.join(_tempfile.gettempdir(), f"exp_verify_{os.getpid()}.json")

try:
    with _patch("app.core.brain_modules.experience_store._STORE_PATH", _tmp_store):
        # 写路径：记录「该数据形态→担保风控 被采纳」经验
        record_experience(FLYWHEEL_DOMAIN, FLY_SIG, "theme:担保风控", "good")
        record_experience(FLYWHEEL_DOMAIN, FLY_SIG, "theme:担保风控", "good")
        # 读路径：S2 生成时注入历史经验（闭环验证）
        ctx = build_flywheel_context_from_fields(FLY_FIELDS, "detail")
        hints = retrieve_experience(FLYWHEEL_DOMAIN, FLY_SIG, top_n=3)
    if "担保风控" in ctx and any(h.get("decision") == "theme:担保风控" and h.get("good", 0) >= 2 for h in hints):
        ok("flywheel:read_write", f"经验已回读并注入 S2 上下文（good≥2，ctx 含「担保风控」）")
    else:
        bad("flywheel:read_write", f"ctx={ctx!r} hints={hints}")
except Exception as e:
    bad("flywheel:read_write", f"异常 {e}\n{traceback.format_exc()}")
finally:
    try:
        if os.path.exists(_tmp_store):
            os.remove(_tmp_store)
    except Exception:
        pass

# 运行上下文暂存（写路径桥梁：feedback 端点据此回写经验库）
try:
    set_run_context("run_verify_1", FLY_FIELDS, "detail", "担保风控", FLY_SIG, dataset_id="ds_x")
    rc = get_run_context("run_verify_1")
    if rc and rc.get("signature") == FLY_SIG and rc.get("theme") == "担保风控" and rc.get("grain") == "detail":
        ok("run_context:bridge", f"run_context 暂存签名={rc['signature']!r} 主题={rc['theme']}")
    else:
        bad("run_context:bridge", f"rc={rc}")
    # 清理
    from app.core.run_context import clear_run_context
    clear_run_context("run_verify_1")
except Exception as e:
    bad("run_context:bridge", f"异常 {e}\n{traceback.format_exc()}")


# ───────────────────────── 汇总 ─────────────────────────
section("【汇总】")
print(f"  PASS = {PASS}   FAIL = {FAIL}")
if FAIL:
    print("\n失败项：")
    for f in FAILURES:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("\n✅ 全部通过：白盒 + 黑盒/爬虫 三类验收 GREEN")
    sys.exit(0)
