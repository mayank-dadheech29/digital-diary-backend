"""add_task_embedding

Revision ID: 2c57fbe9ab9e
Revises: 8be6196bd921
Create Date: 2026-02-28 19:51:34.335730

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2c57fbe9ab9e'
down_revision: Union[str, Sequence[str], None] = '8be6196bd921'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    from pgvector.sqlalchemy import Vector
    op.add_column('tasks', sa.Column('embedding', Vector(dim=3072), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('tasks', 'embedding')
