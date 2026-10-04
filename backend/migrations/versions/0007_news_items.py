"""news items

호재·악재(news_items). 운영일·종목당 1건. 전날 정산 때 무작위로 생성되거나 관리자가 쓴다.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-04 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0007'
down_revision: Union[str, Sequence[str], None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'news_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('day', sa.Date(), nullable=False),
        sa.Column('code', sa.String(length=16), nullable=False),
        sa.Column('kind', sa.Enum('good', 'bad', name='newskind', native_enum=False, length=32), nullable=False),
        sa.Column('rate', sa.Float(), nullable=False),
        sa.Column('headline', sa.String(length=120), nullable=False),
        sa.Column('source', sa.Enum('random', 'manual', name='newssource', native_enum=False, length=32), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('day', 'code'),
    )
    op.create_index(op.f('ix_news_items_day'), 'news_items', ['day'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_news_items_day'), table_name='news_items')
    op.drop_table('news_items')
