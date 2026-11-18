"""conflicts: facts that cannot both be true, and how relation words behave

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-17 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('conflicts',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=True),
    sa.Column('kind', sa.String(length=30), nullable=False),
    sa.Column('severity', sa.String(length=10), nullable=False),
    sa.Column('fact_a_id', sa.String(length=32), nullable=False),
    sa.Column('fact_b_id', sa.String(length=32), nullable=False),
    sa.Column('reasons', sa.JSON(), nullable=False),
    sa.Column('llm_verdict', sa.String(length=10), nullable=True),
    sa.Column('status', sa.Enum('OPEN', 'RESOLVED', 'DISMISSED', name='conflictstatus'), nullable=False),
    sa.Column('resolution', sa.String(length=20), nullable=True),
    sa.Column('data', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['fact_a_id'], ['facts.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['fact_b_id'], ['facts.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('fact_a_id', 'fact_b_id', name='uq_conflict_pair')
    )
    with op.batch_alter_table('conflicts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_conflicts_fact_a_id'), ['fact_a_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_conflicts_fact_b_id'), ['fact_b_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_conflicts_owner_id'), ['owner_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_conflicts_status'), ['status'], unique=False)

    op.create_table('predicate_kinds',
    sa.Column('key', sa.String(length=80), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('model', sa.String(length=120), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('key')
    )


def downgrade() -> None:
    op.drop_table('predicate_kinds')
    with op.batch_alter_table('conflicts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_conflicts_status'))
        batch_op.drop_index(batch_op.f('ix_conflicts_owner_id'))
        batch_op.drop_index(batch_op.f('ix_conflicts_fact_b_id'))
        batch_op.drop_index(batch_op.f('ix_conflicts_fact_a_id'))
    op.drop_table('conflicts')
    sa.Enum(name='conflictstatus').drop(op.get_bind(), checkfirst=True)
