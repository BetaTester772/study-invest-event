"""news article fields

호재·악재에 기사 부제·본문·바이라인(news_items.subtitle/body/byline)을 더한다. 제목만 있던
기존 기록은 NULL.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-04 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0008'
down_revision: Union[str, Sequence[str], None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('news_items', sa.Column('subtitle', sa.String(length=120), nullable=True))
    op.add_column('news_items', sa.Column('body', sa.String(length=600), nullable=True))
    op.add_column('news_items', sa.Column('byline', sa.String(length=40), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('news_items', 'byline')
    op.drop_column('news_items', 'body')
    op.drop_column('news_items', 'subtitle')
