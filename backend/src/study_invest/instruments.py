"""종목 마스터 (01-data-model §1)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class InstrumentKind(StrEnum):
    STOCK = "stock"
    COIN = "coin"


@dataclass(frozen=True)
class Instrument:
    code: str
    """내부 종목 코드(공백 없음)."""
    name: str
    """종목명."""
    alias: str
    """규격서의 약칭 표기."""
    kind: InstrumentKind
    initial_price: int
    """이벤트 1일차 시작가(원)."""


SAMSU = Instrument("SAMSU", "삼수전자", "SAMSU", InstrumentKind.STOCK, 75_000)
SKLOW = Instrument("SKLOW", "SK로우닉스", "SKLOW", InstrumentKind.STOCK, 170_000)
MIRAE = Instrument("MIRAE", "미래대", "MIRAE DAI", InstrumentKind.STOCK, 40_000)
LB = Instrument("LB", "LB", "Life is Bad", InstrumentKind.STOCK, 14_000)
BYUNG = Instrument("BYUNG", "병더리움", "BYUNG", InstrumentKind.COIN, 250_000)

INSTRUMENTS: tuple[Instrument, ...] = (SAMSU, SKLOW, MIRAE, LB, BYUNG)
STOCKS: tuple[Instrument, ...] = tuple(i for i in INSTRUMENTS if i.kind is InstrumentKind.STOCK)
COIN: Instrument = BYUNG

BY_CODE: dict[str, Instrument] = {i.code: i for i in INSTRUMENTS}
