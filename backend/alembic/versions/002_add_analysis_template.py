"""分析模板库表 - 2.6 P0

Revision ID: 002
Revises: 001
Create Date: 2026-09-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'analysis_template',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(120), nullable=False, comment='展示名'),
        sa.Column('description', sa.Text, comment='模板说明'),
        sa.Column('goal_skeleton', sa.JSON, comment='目标骨架（字段画像特征，非列名）'),
        sa.Column('match_features', sa.JSON, comment='匹配条件（字段画像特征，非列名）'),
        sa.Column('base_goals', sa.JSON, comment='预置分析目标（对齐 AnalysisGoal）'),
        sa.Column('approved', sa.Boolean, default=False, comment='须经用户确认才生效'),
        sa.Column('usage_count', sa.Integer, default=0, comment='被命中套用次数'),
        sa.Column('source', sa.String(10), default='system', comment='system/user/ai'),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('ix_analysis_template_approved', 'analysis_template', ['approved'])

    # ---- 2.6 收尾：种子分析模板（幂等，已存在 name 跳过）----
    # 与 scripts/seed_templates.py 内容一致；迁移自带，保证新装即带种子。
    import json as _json
    import uuid as _uuid
    _bind = op.get_bind()
    _seeds = [
        {
            "name": "担保风控标准六图",
            "description": "覆盖担保/抵押/质押业务的标准分析目标：金额、逾期、地区、抵押率、类型、预警。",
            "match_features": {"must_have_types": ["CATEGORY", "NUMBER"], "min_fields": 5,
                               "theme_hint": "担保|风控|抵押|质押|代偿|保证"},
            "base_goals": [
                {"goal_id": "TG1", "title": "总担保金额", "type": "KPI", "priority": 10, "expected_charts": ["kpi"]},
                {"goal_id": "TG2", "title": "逾期率趋势监控", "type": "趋势", "priority": 9, "expected_charts": ["line", "area"]},
                {"goal_id": "TG3", "title": "地区风险对比", "type": "对比", "priority": 8, "expected_charts": ["bar", "map"]},
                {"goal_id": "TG4", "title": "抵押率分布", "type": "分布", "priority": 7, "expected_charts": ["pie"]},
                {"goal_id": "TG5", "title": "大额担保风险预警", "type": "预警", "priority": 6, "expected_charts": ["kpi", "table"]},
                {"goal_id": "TG6", "title": "担保类型占比分析", "type": "分布", "priority": 5, "expected_charts": ["pie", "bar"]},
            ],
            "goal_skeleton": [{"type": "KPI", "role_hint": "金额指标", "title": "总担保金额"},
                              {"type": "趋势", "title": "逾期率趋势监控"}],
        },
        {
            "name": "客户画像分析",
            "description": "客户/借款人维度画像：规模分布、类型占比、地区分布、重点客户识别。",
            "match_features": {"must_have_types": ["CATEGORY", "NUMBER"], "min_fields": 4,
                               "theme_hint": "客户|画像|借款人|企业|客群"},
            "base_goals": [
                {"goal_id": "CG1", "title": "客户规模分布", "type": "分布", "priority": 10, "expected_charts": ["pie", "bar"]},
                {"goal_id": "CG2", "title": "客户类型占比", "type": "分布", "priority": 8, "expected_charts": ["pie"]},
                {"goal_id": "CG3", "title": "地区客户分布", "type": "分布", "priority": 7, "expected_charts": ["map", "bar"]},
                {"goal_id": "CG4", "title": "重点客户识别", "type": "画像", "priority": 6, "expected_charts": ["table", "kpi"]},
            ],
            "goal_skeleton": [{"type": "分布", "title": "客户规模分布"}, {"type": "画像", "title": "重点客户识别"}],
        },
        {
            "name": "贷款借据明细分析",
            "description": "单笔借据/贷款明细：放款趋势、逾期分布、借据类型、大额预警、还款结构。",
            "match_features": {"must_have_types": ["CATEGORY", "NUMBER", "DATE"], "min_fields": 6,
                               "theme_hint": "贷款|借据|放款|还款|合同|逾期|不良"},
            "base_goals": [
                {"goal_id": "LG1", "title": "放款金额趋势", "type": "趋势", "priority": 10, "expected_charts": ["line"]},
                {"goal_id": "LG2", "title": "逾期金额分布", "type": "分布", "priority": 8, "expected_charts": ["histogram", "bar"]},
                {"goal_id": "LG3", "title": "借据类型占比", "type": "分布", "priority": 7, "expected_charts": ["pie"]},
                {"goal_id": "LG4", "title": "大额借据风险预警", "type": "预警", "priority": 6, "expected_charts": ["kpi", "table"]},
                {"goal_id": "LG5", "title": "还款结构分析", "type": "关联", "priority": 5, "expected_charts": ["bar", "heatmap"]},
            ],
            "goal_skeleton": [{"type": "趋势", "title": "放款金额趋势"}, {"type": "预警", "title": "大额借据风险预警"}],
        },
        {
            "name": "销售经营分析",
            "description": "销售/经营类数据：收入趋势、产品占比、区域对比、热销排名。",
            "match_features": {"must_have_types": ["CATEGORY", "NUMBER"], "min_fields": 4,
                               "theme_hint": "销售|营收|经营|收入|产品|业绩"},
            "base_goals": [
                {"goal_id": "SG1", "title": "销售收入趋势", "type": "趋势", "priority": 10, "expected_charts": ["line"]},
                {"goal_id": "SG2", "title": "产品销售额占比", "type": "分布", "priority": 8, "expected_charts": ["pie"]},
                {"goal_id": "SG3", "title": "区域销售对比", "type": "对比", "priority": 7, "expected_charts": ["bar", "map"]},
                {"goal_id": "SG4", "title": "热销产品排名", "type": "KPI", "priority": 6, "expected_charts": ["kpi", "bar"]},
            ],
            "goal_skeleton": [{"type": "趋势", "title": "销售收入趋势"}, {"type": "分布", "title": "产品销售额占比"}],
        },
        {
            "name": "地区分布分析",
            "description": "地理维度：地区规模、增长趋势、对比、重点地区识别。",
            "match_features": {"must_have_types": ["CATEGORY", "NUMBER"], "min_fields": 4,
                               "theme_hint": "地区|省份|城市|区域|地理|行政区"},
            "base_goals": [
                {"goal_id": "RG1", "title": "地区规模分布", "type": "分布", "priority": 10, "expected_charts": ["map", "bar"]},
                {"goal_id": "RG2", "title": "地区增长趋势", "type": "趋势", "priority": 8, "expected_charts": ["line"]},
                {"goal_id": "RG3", "title": "地区对比分析", "type": "对比", "priority": 7, "expected_charts": ["bar", "map"]},
                {"goal_id": "RG4", "title": "重点地区识别", "type": "KPI", "priority": 6, "expected_charts": ["kpi"]},
            ],
            "goal_skeleton": [{"type": "分布", "title": "地区规模分布"}, {"type": "对比", "title": "地区对比分析"}],
        },
    ]
    for _s in _seeds:
        _exists = _bind.execute(
            sa.text("SELECT 1 FROM analysis_template WHERE name = :n"), {"n": _s["name"]}
        ).fetchone()
        if _exists:
            continue
        _bind.execute(sa.text(
            "INSERT INTO analysis_template "
            "(id, name, description, goal_skeleton, match_features, base_goals, approved, usage_count, source, created_at, updated_at) "
            "VALUES (:id, :name, :description, :goal_skeleton, :match_features, :base_goals, :approved, :usage_count, :source, "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ), {
            "id": _uuid.uuid4().hex,
            "name": _s["name"],
            "description": _s["description"],
            "goal_skeleton": _json.dumps(_s["goal_skeleton"], ensure_ascii=False),
            "match_features": _json.dumps(_s["match_features"], ensure_ascii=False),
            "base_goals": _json.dumps(_s["base_goals"], ensure_ascii=False),
            "approved": 1,
            "usage_count": 0,
            "source": "system",
        })


def downgrade() -> None:
    op.drop_index('ix_analysis_template_approved', table_name='analysis_template')
    op.drop_table('analysis_template')
