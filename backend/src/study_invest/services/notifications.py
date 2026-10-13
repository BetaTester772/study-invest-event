"""참가자 알림: 관리자가 쓰고(전체 또는 한 사람), 참가자는 읽음·안 읽음을 구분해 본다."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import ColumnElement, delete, func, or_, select
from sqlalchemy.orm import Session

from ..models import Notification, NotificationRead, Participant
from .common import DomainError, audit, lock_participant


@dataclass(frozen=True)
class InboxItem:
    notification: Notification
    read_at: datetime | None


def _visible_to(participant_id: int) -> ColumnElement[bool]:
    return or_(Notification.participant_id.is_(None), Notification.participant_id == participant_id)


def inbox(s: Session, participant_id: int) -> list[InboxItem]:
    """참가자에게 보이는 알림(전체 + 본인), 최신부터. 읽은 시각을 함께 돌려준다."""
    rows = s.execute(
        select(Notification, NotificationRead.read_at)
        .outerjoin(
            NotificationRead,
            (NotificationRead.notification_id == Notification.id)
            & (NotificationRead.participant_id == participant_id),
        )
        .where(_visible_to(participant_id))
        .order_by(Notification.created_at.desc(), Notification.id.desc())
    )
    return [InboxItem(n, read_at) for n, read_at in rows]


def mark_read(s: Session, participant_id: int, ids: Iterable[int] | None, now: datetime) -> int:
    """알림을 읽음으로 표시한다. ids가 None이면 보이는 알림 전부. 이미 읽은 것은 건너뛴다.

    참가자 행을 잠가 같은 참가자의 동시 요청(두 번 누르기)이 같은 읽음 행을 두 번 넣지 않게 한다.
    알림 행은 공유 잠금(FOR SHARE)으로 읽어, 진행 중인 삭제(remove의 FOR UPDATE)가 끝난 뒤에
    판단하고 이 트랜잭션이 끝날 때까지 삭제가 끼어들지 못하게 한다.
    돌려주는 값은 새로 읽음 처리한 개수.
    """
    lock_participant(s, participant_id)
    query = select(Notification.id).where(_visible_to(participant_id)).with_for_update(read=True)
    if ids is not None:
        wanted = set(ids)
        if not wanted:
            return 0
        query = query.where(Notification.id.in_(wanted))
    visible = set(s.scalars(query))
    already = set(
        s.scalars(
            select(NotificationRead.notification_id).where(
                NotificationRead.participant_id == participant_id,
                NotificationRead.notification_id.in_(visible),
            )
        )
    )
    new = sorted(visible - already)
    for nid in new:
        s.add(NotificationRead(notification_id=nid, participant_id=participant_id, read_at=now))
    s.flush()
    return len(new)


def create(
    s: Session, title: str, body: str, participant_id: int | None, now: datetime
) -> Notification:
    title, body = title.strip(), body.strip()
    if not title or not body:
        raise DomainError("INVALID_NOTIFICATION", "제목과 내용을 모두 적어 주세요.", 422)
    if participant_id is not None and s.get(Participant, participant_id) is None:
        raise DomainError(
            "NOT_FOUND",
            "참가자를 찾을 수 없습니다.",
            404,
            context={"participant_id": participant_id},
        )
    item = Notification(participant_id=participant_id, title=title, body=body, created_at=now)
    s.add(item)
    s.flush()
    audit(
        s,
        now,
        "admin",
        "notification.create",
        notification_id=item.id,
        participant_id=participant_id,
        title=title,
    )
    return item


def remove(s: Session, notification_id: int, now: datetime) -> None:
    # 배타 잠금: 진행 중인 읽음 처리(mark_read의 FOR SHARE)가 끝난 뒤 지우고, 그동안 새 읽음 행이
    # 끼어들지 못하게 한다(읽음 행 FK 위반 → 500 방지).
    item = s.scalars(
        select(Notification).where(Notification.id == notification_id).with_for_update()
    ).one_or_none()
    if item is None:
        raise DomainError("NOT_FOUND", "알림을 찾을 수 없습니다.", 404)
    s.execute(delete(NotificationRead).where(NotificationRead.notification_id == notification_id))
    s.delete(item)
    audit(s, now, "admin", "notification.delete", notification_id=notification_id, title=item.title)


@dataclass(frozen=True)
class AdminItem:
    notification: Notification
    nickname: str | None
    """받는 참가자 닉네임. 전체 알림이면 None."""
    read_count: int
    recipients: int
    """받는 사람 수(전체 알림이면 지금 참가자 수)."""


def admin_list(s: Session) -> list[AdminItem]:
    reads = dict(
        s.execute(
            select(NotificationRead.notification_id, func.count()).group_by(
                NotificationRead.notification_id
            )
        ).all()
    )
    everyone = s.scalar(select(func.count()).select_from(Participant)) or 0
    rows = s.execute(
        select(Notification, Participant.nickname)
        .outerjoin(Participant, Participant.id == Notification.participant_id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
    )
    return [
        AdminItem(n, nick, int(reads.get(n.id, 0)), everyone if n.participant_id is None else 1)
        for n, nick in rows
    ]


def update(
    s: Session,
    notification_id: int,
    title: str | None,
    body: str | None,
    reset_reads: bool,
    now: datetime,
) -> Notification:
    """제목·내용을 고친다(받는 사람은 바꾸지 않는다). reset_reads면 읽음 기록을 지워 모두에게 다시
    안 읽은 알림으로 보인다. 읽음 처리와 겹치지 않게 삭제와 같은 배타 잠금을 쓴다."""
    item = s.scalars(
        select(Notification).where(Notification.id == notification_id).with_for_update()
    ).one_or_none()
    if item is None:
        raise DomainError("NOT_FOUND", "알림을 찾을 수 없습니다.", 404)
    before = {"title": item.title, "body": item.body}
    if title is not None:
        if not title.strip():
            raise DomainError("INVALID_NOTIFICATION", "제목을 비울 수 없습니다.", 422)
        item.title = title.strip()
    if body is not None:
        if not body.strip():
            raise DomainError("INVALID_NOTIFICATION", "내용을 비울 수 없습니다.", 422)
        item.body = body.strip()
    changed = before != {"title": item.title, "body": item.body}
    cleared = 0
    if reset_reads:
        mine = NotificationRead.notification_id == notification_id
        cleared = s.scalar(select(func.count()).select_from(NotificationRead).where(mine)) or 0
        s.execute(delete(NotificationRead).where(mine))
    if changed:
        item.updated_at = now
    s.flush()
    audit(
        s,
        now,
        "admin",
        "notification.update",
        notification_id=notification_id,
        title_before=before["title"],
        title_after=item.title,
        body_changed=before["body"] != item.body,
        reads_cleared=cleared,
    )
    return item


@dataclass(frozen=True)
class Reader:
    participant_id: int
    nickname: str
    read_at: datetime | None


def readers(s: Session, item: Notification) -> list[Reader]:
    """받는 사람별 읽은 시각. 전체 알림이면 모든 참가자(안 읽었으면 read_at None).
    읽은 사람을 먼저(읽은 순서대로), 그다음 안 읽은 사람을 참가자 번호 순으로."""
    query = select(Participant.id, Participant.nickname, NotificationRead.read_at).outerjoin(
        NotificationRead,
        (NotificationRead.participant_id == Participant.id)
        & (NotificationRead.notification_id == item.id),
    )
    if item.participant_id is not None:
        query = query.where(Participant.id == item.participant_id)
    rows = [Reader(pid, nick, read_at) for pid, nick, read_at in s.execute(query)]
    read = sorted(
        (r for r in rows if r.read_at is not None), key=lambda r: (r.read_at, r.participant_id)
    )
    unread = sorted((r for r in rows if r.read_at is None), key=lambda r: r.participant_id)
    return read + unread
