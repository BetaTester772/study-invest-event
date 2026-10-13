"""notifications

참가자 알림(notifications)과 읽음 기록(notification_reads). participant_id가 NULL이면 전체 알림.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-13 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0010'
down_revision: Union[str, Sequence[str], None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'notifications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('participant_id', sa.Integer(), nullable=True),
        sa.Column('title', sa.String(length=120), nullable=False),
        sa.Column('body', sa.String(length=2000), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['participant_id'], ['participants.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_notifications_participant_id'), 'notifications', ['participant_id'], unique=False)
    op.create_index(op.f('ix_notifications_created_at'), 'notifications', ['created_at'], unique=False)
    op.create_table(
        'notification_reads',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('notification_id', sa.Integer(), nullable=False),
        sa.Column('participant_id', sa.Integer(), nullable=False),
        sa.Column('read_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['notification_id'], ['notifications.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['participant_id'], ['participants.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('notification_id', 'participant_id'),
    )
    op.create_index(op.f('ix_notification_reads_notification_id'), 'notification_reads', ['notification_id'], unique=False)
    op.create_index(op.f('ix_notification_reads_participant_id'), 'notification_reads', ['participant_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_notification_reads_participant_id'), table_name='notification_reads')
    op.drop_index(op.f('ix_notification_reads_notification_id'), table_name='notification_reads')
    op.drop_table('notification_reads')
    op.drop_index(op.f('ix_notifications_created_at'), table_name='notifications')
    op.drop_index(op.f('ix_notifications_participant_id'), table_name='notifications')
    op.drop_table('notifications')
