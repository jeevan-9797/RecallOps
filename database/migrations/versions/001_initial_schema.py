"""001_initial_schema

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-11-06 14:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. engineers
    op.create_table(
        'engineers',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('team', sa.String(length=64), nullable=False),
        sa.Column('slack_handle', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slack_handle')
    )

    # 2. services
    op.create_table(
        'services',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('team', sa.String(length=64), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=True),
        sa.Column('tier', sa.String(length=16), nullable=False, server_default='Tier-1'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['owner_id'], ['engineers.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    op.create_index('idx_services_team', 'services', ['team'])
    op.create_index('idx_services_tier', 'services', ['tier'])

    # 3. deploys
    op.create_table(
        'deploys',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('service_id', sa.Integer(), nullable=False),
        sa.Column('author_id', sa.Integer(), nullable=True),
        sa.Column('deployed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('config_change', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('diff_note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['author_id'], ['engineers.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['service_id'], ['services.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_deploys_service_deployed', 'deploys', ['service_id', 'deployed_at'])
    op.create_index('idx_deploys_deployed_at', 'deploys', ['deployed_at'])

    # 4. alerts
    op.create_table(
        'alerts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('service_id', sa.Integer(), nullable=False),
        sa.Column('metric', sa.String(length=128), nullable=False),
        sa.Column('threshold', sa.Float(), nullable=False),
        sa.Column('value', sa.Float(), nullable=False),
        sa.Column('fired_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['service_id'], ['services.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_alerts_service_fired', 'alerts', ['service_id', 'fired_at'])
    op.create_index('idx_alerts_metric', 'alerts', ['metric'])

    # 5. incidents
    op.create_table(
        'incidents',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(length=32), nullable=False),
        sa.Column('alert_id', sa.Integer(), nullable=True),
        sa.Column('severity', sa.String(length=16), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='OPEN'),
        sa.Column('opened_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('root_cause', sa.Text(), nullable=False),
        sa.Column('root_cause_family', sa.String(length=64), nullable=False),
        sa.Column('duration_min', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.CheckConstraint("severity IN ('P1', 'P2', 'P3', 'P4')", name='chk_incident_severity'),
        sa.CheckConstraint("status IN ('OPEN', 'INVESTIGATING', 'MITIGATED', 'RESOLVED')", name='chk_incident_status'),
        sa.CheckConstraint("resolved_at IS NULL OR resolved_at >= opened_at", name='chk_incident_resolved_after_opened'),
        sa.ForeignKeyConstraint(['alert_id'], ['alerts.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code')
    )
    op.create_index('idx_incidents_code', 'incidents', ['code'])
    op.create_index('idx_incidents_status', 'incidents', ['status'])
    op.create_index('idx_incidents_severity', 'incidents', ['severity'])
    op.create_index('idx_incidents_opened_at', 'incidents', ['opened_at'])
    op.create_index('idx_incidents_family', 'incidents', ['root_cause_family'])

    # 6. log_lines
    op.create_table(
        'log_lines',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('incident_id', sa.Integer(), nullable=False),
        sa.Column('ts', sa.DateTime(timezone=True), nullable=False),
        sa.Column('level', sa.String(length=16), nullable=False),
        sa.Column('source', sa.String(length=64), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.CheckConstraint("level IN ('DEBUG', 'INFO', 'WARN', 'ERROR', 'FATAL')", name='chk_log_level'),
        sa.ForeignKeyConstraint(['incident_id'], ['incidents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_log_lines_incident_ts', 'log_lines', ['incident_id', 'ts'])
    op.create_index('idx_log_lines_level', 'log_lines', ['level'])

    # 7. fix_attempts
    op.create_table(
        'fix_attempts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('incident_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.Text(), nullable=False),
        sa.Column('outcome', sa.String(length=32), nullable=False),
        sa.Column('by_engineer', sa.Integer(), nullable=True),
        sa.Column('at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.CheckConstraint("outcome IN ('worked', 'failed', 'partial')", name='chk_fix_outcome'),
        sa.ForeignKeyConstraint(['by_engineer'], ['engineers.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['incident_id'], ['incidents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_fix_attempts_incident', 'fix_attempts', ['incident_id'])
    op.create_index('idx_fix_attempts_outcome', 'fix_attempts', ['outcome'])

    # 8. agent_suggestions
    op.create_table(
        'agent_suggestions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('incident_id', sa.Integer(), nullable=False),
        sa.Column('hypothesis', sa.Text(), nullable=False),
        sa.Column('rank', sa.Integer(), nullable=False),
        sa.Column('memory_on', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('accepted', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.CheckConstraint('rank >= 1', name='chk_suggestion_rank'),
        sa.ForeignKeyConstraint(['incident_id'], ['incidents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_agent_suggestions_incident', 'agent_suggestions', ['incident_id'])

    # 9. replay_results
    op.create_table(
        'replay_results',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('run_id', sa.String(length=64), nullable=False),
        sa.Column('incident_id', sa.Integer(), nullable=False),
        sa.Column('memory_on', sa.Boolean(), nullable=False),
        sa.Column('top1_correct', sa.Boolean(), nullable=False),
        sa.Column('top3_correct', sa.Boolean(), nullable=False),
        sa.Column('minutes_to_hypothesis', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['incident_id'], ['incidents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('run_id', 'incident_id', 'memory_on', name='uq_run_incident_memory')
    )
    op.create_index('idx_replay_results_run', 'replay_results', ['run_id'])

    # Optional: postmortems
    op.create_table(
        'postmortems',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('incident_id', sa.Integer(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('timeline_json', sa.JSON(), nullable=False),
        sa.Column('preventative_actions', sa.JSON(), nullable=False),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('author_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['author_id'], ['engineers.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['incident_id'], ['incidents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('incident_id')
    )


def downgrade() -> None:
    op.drop_table('postmortems')
    op.drop_table('replay_results')
    op.drop_table('agent_suggestions')
    op.drop_table('fix_attempts')
    op.drop_table('log_lines')
    op.drop_table('incidents')
    op.drop_table('alerts')
    op.drop_table('deploys')
    op.drop_table('services')
    op.drop_table('engineers')
