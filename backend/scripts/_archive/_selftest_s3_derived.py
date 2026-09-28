"""
自测：派生指标反哺 S3（规则引擎 + LLM 输出后处理）

覆盖三条硬保证：
  1. 已验证派生指标优先被选作图表指标（打分提权）
  2. 图表 config 带上加工公式（derived_metric），供血缘/前端白盒展示
  3. 比率类派生指标禁止求和：即便上游给了 sum，也必须纠正为 avg

运行：cd backend && python _selftest_s3_derived.py
（不依赖 DuckDB / 后端进程，纯逻辑自测）
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.brain_modules.s3_chart_engine_v2 import S3ChartEngine
from app.core.brain_modules.s3_llm_enhancer import S3LLMEnhancer
from app.core.derived_metric_service import annotate_fields

FIELDS = [
    "借款人ID", "贷款类型", "单位所属行业", "贷款金额", "担保余额",
    "抵押物评估价值", "抵押率", "逾期天数", "放款日期", "风险等级",
]

SAMPLE = [
    {"借款人ID": "C001", "贷款类型": "公积金", "单位所属行业": "制造业", "贷款金额": 1200000,
     "担保余额": 900000, "抵押物评估价值": 1500000, "抵押率": 80.0, "逾期天数": 0,
     "放款日期": "2024-01-15", "风险等级": "低"},
    {"借款人ID": "C002", "贷款类型": "商业", "单位所属行业": "IT", "贷款金额": 2500000,
     "担保余额": 1800000, "抵押物评估价值": 2000000, "抵押率": 125.0, "逾期天数": 12,
     "放款日期": "2024-02-20", "风险等级": "中"},
]

DERIVED = {
    "抵押率": {
        "metric": "抵押率",
        "op": "div_pct",
        "expression": "贷款金额 ÷ 抵押物评估价值 × 100",
        "formula": "抵押率 = 贷款金额 ÷ 抵押物评估价值 × 100",
        "components": ["贷款金额", "抵押物评估价值"],
        "match_ratio": 0.98,
    }
}

ok = True


def check(name, cond, extra=""):
    global ok
    flag = "PASS" if cond else "FAIL"
    if not cond:
        ok = False
    print(f"  [{flag}] {name}{(' -> ' + str(extra)) if extra else ''}")


print("== 1) 规则引擎：派生指标提权 + 公式落配置 ==")
cfg = S3ChartEngine(derived_metrics=DERIVED).generate_dashboard_config(
    fields=FIELDS, grain="detail", sample_data=SAMPLE
)
charts = cfg.get("charts") or []
hit = [c for c in charts if (c.get("y_field") or c.get("value_field")) == "抵押率"]
check("至少一张图的指标选中「抵押率」", len(hit) > 0,
      [c.get("title") for c in charts])
if hit:
    c0 = hit[0]
    dm = (c0.get("config") or {}).get("derived_metric") or {}
    check("config.derived_metric 带加工公式", "抵押率 =" in dm.get("formula", ""),
          dm.get("formula"))
    check("config.derived_metric 带分量列",
          set(dm.get("components") or []) == {"贷款金额", "抵押物评估价值"},
          dm.get("components"))
    check("比率类聚合为 avg", (c0.get("config") or {}).get("aggregation") == "avg",
          (c0.get("config") or {}).get("aggregation"))
check("generate 返回体带 derived_metrics", "抵押率" in (cfg.get("derived_metrics") or {}),
      list((cfg.get("derived_metrics") or {}).keys()))

# 比率类 KPI 不能叫"总X"，也不能带金额货币前缀
_kpis = [c for c in charts if c.get("chart_type") == "kpi"
         and (c.get("y_field") or c.get("value_field")) == "抵押率"]
for _k in _kpis:
    check("比率 KPI 标题为「平均X」而非「总X」",
          not str(_k.get("title", "")).startswith("总"), _k.get("title"))
    check("比率 KPI 不带金额 ¥ 前缀",
          "prefix" not in (_k.get("config") or {}), (_k.get("config") or {}).get("prefix"))

print("== 2) 同图不重复：派生指标与其分量列不共存 ==")
for c in charts:
    metric = c.get("y_field") or c.get("value_field")
    refs = {c.get("x_field"), c.get("y_field"), c.get("category_field"), c.get("value_field")}
    refs.discard(None)
    if metric == "抵押率":
        overlap = refs & {"贷款金额", "抵押物评估价值"}
        check(f"「{c.get('title')}」不含该指标的分量列", not overlap, refs)

print("== 3) LLM 输出后处理：比率求和被强制纠正 ==")
llm_charts = [
    {"chart_type": "bar", "title": "各贷款类型抵押率", "x_field": "贷款类型",
     "y_field": "抵押率", "aggregate": "sum",
     "config": {"aggregate": "sum"}},
    {"chart_type": "kpi", "title": "总贷款金额", "y_field": "贷款金额",
     "aggregate": "sum", "config": {}},
]
fixed = S3LLMEnhancer._apply_derived_metrics(llm_charts, DERIVED)
c_ratio = fixed[0]
check("顶层 aggregate: sum -> avg", c_ratio.get("aggregate") == "avg", c_ratio.get("aggregate"))
check("config.aggregate: sum -> avg",
      (c_ratio.get("config") or {}).get("aggregate") == "avg",
      (c_ratio.get("config") or {}).get("aggregate"))
check("补写 derived_metric",
      "抵押率 =" in ((c_ratio.get("config") or {}).get("derived_metric") or {}).get("formula", ""),
      (c_ratio.get("config") or {}).get("derived_metric"))
check("非派生指标（贷款金额 sum）不受影响",
      fixed[1].get("aggregate") == "sum" and "derived_metric" not in (fixed[1].get("config") or {}),
      fixed[1])

print("== 4) 字段描述标注（喂给 LLM 感知口径） ==")
desc = "\n".join(f"  - {f}（数值/指标）" for f in FIELDS)
annotated = annotate_fields(desc, DERIVED)
line = [l for l in annotated.splitlines() if "抵押率" in l]
check("抵押率行带派生指标标注", bool(line) and "派生指标" in line[0], line[0] if line else "")
check("标注含安全汇总方式", bool(line) and "avg" in line[0], line[0] if line else "")

print()
print("RESULT:", "ALL PASS" if ok else "HAS FAILURE")
sys.exit(0 if ok else 1)
