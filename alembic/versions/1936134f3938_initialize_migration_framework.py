"""initialize migration framework

Revision ID: 1936134f3938
Revises:
Create Date: 2026-09-12 04:35:05.100180

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "1936134f3938"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
