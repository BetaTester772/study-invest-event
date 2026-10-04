"""code requester

인증 코드를 요청한 로그인 참가자(email_verifications.requested_by)를 남긴다. 로그인한 요청은
주소를 바꿔 가며 요청해도 계정마다 재요청 대기(60초)·하루 한도(5통)를 센다. 기존 기록은 NULL.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-04 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('email_verifications', sa.Column('requested_by', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_email_verifications_requested_by'), 'email_verifications', ['requested_by'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_email_verifications_requested_by'), table_name='email_verifications')
    op.drop_column('email_verifications', 'requested_by')
