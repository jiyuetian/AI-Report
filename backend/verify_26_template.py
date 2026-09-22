"""
2.6 P0 真实跑验证：分析模板匹配（命中 / 不命中 / 未批准门禁）

用内存 sqlite(async + aiosqlite) 真实建表 + 插入 + 查询 + 匹配，验证：
  - T1 命中：approved=True 且 profile 满足 match_features → 返回该模板
  - T2 不命中：approved=True 但 profile 不满足 → 返回空
  - T3 门禁：approved=False 即使 match_features 满足 → 不返回（防污染）
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.analysis_template import AnalysisTemplate
from app.core.brain_modules.s2_goal_generator import match_templates


ASYNC_DB = "sqlite+aiosqlite:///:memory:"


async def main():
    engine = create_async_engine(ASYNC_DB, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        # ---- 插入三条模板 ----
        t_match = AnalysisTemplate(
            name="担保风控标准六图",
            source="system",
            approved=True,
            match_features={
                "must_have_types": ["CATEGORY", "NUMBER"],
                "semantic_hints": ["比率类", "金额指标"],
                "min_fields": 4,
                "theme_hint": "担保|风控",
                "cardinality_need": ["high"],
            },
            base_goals=[
                {"goal_id": "TG1", "title": "总担保金额", "type": "KPI", "priority": 10, "expected_charts": ["kpi"]},
                {"goal_id": "TG2", "title": "抵押率分布", "type": "分布", "priority": 8, "expected_charts": ["pie"]},
            ],
            goal_skeleton=[{"type": "KPI", "role_hint": "金额指标", "title": "总担保金额"}],
        )
        t_nomatch = AnalysisTemplate(
            name="医疗专项模板",
            source="system",
            approved=True,
            match_features={"theme_hint": "医疗|医院", "min_fields": 50},
            base_goals=[{"goal_id": "MG1", "title": "患者数量", "type": "KPI", "priority": 9, "expected_charts": ["kpi"]}],
            goal_skeleton=[],
        )
        t_unapproved = AnalysisTemplate(
            name="未确认候选模板(应被门禁排除)",
            source="ai",
            approved=False,
            match_features={"must_have_types": ["CATEGORY", "NUMBER"], "theme_hint": "担保|风控"},
            base_goals=[{"goal_id": "UG1", "title": "应不出现", "type": "KPI", "priority": 5, "expected_charts": ["kpi"]}],
            goal_skeleton=[],
        )
        db.add_all([t_match, t_nomatch, t_unapproved])
        await db.commit()

        # ---- T1：命中 profile ----
        profile_hit = {
            "type_buckets": ["CATEGORY", "NUMBER", "DATE"],
            "business_roles": ["比率类", "金额指标"],
            "recommended_aggs": ["sum", "avg", "count"],
            "cardinality_buckets": ["low", "high"],
            "field_count": 8,
            "theme": "担保风控",
        }
        matched_hit = await match_templates(db, profile_hit)
        names_hit = [t.name for t in matched_hit]

        # ---- T2：不命中 profile ----
        profile_miss = {
            "type_buckets": ["TEXT"],
            "business_roles": [],
            "recommended_aggs": [],
            "cardinality_buckets": ["low"],
            "field_count": 2,
            "theme": "通用分析",
        }
        matched_miss = await match_templates(db, profile_miss)

        # ---- 断言 ----
        assert "担保风控标准六图" in names_hit, f"T1 命中失败：{names_hit}"
        assert "医疗专项模板" not in names_hit, "T2 不相关模板不应命中"
        assert "未确认候选模板(应被门禁排除)" not in names_hit, "T3 未批准模板不应命中"
        assert len(matched_miss) == 0, f"T2 不命中应返回空：{[t.name for t in matched_miss]}"

        # ---- T4：并入候选集成（_apply_templates 直接验证 merge 层）----
        from app.core.brain_modules.s2_goal_generator import S2GoalGenerator, AnalysisGoal

        gen = S2GoalGenerator()
        base = [AnalysisGoal(goal_id="G1", title="逾期率趋势监控", description="追踪逾期率变化", type="趋势", priority=10, expected_charts=["line"])]
        orig_n = len(base)
        merged = await gen._apply_templates(
            db, base, theme="担保风控",
            fields=["担保类型", "担保金额", "抵押率", "客户名称", "地区", "日期"],
            grain="detail",
            field_profiles=[
                {"name": "担保金额", "distinct_count": 120},
                {"name": "抵押率", "distinct_count": 300},
                {"name": "地区", "distinct_count": 30},
                {"name": "担保类型", "distinct_count": 2},
            ],
        )
        merged_titles = [g.title for g in merged]
        merged_by = [g.generated_by for g in merged]
        assert "总担保金额" in merged_titles, f"T4 模板目标未并入：{merged_titles}"
        assert "template" in merged_by, "T4 并入目标 generated_by 应为 template"

        print("=== verify_26_template PASS ===")
        print(f"T1 命中用例返回: {names_hit}  (期望仅含 [担保风控标准六图])")
        print(f"T2 不命中用例返回: {[t.name for t in matched_miss]}  (期望空)")
        print(f"T3 门禁: 未批准模板未被返回 ✓")
        print(f"T4 并入集成: 原 {orig_n} 个 → 并入后 {len(merged)} 个，含模板目标 "
              f"{[t for t in merged_titles if t in ('总担保金额', '抵押率分布')]}，generated_by={merged_by}")
        print("ALL_PASS=True")
        print(f"T1 命中用例返回: {names_hit}  (期望仅含 [担保风控标准六图])")
        print(f"T2 不命中用例返回: {[t.name for t in matched_miss]}  (期望空)")
        print(f"T3 门禁: 未批准模板未被返回 ✓")
        print("ALL_PASS=True")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
