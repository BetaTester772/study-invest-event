"""이벤트 기간·운영일·장 운영 시간 (02-parameters §1, 04-trading §1, 05-certification §1)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from .params import EVENT_END, EVENT_START, KST, MARKET_CLOSE, MARKET_OPEN


def to_kst(at: datetime) -> datetime:
    """시간대가 있는 datetime을 KST로 바꾼다. naive datetime은 받지 않는다."""
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("timezone-aware datetime required")
    return at.astimezone(KST)


@dataclass(frozen=True)
class EventCalendar:
    """운영일은 기간 내 모든 날짜다(주말 포함).

    가격 변동 회차 n(1부터)은 n번째 운영일 18:00 정산이며 n+1번째 운영일 시작가에 반영된다.
    마지막 운영일의 정산은 반영일이 없으므로 회차가 없다.
    """

    start: date = EVENT_START
    end: date = EVENT_END

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError("end must not precede start")

    @property
    def operating_days(self) -> tuple[date, ...]:
        count = (self.end - self.start).days + 1
        return tuple(self.start + timedelta(days=i) for i in range(count))

    @property
    def total_rounds(self) -> int:
        return len(self.operating_days) - 1

    def is_operating_day(self, day: date) -> bool:
        return self.start <= day <= self.end

    def next_operating_day(self, day: date) -> date | None:
        nxt = day + timedelta(days=1)
        return nxt if self.is_operating_day(nxt) else None

    def previous_operating_day(self, day: date) -> date | None:
        prev = day - timedelta(days=1)
        return prev if self.is_operating_day(prev) else None

    def round_of(self, day: date) -> int | None:
        """day 18:00 정산의 가격 변동 회차. 반영일이 없으면 None."""
        if not self.is_operating_day(day) or day == self.end:
            return None
        return (day - self.start).days + 1

    def is_market_open(self, at: datetime) -> bool:
        """주문 접수 가능 여부. 접수 시간은 [09:00, 18:00)이며 18:00 정각부터는 마감이다."""
        local = to_kst(at)
        return self.is_operating_day(local.date()) and MARKET_OPEN <= local.time() < MARKET_CLOSE

    def certification_target_date(self, at: datetime, cutoff: time) -> date:
        """인증 접수 시각을 집계 대상 일자로 바꾼다.

        cutoff가 가리키는 분(分)까지는 당일로, 그 이후는 다음 날짜로 집계한다.
        """
        local = to_kst(at)
        if (local.hour, local.minute) <= (cutoff.hour, cutoff.minute):
            return local.date()
        return local.date() + timedelta(days=1)
