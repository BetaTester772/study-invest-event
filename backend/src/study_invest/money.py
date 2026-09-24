"""금액 계산 유틸리티.

규격 표기 규칙: 통화 단위는 원(KRW), 모든 가격·금액은 정수 원, 별도 명시가 없으면
가격은 10원 단위 반올림(00-overview / README 표기 규칙).
"""

from __future__ import annotations

import math
from fractions import Fraction

PRICE_UNIT = 10
"""가격 반올림 단위(원)."""

Number = int | float | Fraction


def round_half_up(value: Number, unit: int = PRICE_UNIT) -> int:
    """value를 unit 단위로 반올림한다. 정확히 절반이면 0에서 먼 쪽으로 올린다.

    파이썬 내장 round()는 은행가 반올림(짝수 쪽)이므로 가격 계산에 쓰지 않는다.
    float 입력은 이진 표현 그대로 Fraction으로 바꿔 계산한다.
    """
    if unit <= 0:
        raise ValueError("unit must be positive")
    q = Fraction(value) / unit
    half = Fraction(1, 2)
    n = math.floor(q + half) if q >= 0 else -math.floor(-q + half)
    return n * unit


def exact(value: Number) -> Fraction:
    """파라미터 값(예: 0.30)을 사람이 적은 십진수 그대로의 유리수로 바꾼다.

    Fraction(0.3)은 이진 근삿값이 되므로, float는 repr 문자열을 거쳐 변환한다.
    """
    if isinstance(value, float):
        return Fraction(repr(value))
    return Fraction(value)
