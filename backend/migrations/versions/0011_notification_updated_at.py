"""notification updated_at

관리자가 알림 제목·내용을 고칠 수 있게 마지막 수정 시각을 둔다.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-13 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0011'
down_revision: Union[str, Sequence[str], None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('notifications', sa.Column('updated_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('notifications', 'updated_at')
