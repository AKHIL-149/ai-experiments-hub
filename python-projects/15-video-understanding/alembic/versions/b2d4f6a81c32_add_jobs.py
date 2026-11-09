"""add jobs: the queue for downloads and video analysis

Revision ID: b2d4f6a81c32
Revises: a1c3e5f70b21
Create Date: 2026-11-09 15:00:00

Safe to run on a database where the server already created the table (create_all in debug mode).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2d4f6a81c32'
down_revision: Union[str, None] = 'a1c3e5f70b21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if 'jobs' in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        'jobs',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('video_id', sa.Integer(), sa.ForeignKey('videos.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('payload', sa.JSON(), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_attempts', sa.Integer(), nullable=False, server_default='2'),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('cancel_requested', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('worker', sa.String(length=80), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('heartbeat_at', sa.DateTime(), nullable=True),
    )
    for column in ('kind', 'status', 'video_id', 'user_id', 'created_at'):
        op.create_index(f'ix_jobs_{column}', 'jobs', [column])


def downgrade() -> None:
    op.drop_table('jobs')
