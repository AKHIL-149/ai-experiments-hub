"""jobs: the background job queue

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-16 13:39:53.843399
"""
from alembic import op
import sqlalchemy as sa


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('jobs',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=True),
    sa.Column('document_id', sa.String(length=32), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('max_attempts', sa.Integer(), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('cancel_requested', sa.Boolean(), nullable=False),
    sa.Column('worker', sa.String(length=80), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('heartbeat_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_jobs_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_jobs_document_id'), ['document_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_jobs_kind'), ['kind'], unique=False)
        batch_op.create_index(batch_op.f('ix_jobs_owner_id'), ['owner_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_jobs_status'), ['status'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_jobs_status'))
        batch_op.drop_index(batch_op.f('ix_jobs_owner_id'))
        batch_op.drop_index(batch_op.f('ix_jobs_kind'))
        batch_op.drop_index(batch_op.f('ix_jobs_document_id'))
        batch_op.drop_index(batch_op.f('ix_jobs_created_at'))

    op.drop_table('jobs')
