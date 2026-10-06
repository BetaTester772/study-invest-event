"""certification resubmit after reject

반려된 인증은 같은 날짜에 다시 낼 수 있도록 (participant_id, target_date) 유일 제약을
반려되지 않은 행에만 적용하는 부분 유일 인덱스로 바꾼다.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-06 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0009'
down_revision: Union[str, Sequence[str], None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX = 'uq_certifications_active_day'
WHERE = sa.text("status != 'rejected'")


def _old_unique_name() -> str | None:
    insp = sa.inspect(op.get_bind())
    for uc in insp.get_unique_constraints('certifications'):
        if uc['column_names'] == ['participant_id', 'target_date']:
            return uc['name']
    return None


def upgrade() -> None:
    """Upgrade schema."""
    name = _old_unique_name()
    if name is not None:
        op.drop_constraint(name, 'certifications', type_='unique')
    op.create_index(
        INDEX, 'certifications', ['participant_id', 'target_date'], unique=True,
        sqlite_where=WHERE, postgresql_where=WHERE,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(INDEX, table_name='certifications')
    op.create_unique_constraint(
        'certifications_participant_id_target_date_key', 'certifications',
        ['participant_id', 'target_date'],
    )
