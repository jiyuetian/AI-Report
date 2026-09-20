"""初始化所有表结构

Revision ID: 001
Revises: 
Create Date: 2026-08-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 用户和权限表
    op.create_table(
        'users',
        sa.Column('id', sa.String(100), primary_key=True),
        sa.Column('username', sa.String(100), unique=True, nullable=False),
        sa.Column('email', sa.String(255), unique=True, nullable=False),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('full_name', sa.String(100)),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('is_superuser', sa.Boolean, default=False),
        sa.Column('token_quota', sa.Integer, default=5000),
        sa.Column('last_login', sa.DateTime),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    op.create_table(
        'roles',
        sa.Column('id', sa.String(100), primary_key=True),
        sa.Column('name', sa.String(50), unique=True, nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('default_quota', sa.Integer, default=5000),
        sa.Column('permissions', sa.Text),  # JSON
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    op.create_table(
        'user_roles',
        sa.Column('user_id', sa.String(100), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('role_id', sa.String(100), sa.ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True),
    )
    
    # 2. 文件表
    op.create_table(
        'files',
        sa.Column('id', sa.String(100), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('hash', sa.String(64), nullable=False, index=True),
        sa.Column('size', sa.Integer, nullable=False),
        sa.Column('mime_type', sa.String(100), nullable=False),
        sa.Column('extension', sa.String(20), nullable=False),
        sa.Column('storage_path', sa.String(500), nullable=False),
        sa.Column('status', sa.String(20), default='temporary'),
        sa.Column('expire_at', sa.DateTime),
        sa.Column('uploaded_by', sa.String(100)),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # 3. 数据集表
    op.create_table(
        'datasets',
        sa.Column('id', sa.String(100), primary_key=True),
        sa.Column('file_id', sa.String(100), sa.ForeignKey('files.id', ondelete='CASCADE'), nullable=False),
        sa.Column('duckdb_table', sa.String(100), nullable=False),
        sa.Column('grain', sa.String(20), default='row'),
        sa.Column('schema_json', sa.JSON, default=dict),
        sa.Column('profile_json', sa.JSON, default=dict),
        sa.Column('quality_score', sa.Integer),
        sa.Column('row_count', sa.Integer, default=0),
        sa.Column('status', sa.String(20), default='pending'),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # 4. 质量问题表
    op.create_table(
        'quality_issues',
        sa.Column('id', sa.String(100), primary_key=True),
        sa.Column('dataset_id', sa.String(100), sa.ForeignKey('datasets.id', ondelete='CASCADE'), nullable=False),
        sa.Column('field_name', sa.String(100)),
        sa.Column('type', sa.String(20), nullable=False),  # uniqueness/null/range/logic/code/format
        sa.Column('severity', sa.String(20), default='warning'),  # blocking/warning
        sa.Column('status', sa.String(20), default='todo'),  # todo/done/ignored
        sa.Column('message', sa.Text, nullable=False),
        sa.Column('fix_rule', sa.JSON),
        sa.Column('affect_rows', sa.Integer),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # 5. 清洗规则表
    op.create_table(
        'clean_rules',
        sa.Column('id', sa.String(100), primary_key=True),
        sa.Column('dataset_id', sa.String(100), sa.ForeignKey('datasets.id', ondelete='CASCADE'), nullable=False),
        sa.Column('rule_type', sa.String(30), nullable=False),
        sa.Column('target_field', sa.String(100)),
        sa.Column('params', sa.JSON, default=dict),
        sa.Column('reversible', sa.Boolean, default=True),
        sa.Column('execution_order', sa.Integer, default=0),
        sa.Column('applied_at', sa.DateTime),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # 6. 看板表
    op.create_table(
        'dashboards',
        sa.Column('id', sa.String(100), primary_key=True),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('theme_tag', sa.String(50)),
        sa.Column('score', sa.Integer),
        sa.Column('current_version', sa.Integer, default=1),
        sa.Column('dataset_ids', postgresql.ARRAY(sa.String)),  # 多数据源
        sa.Column('layout_config', sa.JSON),
        sa.Column('status', sa.String(20), default='draft'),  # draft/published/archived
        sa.Column('owner_id', sa.String(100), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # 7. 看板版本表
    op.create_table(
        'dashboard_versions',
        sa.Column('id', sa.String(100), primary_key=True),
        sa.Column('dashboard_id', sa.String(100), sa.ForeignKey('dashboards.id', ondelete='CASCADE'), nullable=False),
        sa.Column('version', sa.Integer, nullable=False),
        sa.Column('snapshot_json', sa.JSON, nullable=False),
        sa.Column('created_by', sa.String(100)),
        sa.Column('comment', sa.Text),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
    )
    
    # 8. 图表表
    op.create_table(
        'charts',
        sa.Column('id', sa.String(100), primary_key=True),
        sa.Column('dashboard_id', sa.String(100), sa.ForeignKey('dashboards.id', ondelete='CASCADE'), nullable=False),
        sa.Column('dataset_id', sa.String(100), sa.ForeignKey('datasets.id'), nullable=False),
        sa.Column('type', sa.String(20), nullable=False),  # line/bar/pie/scatter/table/kpi/funnel/radar
        sa.Column('config_json', sa.JSON, nullable=False),
        sa.Column('query_config', sa.JSON),
        sa.Column('position', sa.JSON),
        sa.Column('title', sa.String(255)),
        sa.Column('status', sa.String(20), default='ok'),  # ok/degraded/failed/stale
        sa.Column('sort_order', sa.Integer, default=0),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # 9. 对话会话表
    op.create_table(
        'chat_sessions',
        sa.Column('id', sa.String(100), primary_key=True),
        sa.Column('dashboard_id', sa.String(100), sa.ForeignKey('dashboards.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.String(100), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('title', sa.String(255)),
        sa.Column('total_tokens', sa.Integer, default=0),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # 10. 对话消息表
    op.create_table(
        'chat_messages',
        sa.Column('id', sa.String(100), primary_key=True),
        sa.Column('session_id', sa.String(100), sa.ForeignKey('chat_sessions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.String(20), nullable=False),  # user/assistant
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('tokens', sa.Integer),
        sa.Column('action_type', sa.String(30)),  # query/switch_chart/add_chart/drilldown/style_change
        sa.Column('ref_chart_id', sa.String(100)),
        sa.Column('meta_json', sa.JSON),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
    )
    
    # 11. 血缘节点表
    op.create_table(
        'lineage_nodes',
        sa.Column('id', sa.String(100), primary_key=True),
        sa.Column('node_type', sa.String(30), nullable=False),  # source/field/clean/business/agg/chart
        sa.Column('ref_id', sa.String(100), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('logic_json', sa.JSON),
        sa.Column('quality_flag', sa.String(50)),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # 12. 血缘边表
    op.create_table(
        'lineage_edges',
        sa.Column('id', sa.String(100), primary_key=True),
        sa.Column('source_id', sa.String(100), sa.ForeignKey('lineage_nodes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('target_id', sa.String(100), sa.ForeignKey('lineage_nodes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('transform_type', sa.String(30), default='direct'),  # direct/transform/aggregate/filter
        sa.Column('description', sa.Text),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
    )
    
    # 13. 分享链接表
    op.create_table(
        'share_links',
        sa.Column('id', sa.String(100), primary_key=True),
        sa.Column('dashboard_id', sa.String(100), sa.ForeignKey('dashboards.id', ondelete='CASCADE'), nullable=False),
        sa.Column('perm', sa.String(20), default='view'),  # view/edit
        sa.Column('expire_at', sa.DateTime),
        sa.Column('password', sa.String(100)),
        sa.Column('revoked', sa.Boolean, default=False),
        sa.Column('access_count', sa.Integer, default=0),
        sa.Column('created_by', sa.String(100), nullable=False),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
    )
    
    # 14. 导出任务表
    op.create_table(
        'export_tasks',
        sa.Column('id', sa.String(100), primary_key=True),
        sa.Column('dashboard_id', sa.String(100), sa.ForeignKey('dashboards.id', ondelete='CASCADE'), nullable=False),
        sa.Column('fmt', sa.String(20), nullable=False),  # pdf/png/excel/ppt
        sa.Column('status', sa.String(20), default='pending'),  # pending/processing/completed/failed
        sa.Column('file_path', sa.Text),
        sa.Column('file_size', sa.Integer, default=0),
        sa.Column('expire_at', sa.DateTime),
        sa.Column('error_msg', sa.Text),
        sa.Column('created_by', sa.String(100), nullable=False),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # 15. 配额使用表
    op.create_table(
        'quota_usage',
        sa.Column('user_id', sa.String(100), nullable=False),
        sa.Column('date', sa.Date, nullable=False),
        sa.Column('used_tokens', sa.Integer, default=0),
        sa.PrimaryKeyConstraint('user_id', 'date'),
    )
    
    # 16. 审计日志表
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.String(100), primary_key=True),
        sa.Column('user', sa.String(100)),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('object_type', sa.String(50)),
        sa.Column('object_id', sa.String(100)),
        sa.Column('ip', sa.String(50)),
        sa.Column('result', sa.String(20), default='success'),
        sa.Column('detail_json', sa.JSON),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
    )
    
    # 17. 策略大脑追踪表（P0）
    op.create_table(
        'brain_traces',
        sa.Column('id', sa.String(100), primary_key=True),
        sa.Column('run_id', sa.String(100), nullable=False, index=True),
        sa.Column('stage', sa.String(20), nullable=False),  # S1_theme/S2_goal/S3_chart/S4_layout/S5_eval
        sa.Column('input_json', sa.JSON, default=dict),
        sa.Column('output_json', sa.JSON, default=dict),
        sa.Column('latency_ms', sa.Integer),
        sa.Column('prompt_version', sa.String(50), default='1.0'),
        sa.Column('status', sa.String(20), default='success'),  # success/failure/retry
        sa.Column('error_msg', sa.Text),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
    )
    
    # 18. 策略大脑配置表
    op.create_table(
        'brain_configs',
        sa.Column('id', sa.String(100), primary_key=True),
        sa.Column('key', sa.String(50), nullable=False, unique=True),
        sa.Column('version', sa.String(20), default='1.0'),
        sa.Column('content_yaml', sa.Text, nullable=False),
        sa.Column('status', sa.String(20), default='active'),  # active/inactive
        sa.Column('rollout_percent', sa.Integer, default=100),
        sa.Column('description', sa.Text),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # 创建索引
    op.create_index('idx_files_hash', 'files', ['hash'])
    op.create_index('idx_datasets_file_id', 'datasets', ['file_id'])
    op.create_index('idx_quality_issues_dataset_id', 'quality_issues', ['dataset_id'])
    op.create_index('idx_charts_dashboard_id', 'charts', ['dashboard_id'])
    op.create_index('idx_chat_messages_session_id', 'chat_messages', ['session_id'])
    op.create_index('idx_brain_traces_run_id', 'brain_traces', ['run_id'])
    op.create_index('idx_audit_logs_created_at', 'audit_logs', ['created_at'])


def downgrade() -> None:
    # 删除表（倒序）
    op.drop_table('brain_configs')
    op.drop_table('brain_traces')
    op.drop_table('audit_logs')
    op.drop_table('quota_usage')
    op.drop_table('export_tasks')
    op.drop_table('share_links')
    op.drop_table('lineage_edges')
    op.drop_table('lineage_nodes')
    op.drop_table('chat_messages')
    op.drop_table('chat_sessions')
    op.drop_table('charts')
    op.drop_table('dashboard_versions')
    op.drop_table('dashboards')
    op.drop_table('clean_rules')
    op.drop_table('quality_issues')
    op.drop_table('datasets')
    op.drop_table('files')
    op.drop_table('user_roles')
    op.drop_table('roles')
    op.drop_table('users')