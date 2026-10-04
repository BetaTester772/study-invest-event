"""앱 시계. 기본은 실제 KST 시각이고, 테스트·QA 서버에서는 빠르게 돌릴 수 있다."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from .params import KST


def system_now() -> datetime:
    return datetime.now(KST)


@dataclass(frozen=True)
class ScaledClock:
    """실제 시각 origin에 virtual_origin을 가리키고, 그 뒤로 scale배 빠르게 흐르는 시계.

    scale=24면 실제 1시간이 이벤트 하루다. 09:00 공시는 매시 22분 30초, 18:00 정산은 45분.
    공시·정산·장 운영·인증 마감·기록 시각이 모두 이 시계를 따른다.
    """

    origin: datetime
    virtual_origin: datetime
    scale: float
    source: Callable[[], datetime] = system_now

    def __post_init__(self) -> None:
        if not (math.isfinite(self.scale) and self.scale > 0):
            raise ValueError("clock scale must be a positive number")
        for at in (self.origin, self.virtual_origin):
            if at.tzinfo is None or at.utcoffset() is None:
                raise ValueError("timezone-aware datetime required")

    def __call__(self) -> datetime:
        return self.virtual_origin + (self.source() - self.origin) * self.scale

    def to_real(self, at: datetime) -> datetime:
        """이 시계가 at을 가리키는 실제 시각(KST)."""
        return (self.origin + (at - self.virtual_origin) / self.scale).astimezone(KST)


class OffsetClock:
    """base 시계에 오프셋을 더한 시계. QA가 "다음 단계"로 시각을 건너뛸 때 쓴다.

    jump_to 뒤에도 base처럼 계속 흐른다. 실제 시각이 필요한 곳은 real()로 풀어서 쓴다.
    """

    def __init__(self, base: Callable[[], datetime]) -> None:
        self.base = base
        self.offset = timedelta(0)

    def __call__(self) -> datetime:
        return self.base() + self.offset

    def jump_to(self, at: datetime) -> None:
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("timezone-aware datetime required")
        self.offset = at - self.base()

    def real(self) -> datetime:
        base = self.base
        return base.source() if isinstance(base, ScaledClock) else base()
