"""랭킹 (F-10). 시상 순위는 총자산 100% 기준(2026-09-24 결정), 닉네임만 공개."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from fractions import Fraction

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import CertStatus, Participant, ParticipantStatus, StudyCertification
from ..params import INITIAL_CASH
from .common import current_prices, total_assets


@dataclass(frozen=True)
class RankingEntry:
    rank: int
    participant_id: int
    nickname: str
    total_assets: int
    return_rate: float
    certified_days: int
    streak: int


def streak(approved_days: set[date], today: date) -> int:
    """인증 연속일수. 오늘 승인분이 없으면 어제부터 거슬러 센다."""
    day = today if today in approved_days else today - timedelta(days=1)
    count = 0
    while day in approved_days:
        count += 1
        day -= timedelta(days=1)
    return count


def ranking(s: Session, today: date) -> tuple[date | None, list[RankingEntry]]:
    day, prices = current_prices(s)
    participants = s.scalars(
        select(Participant)
        .where(Participant.status != ParticipantStatus.DISQUALIFIED)
        .options(selectinload(Participant.holdings))
    ).all()
    approved: dict[int, set[date]] = {}
    for pid, target in s.execute(
        select(StudyCertification.participant_id, StudyCertification.target_date).where(
            StudyCertification.status == CertStatus.APPROVED
        )
    ):
        approved.setdefault(pid, set()).add(target)

    rows = sorted(
        ((p, total_assets(p, prices)) for p in participants),
        key=lambda pair: (-pair[1], pair[0].id),
    )
    entries: list[RankingEntry] = []
    for index, (p, total) in enumerate(rows):
        # 동점은 공동 순위(1, 2, 2, 4)
        rank = entries[-1].rank if entries and entries[-1].total_assets == total else index + 1
        days = approved.get(p.id, set())
        entries.append(
            RankingEntry(
                rank=rank,
                participant_id=p.id,
                nickname=p.nickname,
                total_assets=total,
                return_rate=float(Fraction(total - INITIAL_CASH, INITIAL_CASH)),
                certified_days=len(days),
                streak=streak(days, today),
            )
        )
    return day, entries
