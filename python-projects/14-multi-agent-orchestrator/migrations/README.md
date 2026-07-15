# Database Migrations

This directory contains Alembic database migrations for the Multi-Agent Task Orchestrator.

## Quick Start

### Running Migrations

```bash
# Upgrade to latest version
alembic upgrade head

# Downgrade one version
alembic downgrade -1

# Show current version
alembic current

# Show migration history
alembic history
```

## Setup

### First Time Setup

1. **Configure Database URL**

   Edit `alembic.ini` or set environment variable:
   ```bash
   export DATABASE_URL="postgresql://user:password@localhost:5432/multi_agent_orchestrator"
   ```

2. **Run Initial Migration**
   ```bash
   alembic upgrade head
   ```

   This will create all tables including:
   - `workflows` - Workflow definitions and execution metadata
   - `workflow_steps` - Individual steps within workflows
   - All other application tables

## Migration Files

### Current Migrations

**001_add_workflow_models.py** (Initial)
- Creates `workflows` table
- Creates `workflow_steps` table
- Adds PostgreSQL enum types: `workflowstatus`, `workflowtype`

## Creating New Migrations

### Auto-generate Migration

Alembic can automatically detect model changes:

```bash
# Generate migration from model changes
alembic revision --autogenerate -m "Add new field to Task model"
```

### Manual Migration

For complex changes, create manual migration:

```bash
# Create empty migration file
alembic revision -m "Add custom indexes"
```

Then edit the generated file in `migrations/versions/`.

### Migration Template

```python
"""Description of changes

Revision ID: xxx
Revises: yyy
Create Date: 2026-07-14

"""
from alembic import op
import sqlalchemy as sa

revision = 'xxx'
down_revision = 'yyy'

def upgrade() -> None:
    # Add your upgrade commands here
    op.add_column('table_name', sa.Column('new_column', sa.String(50)))

def downgrade() -> None:
    # Add your downgrade commands here
    op.drop_column('table_name', 'new_column')
```

## Common Operations

### Add Column

```python
def upgrade():
    op.add_column('workflows',
        sa.Column('priority', sa.Integer(), nullable=True)
    )

def downgrade():
    op.drop_column('workflows', 'priority')
```

### Add Index

```python
def upgrade():
    op.create_index(
        'ix_workflows_created_at',
        'workflows',
        ['created_at']
    )

def downgrade():
    op.drop_index('ix_workflows_created_at')
```

### Add Foreign Key

```python
def upgrade():
    op.add_column('workflows',
        sa.Column('owner_id', sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        'fk_workflows_owner_id',
        'workflows', 'users',
        ['owner_id'], ['id']
    )

def downgrade():
    op.drop_constraint('fk_workflows_owner_id', 'workflows')
    op.drop_column('workflows', 'owner_id')
```

### Modify Column

```python
def upgrade():
    op.alter_column('workflows', 'name',
        existing_type=sa.String(100),
        type_=sa.String(255),
        existing_nullable=False
    )

def downgrade():
    op.alter_column('workflows', 'name',
        existing_type=sa.String(255),
        type_=sa.String(100),
        existing_nullable=False
    )
```

## Alembic Commands Reference

### Basic Commands

```bash
# Upgrade to latest
alembic upgrade head

# Upgrade to specific revision
alembic upgrade abc123

# Upgrade one version
alembic upgrade +1

# Downgrade to specific revision
alembic downgrade abc123

# Downgrade one version
alembic downgrade -1

# Downgrade to base (remove all)
alembic downgrade base
```

### Information Commands

```bash
# Show current revision
alembic current

# Show migration history
alembic history

# Show detailed history
alembic history --verbose

# Show pending migrations
alembic show head
```

### Revision Commands

```bash
# Create new migration (auto-detect changes)
alembic revision --autogenerate -m "Description"

# Create empty migration
alembic revision -m "Description"

# Create migration with specific revision ID
alembic revision -m "Description" --rev-id "001"
```

## Best Practices

### 1. Always Test Migrations

Test both upgrade and downgrade:

```bash
# Test upgrade
alembic upgrade head

# Test downgrade
alembic downgrade -1

# Test upgrade again
alembic upgrade head
```

### 2. Write Reversible Migrations

Always implement both `upgrade()` and `downgrade()`:

```python
def upgrade() -> None:
    """Apply changes"""
    op.add_column('table', sa.Column('new_col', sa.String(50)))

def downgrade() -> None:
    """Revert changes"""
    op.drop_column('table', 'new_col')
```

### 3. Use Meaningful Messages

```bash
# Good
alembic revision -m "Add workflow priority and tags"

# Bad
alembic revision -m "Update"
```

### 4. Review Auto-generated Migrations

Always review and test auto-generated migrations before applying:

```bash
alembic revision --autogenerate -m "Auto-detected changes"
# Review migrations/versions/xxx_auto_detected_changes.py
# Test the migration
alembic upgrade head
```

### 5. Data Migrations

For migrations that modify data:

```python
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column

def upgrade():
    # Schema change
    op.add_column('workflows', sa.Column('status_v2', sa.String(50)))

    # Data migration
    workflows = table('workflows',
        column('status', sa.String),
        column('status_v2', sa.String)
    )

    op.execute(
        workflows.update().values(status_v2=workflows.c.status)
    )

    # Drop old column
    op.drop_column('workflows', 'status')

    # Rename new column
    op.alter_column('workflows', 'status_v2', new_column_name='status')
```

## Troubleshooting

### "Target database is not up to date"

```bash
# Check current version
alembic current

# Upgrade to head
alembic upgrade head
```

### "Can't locate revision identified by 'xxx'"

The migration file might be missing. Check `migrations/versions/` directory.

### "Relation already exists"

The table might already exist in the database. Options:

1. Stamp the database at current migration:
   ```bash
   alembic stamp head
   ```

2. Or drop the table and re-run migration:
   ```bash
   # In psql or your DB tool
   DROP TABLE workflows;
   DROP TABLE workflow_steps;

   # Then run migration
   alembic upgrade head
   ```

### "No module named 'src.models'"

Ensure you're running from the project root directory:

```bash
cd /path/to/multi-agent-orchestrator
alembic upgrade head
```

## Database Schema Diagram

Current schema after migrations:

```
workflows
├── id (PK)
├── name
├── description
├── workflow_type (ENUM)
├── status (ENUM)
├── definition (JSON)
├── started_at
├── completed_at
├── created_at
├── updated_at
├── created_by (FK -> users.id)
├── extra_metadata (JSON)
├── result (JSON)
└── error_message

workflow_steps
├── id (PK)
├── workflow_id (FK -> workflows.id)
├── step_name
├── step_type
├── step_order
├── dependencies (JSON)
├── config (JSON)
├── status
├── started_at
├── completed_at
├── result (JSON)
├── error_message
├── created_at
└── updated_at
```

## Production Deployment

### Pre-deployment Checklist

- [ ] Review all pending migrations
- [ ] Test migrations in staging environment
- [ ] Backup production database
- [ ] Schedule maintenance window if needed
- [ ] Prepare rollback plan

### Deployment Steps

```bash
# 1. Backup database
pg_dump multi_agent_orchestrator > backup_$(date +%Y%m%d_%H%M%S).sql

# 2. Run migrations
alembic upgrade head

# 3. Verify migration succeeded
alembic current

# 4. Test application
curl http://localhost:8001/api/health
```

### Rollback Procedure

```bash
# 1. Stop application
systemctl stop orchestrator

# 2. Downgrade migration
alembic downgrade -1

# 3. Restore from backup if needed
psql multi_agent_orchestrator < backup_20260714_120000.sql

# 4. Restart application
systemctl start orchestrator
```

## CI/CD Integration

Add to your deployment pipeline:

```yaml
# .github/workflows/deploy.yml
- name: Run Database Migrations
  run: |
    pip install alembic
    alembic upgrade head
  env:
    DATABASE_URL: ${{ secrets.DATABASE_URL }}
```

## Resources

- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [SQLAlchemy Core](https://docs.sqlalchemy.org/en/20/core/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)

## Support

For issues with migrations:
1. Check the troubleshooting section above
2. Review migration logs: `alembic.log`
3. Consult database logs
4. Open an issue with migration details
