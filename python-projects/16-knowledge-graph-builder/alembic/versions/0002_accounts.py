"""accounts: users, sessions and an owner on every row

Every document, entity, fact, alias, suggestion and merge record gets an owner_id (NULL = the single-user data that
existed before accounts; the first account to register adopts it). Entity and alias names are unique per owner.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-15 15:15:33.922545
"""
from alembic import op
import sqlalchemy as sa


revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(length=40), nullable=False),
    sa.Column('display_name', sa.String(length=80), nullable=True),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('is_guest', sa.Boolean(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_users_username'), ['username'], unique=True)

    op.create_table('user_sessions',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('device', sa.String(length=160), nullable=True),
    sa.Column('ip_address', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('user_sessions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_user_sessions_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.add_column(sa.Column('owner_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_documents_owner_id'), ['owner_id'], unique=False)
        batch_op.create_foreign_key('fk_documents_owner', 'users', ['owner_id'], ['id'], ondelete='CASCADE')

    with op.batch_alter_table('entities', schema=None) as batch_op:
        batch_op.add_column(sa.Column('owner_id', sa.Integer(), nullable=True))
        batch_op.drop_constraint('uq_entity_key', type_='unique')
        batch_op.create_index(batch_op.f('ix_entities_owner_id'), ['owner_id'], unique=False)
        batch_op.create_unique_constraint('uq_entity_owner_key', ['owner_id', 'key'])
        batch_op.create_foreign_key('fk_entities_owner', 'users', ['owner_id'], ['id'], ondelete='CASCADE')

    # the baseline created UNIQUE(key) without a name; a naming convention lets batch mode find and drop it
    with op.batch_alter_table('entity_aliases', schema=None, naming_convention={"uq": "uq_%(table_name)s_%(column_0_name)s"}) as batch_op:
        batch_op.drop_constraint('uq_entity_aliases_key', type_='unique')
        batch_op.add_column(sa.Column('owner_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_entity_aliases_owner_id'), ['owner_id'], unique=False)
        batch_op.create_unique_constraint('uq_alias_owner_key', ['owner_id', 'key'])
        batch_op.create_foreign_key('fk_entity_aliases_owner', 'users', ['owner_id'], ['id'], ondelete='CASCADE')

    with op.batch_alter_table('facts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('owner_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_facts_owner_id'), ['owner_id'], unique=False)
        batch_op.create_foreign_key('fk_facts_owner', 'users', ['owner_id'], ['id'], ondelete='CASCADE')

    with op.batch_alter_table('merge_records', schema=None) as batch_op:
        batch_op.add_column(sa.Column('owner_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_merge_records_owner_id'), ['owner_id'], unique=False)
        batch_op.create_foreign_key('fk_merge_records_owner', 'users', ['owner_id'], ['id'], ondelete='CASCADE')

    with op.batch_alter_table('merge_suggestions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('owner_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_merge_suggestions_owner_id'), ['owner_id'], unique=False)
        batch_op.create_foreign_key('fk_merge_suggestions_owner', 'users', ['owner_id'], ['id'], ondelete='CASCADE')



def downgrade() -> None:
    with op.batch_alter_table('merge_suggestions', schema=None) as batch_op:
        batch_op.drop_constraint('fk_merge_suggestions_owner', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_merge_suggestions_owner_id'))
        batch_op.drop_column('owner_id')

    with op.batch_alter_table('merge_records', schema=None) as batch_op:
        batch_op.drop_constraint('fk_merge_records_owner', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_merge_records_owner_id'))
        batch_op.drop_column('owner_id')

    with op.batch_alter_table('facts', schema=None) as batch_op:
        batch_op.drop_constraint('fk_facts_owner', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_facts_owner_id'))
        batch_op.drop_column('owner_id')

    with op.batch_alter_table('entity_aliases', schema=None) as batch_op:
        batch_op.drop_constraint('fk_entity_aliases_owner', type_='foreignkey')
        batch_op.drop_constraint('uq_alias_owner_key', type_='unique')
        batch_op.drop_index(batch_op.f('ix_entity_aliases_owner_id'))
        batch_op.drop_column('owner_id')
        batch_op.create_unique_constraint('uq_entity_aliases_key', ['key'])

    with op.batch_alter_table('entities', schema=None) as batch_op:
        batch_op.drop_constraint('fk_entities_owner', type_='foreignkey')
        batch_op.drop_constraint('uq_entity_owner_key', type_='unique')
        batch_op.drop_index(batch_op.f('ix_entities_owner_id'))
        batch_op.create_unique_constraint('uq_entity_key', ['key'])
        batch_op.drop_column('owner_id')

    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.drop_constraint('fk_documents_owner', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_documents_owner_id'))
        batch_op.drop_column('owner_id')

    with op.batch_alter_table('user_sessions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_sessions_user_id'))

    op.drop_table('user_sessions')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_username'))

    op.drop_table('users')
