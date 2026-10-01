"""
图表模板库预置数据 - night14 Task B
8 个业务域各 1 个模板，SQL/配置硬编码白名单，禁止 LLM 生成。
config_json.charts 中的字段名是「候选名」，套用端点按目标数据集真实字段画像
精确/子串匹配，命不中则跳过该图（不臆造垃圾图，复用 executor 严格匹配护栏）。
"""
from __future__ import annotations

from typing import List, Dict, Any

# 8 个业务域预置模板（system 来源，启动时补种；已存在同名则跳过）
CHART_TEMPLATE_SEED: List[Dict[str, Any]] = [
    {
        "name": "担保风控·标准四图",
        "category": "担保风控",
        "description": "担保业务标准看板：余额 KPI + 区域分布 + 客户类型占比 + 月度趋势。",
        "tags": ["风控", "担保余额", "区域", "客户类型", "月度"],
        "config_json": {
            "charts": [
                {"chart_type": "kpi", "title": "总担保余额", "metric_field": "担保余额", "aggregation": "sum"},
                {"chart_type": "bar", "title": "各区域担保余额", "dimension_field": "区域", "metric_field": "担保余额", "aggregation": "sum"},
                {"chart_type": "pie", "title": "客户类型占比", "dimension_field": "客户类型", "metric_field": "担保余额"},
                {"chart_type": "line", "title": "月度担保余额趋势", "dimension_field": "月份", "metric_field": "担保余额", "aggregation": "sum"},
            ]
        },
    },
    {
        "name": "信贷审批·标准四图",
        "category": "信贷",
        "description": "信贷审批业务看板：放款 KPI + 产品分布 + 审批状态占比 + 月度趋势。",
        "tags": ["信贷", "放款金额", "产品类型", "审批状态", "月度"],
        "config_json": {
            "charts": [
                {"chart_type": "kpi", "title": "总放款金额", "metric_field": "放款金额", "aggregation": "sum"},
                {"chart_type": "bar", "title": "各产品放款金额", "dimension_field": "产品类型", "metric_field": "放款金额", "aggregation": "sum"},
                {"chart_type": "pie", "title": "审批状态占比", "dimension_field": "审批状态", "metric_field": "放款金额"},
                {"chart_type": "line", "title": "月度放款趋势", "dimension_field": "月份", "metric_field": "放款金额", "aggregation": "sum"},
            ]
        },
    },
    {
        "name": "财务分析·标准四图",
        "category": "财务",
        "description": "财务分析看板：收入 KPI + 科目分布 + 收支结构占比 + 月度趋势。",
        "tags": ["财务", "收入", "成本", "科目", "月度"],
        "config_json": {
            "charts": [
                {"chart_type": "kpi", "title": "总收入", "metric_field": "收入", "aggregation": "sum"},
                {"chart_type": "bar", "title": "各科目金额", "dimension_field": "科目", "metric_field": "金额", "aggregation": "sum"},
                {"chart_type": "pie", "title": "收支结构占比", "dimension_field": "类型", "metric_field": "金额"},
                {"chart_type": "line", "title": "月度收支趋势", "dimension_field": "月份", "metric_field": "收入", "aggregation": "sum"},
            ]
        },
    },
    {
        "name": "销售业绩·标准四图",
        "category": "销售",
        "description": "销售业绩看板：销售额 KPI + 区域分布 + 产品占比 + 月度趋势。",
        "tags": ["销售", "销售额", "区域", "产品", "月度"],
        "config_json": {
            "charts": [
                {"chart_type": "kpi", "title": "总销售额", "metric_field": "销售额", "aggregation": "sum"},
                {"chart_type": "bar", "title": "各区域销售额", "dimension_field": "区域", "metric_field": "销售额", "aggregation": "sum"},
                {"chart_type": "pie", "title": "产品占比", "dimension_field": "产品", "metric_field": "销售额"},
                {"chart_type": "line", "title": "月度销售额趋势", "dimension_field": "月份", "metric_field": "销售额", "aggregation": "sum"},
            ]
        },
    },
    {
        "name": "客户画像·标准四图",
        "category": "客户",
        "description": "客户画像看板：客户数 KPI + 等级分布 + 渠道占比 + 年龄段分布。",
        "tags": ["客户", "客户数", "等级", "渠道", "年龄段"],
        "config_json": {
            "charts": [
                {"chart_type": "kpi", "title": "客户总数", "metric_field": "客户数", "aggregation": "sum"},
                {"chart_type": "bar", "title": "各等级客户数", "dimension_field": "客户等级", "metric_field": "客户数", "aggregation": "sum"},
                {"chart_type": "pie", "title": "渠道占比", "dimension_field": "渠道", "metric_field": "客户数"},
                {"chart_type": "line", "title": "年龄段分布", "dimension_field": "年龄段", "metric_field": "客户数", "aggregation": "sum"},
            ]
        },
    },
    {
        "name": "运营监控·标准四图",
        "category": "运营",
        "description": "运营监控看板：订单量 KPI + 渠道分布 + 状态占比 + 日趋势。",
        "tags": ["运营", "订单量", "渠道", "状态", "日"],
        "config_json": {
            "charts": [
                {"chart_type": "kpi", "title": "总订单量", "metric_field": "订单量", "aggregation": "sum"},
                {"chart_type": "bar", "title": "各渠道订单量", "dimension_field": "渠道", "metric_field": "订单量", "aggregation": "sum"},
                {"chart_type": "pie", "title": "订单状态占比", "dimension_field": "订单状态", "metric_field": "订单量"},
                {"chart_type": "line", "title": "每日订单趋势", "dimension_field": "日期", "metric_field": "订单量", "aggregation": "sum"},
            ]
        },
    },
    {
        "name": "供应链·标准四图",
        "category": "供应链",
        "description": "供应链看板：采购额 KPI + 品类分布 + 供应商占比 + 月度趋势。",
        "tags": ["供应链", "采购额", "品类", "供应商", "月度"],
        "config_json": {
            "charts": [
                {"chart_type": "kpi", "title": "总采购额", "metric_field": "采购额", "aggregation": "sum"},
                {"chart_type": "bar", "title": "各品类采购额", "dimension_field": "品类", "metric_field": "采购额", "aggregation": "sum"},
                {"chart_type": "pie", "title": "供应商占比", "dimension_field": "供应商", "metric_field": "采购额"},
                {"chart_type": "line", "title": "月度采购趋势", "dimension_field": "月份", "metric_field": "采购额", "aggregation": "sum"},
            ]
        },
    },
    {
        "name": "人力资源·标准四图",
        "category": "人力",
        "description": "人力看板：人数 KPI + 部门分布 + 职级占比 + 月度入职趋势。",
        "tags": ["人力", "人数", "部门", "职级", "月度"],
        "config_json": {
            "charts": [
                {"chart_type": "kpi", "title": "员工总数", "metric_field": "人数", "aggregation": "sum"},
                {"chart_type": "bar", "title": "各部门人数", "dimension_field": "部门", "metric_field": "人数", "aggregation": "sum"},
                {"chart_type": "pie", "title": "职级占比", "dimension_field": "职级", "metric_field": "人数"},
                {"chart_type": "line", "title": "月度入职趋势", "dimension_field": "月份", "metric_field": "人数", "aggregation": "sum"},
            ]
        },
    },
]


async def init_chart_templates(db) -> int:
    """启动时补种 8 个 system 预置模板；同名已存在则跳过。返回新增条数。"""
    from sqlalchemy import select
    from app.models.chart_template import ChartTemplate

    existing = set()
    res = await db.execute(select(ChartTemplate.name))
    for (nm,) in res.all():
        existing.add(nm)

    added = 0
    for spec in CHART_TEMPLATE_SEED:
        if spec["name"] in existing:
            continue
        tpl = ChartTemplate(
            name=spec["name"],
            category=spec["category"],
            description=spec.get("description", ""),
            config_json=spec["config_json"],
            tags=spec.get("tags", []),
            source="system",
        )
        db.add(tpl)
        added += 1
    if added:
        await db.commit()
    return added
