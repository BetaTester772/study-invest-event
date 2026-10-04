"""profile, password reset, admin verification

참가자 이름·학번(유니크)·학과를 추가한다. 기존 참가자는 비어 있다.
인증 코드에 용도(purpose: verify·reset_password)를 붙인다. 기존 코드는 verify.
email_verified_at을 verified_at으로 바꾸고(관리자 인증도 같은 칸), 인증 방법(verified_via)을 둔다.
이미 메일로 인증된 참가자는 verified_via = email.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-04 08:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('email_verifications', sa.Column('purpose', sa.Enum('verify', 'reset_password', name='codepurpose', native_enum=False, length=32), server_default='verify', nullable=False))
    op.alter_column('participants', 'email_verified_at', new_column_name='verified_at')
    op.add_column('participants', sa.Column('verified_via', sa.Enum('email', 'admin', name='verifymethod', native_enum=False, length=32), nullable=True))
    op.execute("UPDATE participants SET verified_via = 'email' WHERE verified_at IS NOT NULL")
    op.add_column('participants', sa.Column('name', sa.String(length=30), nullable=True))
    op.add_column('participants', sa.Column('student_id', sa.String(length=16), nullable=True))
    op.add_column('participants', sa.Column('department', sa.String(length=50), nullable=True))
    op.create_unique_constraint('participants_student_id_key', 'participants', ['student_id'])


def downgrade() -> None:
    """Downgrade schema. 관리자 인증은 메일 인증 시각으로 남는다(0003에는 구분이 없다)."""
    op.drop_constraint('participants_student_id_key', 'participants', type_='unique')
    op.drop_column('participants', 'department')
    op.drop_column('participants', 'student_id')
    op.drop_column('participants', 'name')
    op.drop_column('participants', 'verified_via')
    op.alter_column('participants', 'verified_at', new_column_name='email_verified_at')
    op.drop_column('email_verifications', 'purpose')
