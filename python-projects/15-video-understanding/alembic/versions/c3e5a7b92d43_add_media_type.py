"""add videos.media_type: video or audio

Revision ID: c3e5a7b92d43
Revises: b2d4f6a81c32
Create Date: 2026-11-09 17:00:00

Existing rows are videos. Safe to run where the column already exists.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3e5a7b92d43'
down_revision: Union[str, None] = 'b2d4f6a81c32'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    columns = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('videos')}
    if 'media_type' not in columns:
        op.add_column('videos', sa.Column('media_type', sa.String(length=10), nullable=False, server_default='video'))


def downgrade() -> None:
    op.drop_column('videos', 'media_type')
