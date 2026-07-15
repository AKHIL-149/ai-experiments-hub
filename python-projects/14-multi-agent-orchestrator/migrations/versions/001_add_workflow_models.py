"""Add Workflow and WorkflowStep models

Revision ID: 001
Revises:
Create Date: 2026-07-14 21:40:00.000000

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
    """
    Add workflows and workflow_steps tables
    """
    # Detect database type
    bind = op.get_bind()
    is_postgresql = bind.dialect.name == 'postgresql'

    # Create enum types for PostgreSQL only
    if is_postgresql:
        workflow_status = postgresql.ENUM(
            'PENDING', 'RUNNING', 'PAUSED', 'COMPLETED', 'FAILED', 'CANCELLED',
            name='workflowstatus',
            create_type=False
        )
        workflow_type = postgresql.ENUM(
            'SIMPLE', 'DEFAULT', 'CUSTOM', 'DAG',
            name='workflowtype',
            create_type=False
        )
        # Create enums for PostgreSQL
        op.execute("CREATE TYPE IF NOT EXISTS workflowstatus AS ENUM ('PENDING', 'RUNNING', 'PAUSED', 'COMPLETED', 'FAILED', 'CANCELLED')")
        op.execute("CREATE TYPE IF NOT EXISTS workflowtype AS ENUM ('SIMPLE', 'DEFAULT', 'CUSTOM', 'DAG')")
    else:
        # For SQLite and other databases, use String columns
        workflow_status = sa.String(50)
        workflow_type = sa.String(50)

    # Create workflows table
    op.create_table(
        'workflows',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('workflow_type', workflow_type, nullable=False),
        sa.Column('status', workflow_status, nullable=False),
        sa.Column('definition', sa.JSON(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('extra_metadata', sa.JSON(), nullable=True),
        sa.Column('result', sa.JSON(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_workflows_name'), 'workflows', ['name'], unique=False)
    op.create_index(op.f('ix_workflows_status'), 'workflows', ['status'], unique=False)

    # Create workflow_steps table
    op.create_table(
        'workflow_steps',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('workflow_id', sa.Integer(), nullable=False),
        sa.Column('step_name', sa.String(length=255), nullable=False),
        sa.Column('step_type', sa.String(length=100), nullable=False),
        sa.Column('step_order', sa.Integer(), nullable=False),
        sa.Column('dependencies', sa.JSON(), nullable=True),
        sa.Column('config', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('result', sa.JSON(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['workflow_id'], ['workflows.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_workflow_steps_workflow_id'), 'workflow_steps', ['workflow_id'], unique=False)


def downgrade() -> None:
    """
    Remove workflows and workflow_steps tables
    """
    # Drop tables
    op.drop_index(op.f('ix_workflow_steps_workflow_id'), table_name='workflow_steps')
    op.drop_table('workflow_steps')

    op.drop_index(op.f('ix_workflows_status'), table_name='workflows')
    op.drop_index(op.f('ix_workflows_name'), table_name='workflows')
    op.drop_table('workflows')

    # Drop enum types if using PostgreSQL
    bind = op.get_bind()
    is_postgresql = bind.dialect.name == 'postgresql'
    if is_postgresql:
        op.execute("DROP TYPE IF EXISTS workflowstatus")
        op.execute("DROP TYPE IF EXISTS workflowtype")
