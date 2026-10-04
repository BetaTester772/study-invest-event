"""이벤트 기간·운영일·장 운영 시간 (02-parameters §1, 04-trading §1, 05-certification §1)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from .params import EVENT_END, EVENT_START, KST, MARKET_CLOSE, MARKET_OPEN

BATCH_TIMES: tuple[time, ...] = (MARKET_OPEN, MARKET_CLOSE)
"""배치 시각: 09:00 공시, 18:00 정산."""


def to_kst(at: datetime) -> datetime:
    """시간대가 있는 datetime을 KST로 바꾼다. naive datetime은 받지 않는다."""
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("timezone-aware datetime required")
    return at.astimezone(KST)


def seconds_until_next_batch(at: datetime) -> float:
    """다음 배치 시각(09:00 또는 18:00 KST)까지 남은 초. 정각이면 다음 배치까지."""
    local = to_kst(at)
    upcoming = (
        datetime.combine(local.date() + timedelta(days=offset), t, KST)
        for offset in (0, 1)
        for t in BATCH_TIMES
    )
    return min((b - local).total_seconds() for b in upcoming if b > local)


@dataclass(frozen=True)
class EventCalendar:
    """운영일은 기간 내 모든 날짜다(주말 포함).

    가격 변동 회차 n(1부터)은 n번째 운영일 18:00 정산이며 n+1번째 운영일 시작가에 반영된다.
    마지막 운영일의 정산은 반영일이 없으므로 회차가 없다.

    end가 None이면 끝이 없다(QA 무제한 모드). 시작일 이후 모든 날이 운영일이고 회차도
    끝없이 이어진다.
    """

    start: date = EVENT_START
    end: date | None = EVENT_END

    def __post_init__(self) -> None:
        if self.end is not None and self.end < self.start:
            raise ValueError("end must not precede start")

    @property
    def unlimited(self) -> bool:
        return self.end is None

    @property
    def operating_days(self) -> tuple[date, ...]:
        if self.end is None:
            raise ValueError("unlimited calendar has no full list of days; use days_through()")
        return self.days_through(self.end)

    def days_through(self, last: date) -> tuple[date, ...]:
        """시작일부터 last까지의 운영일(기간 끝을 넘으면 끝에서 자른다)."""
        if self.end is not None:
            last = min(last, self.end)
        count = (last - self.start).days + 1
        return tuple(self.start + timedelta(days=i) for i in range(max(count, 0)))

    @property
    def total_rounds(self) -> int | None:
        """전체 가격 변동 회차 수. 무제한이면 None."""
        return None if self.end is None else (self.end - self.start).days

    def is_ended(self, day: date) -> bool:
        """day가 이벤트 종료 뒤인지. 무제한이면 항상 False."""
        return self.end is not None and day > self.end

    def is_operating_day(self, day: date) -> bool:
        return self.start <= day and not self.is_ended(day)

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

    def next_operating_time(self, at: datetime, t: time) -> datetime | None:
        """at 뒤에 처음 오는 운영일의 t 시각(KST). 이벤트 기간에 더 없으면 None."""
        local = to_kst(at)
        day = max(local.date() + timedelta(days=0 if local.time() < t else 1), self.start)
        return None if self.is_ended(day) else datetime.combine(day, t, KST)

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
