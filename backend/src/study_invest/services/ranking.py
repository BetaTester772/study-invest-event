"""랭킹 (F-10). 시상 순위는 총자산 100% 기준(2026-09-24 결정), 닉네임만 공개.

참가자별 수익률은 각자의 투입 원금(시드 + 받은 인증 보상) 대비 손익이라 참가자마다 분모가
다르다(services.common.Valuation). 수익률 순위도 함께 낸다.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from fractions import Fraction

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import CertStatus, Participant, ParticipantStatus, StudyCertification
from .common import current_prices, rewards_received, valuate


@dataclass(frozen=True)
class RankingEntry:
    rank: int
    """총자산 순위(동점 공동)."""
    participant_id: int
    nickname: str
    total_assets: int
    principal: int
    profit: int
    return_rate: float
    return_rank: int
    """수익률 순위(높은 순, 동점 공동)."""
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


def shared_ranks(values: Sequence[int | Fraction]) -> list[int]:
    """내림차순으로 정렬된 값의 순위. 동점은 공동 순위(1, 2, 2, 4)."""
    ranks: list[int] = []
    for index, value in enumerate(values):
        ranks.append(ranks[-1] if index and values[index - 1] == value else index + 1)
    return ranks


def ranking(s: Session, today: date) -> tuple[date | None, list[RankingEntry]]:
    """총자산 순으로 정렬한 랭킹. 항목마다 수익률 순위를 함께 준다."""
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
    rewards = rewards_received(s)
    valuations = {p.id: valuate(p, prices, rewards.get(p.id, 0)) for p in participants}

    by_return = sorted(participants, key=lambda p: (-valuations[p.id].return_rate, p.id))
    return_ranks = dict(
        zip(
            (p.id for p in by_return),
            shared_ranks([valuations[p.id].return_rate for p in by_return]),
            strict=True,
        )
    )

    by_total = sorted(participants, key=lambda p: (-valuations[p.id].total_assets, p.id))
    total_ranks = shared_ranks([valuations[p.id].total_assets for p in by_total])
    entries: list[RankingEntry] = []
    for p, rank in zip(by_total, total_ranks, strict=True):
        v = valuations[p.id]
        days = approved.get(p.id, set())
        entries.append(
            RankingEntry(
                rank=rank,
                participant_id=p.id,
                nickname=p.nickname,
                total_assets=v.total_assets,
                principal=v.principal,
                profit=v.profit,
                return_rate=float(v.return_rate),
                return_rank=return_ranks[p.id],
                certified_days=len(days),
                streak=streak(days, today),
            )
        )
    return day, entries
