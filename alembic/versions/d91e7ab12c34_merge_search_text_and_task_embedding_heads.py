"""merge search_text and task_embedding heads

Revision ID: d91e7ab12c34
Revises: c4d9f6e1a2b3, 2c57fbe9ab9e
Create Date: 2026-03-01 00:20:00.000000

"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = 'd91e7ab12c34'
down_revision: Union[str, Sequence[str], None] = ('c4d9f6e1a2b3', '2c57fbe9ab9e')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Merge two heads; no schema change."""
    pass


def downgrade() -> None:
    """Unmerge two heads; no schema change."""
    pass
