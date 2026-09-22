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


def downgrade() -> None:
    op.drop_index('ix_analysis_template_approved', table_name='analysis_template')
    op.drop_table('analysis_template')
