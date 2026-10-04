"""email delivery address

인증·재설정 코드를 보낼 주소(participants.email_address)를 1인 1계정 키(email)와 따로 둔다.
skku.edu와 g.skku.edu는 같은 ID여도 메일함이 다를 수 있어서, 입력한 도메인 그대로 보낸다.
기존 참가자는 저장된 키(ID@g.skku.edu)로 채운다.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-04 08:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('participants', sa.Column('email_address', sa.String(length=254), nullable=True))
    op.execute("UPDATE participants SET email_address = email WHERE email IS NOT NULL")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('participants', 'email_address')
