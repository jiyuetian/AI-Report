# -*- coding: utf-8 -*-
"""2.5 P0 验收：直接调 _build_prompt，验证 fields_desc 含 distinct/空值率/高基数标注。

V1：fields_desc 含 `distinct=` 与 `空值率`，高基数字段带「禁止作为分类维度」
V2：构造 distinct=2143 的「客户名称」→ prompt 带高基数禁维度标注（LLM 据此不选饼图）
额外：字段名归一化匹配（profile 带空格）、敏感字段跳过取值样例但保留 distinct。
"""
import sys, io, os
REPO = "C:/Users/Asus009/Desktop/临时/ai大赛/AI-Report"
sys.path.insert(0, os.path.join(REPO, "backend"))

from app.core.brain_modules.s3_chart_engine_v2 import FieldType
from app.core.brain_modules.s3_llm_enhancer import S3LLMEnhancer

def build_semantics():
    type_map = {
        "客户名称": FieldType.TEXT,
        "担保类型": FieldType.CATEGORY,
        "抵押率": FieldType.NUMBER,
        " 身份证号 ": FieldType.TEXT,   # 带首尾空格 + 敏感，验证归一化 + V4 前置
    }
    meta = {
        "客户名称": {"business_role": "客户标识", "chart_hint": "", "cardinality": "high",
                     "distribution_ok": False, "priority": 50, "ai": True},
        "担保类型": {"business_role": "担保分类", "chart_hint": "建议做占比", "cardinality": "low",
                     "distribution_ok": True, "priority": 50, "ai": True},
        "抵押率": {"business_role": "比率指标", "chart_hint": "只能avg", "cardinality": "mid",
                   "distribution_ok": True, "priority": 50, "ai": True},
        " 身份证号 ": {"business_role": "标识", "chart_hint": "", "cardinality": "high",
                      "distribution_ok": False, "priority": 50, "ai": True},
    }
    return {"type_map": type_map, "meta": meta, "dim_order": [], "enriched": True}

def build_profiles():
    return [
        {"name": "客户名称", "distinct_count": 2143, "null_rate": 0.0},
        {"name": "担保类型", "distinct_count": 2, "null_rate": 0.0, "sample_values": ["融资性", "非融资性"]},
        {"name": "抵押率", "distinct_count": 56, "null_rate": 0.03},
        # profile 名带首尾空格 → 验证归一化仍能匹配到「 身份证号 」字段
        {"name": " 身份证号 ", "distinct_count": 980, "null_rate": 0.0, "sample_values": ["3301...", "4402..."]},
    ]

enhancer = S3LLMEnhancer()
semantics = build_semantics()
profiles = build_profiles()
prompt = enhancer._build_prompt(
    theme="担保风控",
    fields=list(semantics["type_map"].keys()),
    goals=[{"title": "担保趋势", "type": "趋势"}],
    grain="detail",
    semantics=semantics,
    derived_metrics=None,
    field_profiles=profiles,
)

# 截取 fields_desc 段，便于肉眼核对
seg = prompt.split("【字段列表及类型")[1].split("】")[0] if "【字段列表及类型" in prompt else prompt
print("===== fields_desc 段 =====")
print(seg[:900])
print("=========================")

fails = 0
def check(name, cond):
    global fails
    print(("  PASS" if cond else "  FAIL") + " | " + name)
    if not cond:
        fails += 1

# V1
check("客户名称 含 distinct=2143", "distinct=2143" in prompt)
check("担保类型 含 distinct=2", "distinct=2" in prompt)
check("抵押率 含 空值率3%", "空值率3%" in prompt)
check("担保类型 含 空值率0%", "空值率0%" in prompt)
# V2 高基数禁维度
check("客户名称 高基数带『禁止作为分类维度』", "⚠️高基数，禁止作为分类维度" in prompt)
# 取值样例
check("担保类型 含取值样例 融资性/非融资性", "取值:融资性/非融资性" in prompt)
# 字段名归一化：profile「 身份证号 」匹配字段「 身份证号 」→ 仍显示 distinct
check("敏感字段 身份证号 归一化匹配成功(distinct=980)", "distinct=980" in prompt)
# V4 前置：敏感字段不注入取值样例（其值 3301.../4402... 不应出现在 prompt）
check("V4前置：敏感字段取值样例未注入(3301 不出现)", "3301" not in prompt and "4402" not in prompt)

print()
print("RESULT:", "ALL PASS" if fails == 0 else f"{fails} FAIL")
sys.exit(1 if fails else 0)
