"""add accounts: users, user_sessions and videos.user_id

Revision ID: a1c3e5f70b21
Revises: 70098992c1c0
Create Date: 2026-11-09 11:00:00

Videos that exist before this migration keep user_id NULL; the first account that is created adopts them.
Safe to run on a database where the server already created the tables (create_all in debug mode).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1c3e5f70b21'
down_revision: Union[str, None] = '70098992c1c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    tables = set(insp.get_table_names())

    if 'users' not in tables:
        op.create_table(
            'users',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('username', sa.String(length=40), nullable=False),
            sa.Column('display_name', sa.String(length=80), nullable=True),
            sa.Column('password_hash', sa.String(length=255), nullable=False),
            sa.Column('is_guest', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('is_admin', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('last_login_at', sa.DateTime(), nullable=True),
        )
        op.create_index('ix_users_id', 'users', ['id'])
        op.create_index('ix_users_username', 'users', ['username'], unique=True)

    if 'user_sessions' not in tables:
        op.create_table(
            'user_sessions',
            sa.Column('id', sa.String(length=64), primary_key=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('device', sa.String(length=160), nullable=True),
            sa.Column('ip_address', sa.String(length=64), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('last_seen_at', sa.DateTime(), nullable=False),
            sa.Column('expires_at', sa.DateTime(), nullable=False),
            sa.Column('revoked_at', sa.DateTime(), nullable=True),
        )
        op.create_index('ix_user_sessions_user_id', 'user_sessions', ['user_id'])

    if 'user_id' not in {c['name'] for c in insp.get_columns('videos')}:
        op.add_column('videos', sa.Column('user_id', sa.Integer(), nullable=True))
        op.create_foreign_key('fk_videos_user_id', 'videos', 'users', ['user_id'], ['id'], ondelete='CASCADE')
        op.create_index('ix_videos_user_id', 'videos', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_videos_user_id', table_name='videos')
    op.drop_constraint('fk_videos_user_id', 'videos', type_='foreignkey')
    op.drop_column('videos', 'user_id')
    op.drop_table('user_sessions')
    op.drop_table('users')
