"""호재·악재 (03-pricing §3, F-14).

운영일 09:00 공시와 함께 발표되고 그날 18:00 정산에서 주식 변동률에 곱으로 얹힌다. 무작위 뉴스는
전날 정산 끝에 다음 운영일 몫으로 1건 이하 생성되고, 관리자는 아직 정산되지 않은 운영일에 직접
쓰거나 지울 수 있다. 서비스 함수는 커밋하지 않는다.
"""

from __future__ import annotations

import random
from datetime import date, datetime
from fractions import Fraction

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..event_calendar import EventCalendar
from ..instruments import BY_CODE, STOCKS
from ..models import NewsItem, NewsKind, NewsSource
from ..money import exact
from ..params import NEWS_RATE_MAX, EventParams
from ..pricing import draw_news
from .common import DomainError, audit, batch_lock, latest_opened_day, market_day

HEADLINE_MAX = 120

HEADLINES: dict[NewsKind, tuple[str, ...]] = {
    NewsKind.GOOD: (
        "{name}, 대형 수주 계약 체결",
        "{name}, 분기 실적 예상치 크게 웃돌아",
        "{name}, 신제품 출시 첫날 완판",
        "{name}, 해외 시장 진출 승인",
        "{name}, 자사주 대규모 매입 발표",
        "{name}, 업계 1위 탈환",
    ),
    NewsKind.BAD: (
        "{name}, 주력 공장 가동 중단",
        "{name}, 분기 실적 예상치 크게 밑돌아",
        "{name}, 주력 제품 전량 리콜",
        "{name}, 핵심 임원 돌연 사임",
        "{name}, 규제 당국 조사 착수",
        "{name}, 대규모 소송에 피소",
    ),
}
"""무작위 뉴스 제목 틀. {name}에 종목명이 들어간다."""


def signed_rate(item: NewsItem) -> Fraction:
    """정산에 쓰는 부호 있는 효과. 호재 +rate, 악재 −rate."""
    r = exact(item.rate)
    return r if item.kind is NewsKind.GOOD else -r


def news_on(s: Session, day: date) -> list[NewsItem]:
    return list(s.scalars(select(NewsItem).where(NewsItem.day == day).order_by(NewsItem.code)))


def news_rates(items: list[NewsItem]) -> dict[str, Fraction]:
    return {n.code: signed_rate(n) for n in items}


def published_news(s: Session) -> list[NewsItem]:
    """참가자에게 보이는 뉴스: 공시된 운영일까지의 뉴스, 최신 날짜부터."""
    latest = latest_opened_day(s)
    if latest is None:
        return []
    return list(
        s.scalars(
            select(NewsItem)
            .where(NewsItem.day <= latest)
            .order_by(NewsItem.day.desc(), NewsItem.code)
        )
    )


def all_news(s: Session) -> list[NewsItem]:
    """관리자용: 미래 날짜를 포함한 전체, 최신 날짜부터."""
    return list(s.scalars(select(NewsItem).order_by(NewsItem.day.desc(), NewsItem.code)))


def create_random_news(
    s: Session, day: date, now: datetime, params: EventParams, rng: random.Random
) -> NewsItem | None:
    """day 몫의 무작위 뉴스를 1건 이하 만든다. 그날 뉴스가 이미 있으면(관리자 작성) 만들지 않는다.

    호출자(정산)가 코인·주식 잡음 난수를 뽑은 뒤에 부른다.
    """
    if params.news_probability <= 0 or news_on(s, day):
        return None
    draw = draw_news([i.code for i in STOCKS], params, rng)
    if draw is None:
        return None
    kind = NewsKind(draw.kind)
    pool = HEADLINES[kind]
    headline = pool[min(int(draw.headline_pick * len(pool)), len(pool) - 1)].format(
        name=BY_CODE[draw.code].name
    )
    item = NewsItem(
        day=day,
        code=draw.code,
        kind=kind,
        rate=draw.rate,
        headline=headline,
        source=NewsSource.RANDOM,
        created_at=now,
    )
    s.add(item)
    s.flush()
    return item


def _check_day(s: Session, day: date, calendar: EventCalendar) -> None:
    if not calendar.is_operating_day(day):
        raise DomainError("NOT_OPERATING_DAY", f"{day}는 운영일이 아닙니다.", 422)
    if calendar.round_of(day) is None:
        raise DomainError(
            "NO_ROUND", f"{day}는 정산(반영일)이 없어 뉴스를 반영할 수 없습니다.", 422
        )
    md = market_day(s, day)
    if md is not None and md.settled_at is not None:
        raise DomainError("DAY_ALREADY_SETTLED", "이미 정산된 운영일의 뉴스는 바꿀 수 없습니다.")


def set_manual_news(
    s: Session,
    day: date,
    code: str,
    kind: NewsKind,
    rate: float,
    headline: str,
    now: datetime,
    calendar: EventCalendar,
) -> NewsItem:
    """아직 정산되지 않은 운영일의 뉴스를 쓴다(같은 날·종목이 있으면 덮어쓴다)."""
    batch_lock(s)  # 정산·무작위 생성과 겹치지 않게
    inst = BY_CODE.get(code)
    if inst is None:
        raise DomainError("UNKNOWN_INSTRUMENT", "존재하지 않는 종목입니다.", 404)
    if inst not in STOCKS:
        raise DomainError("NOT_A_STOCK", "호재·악재는 주식 종목에만 쓸 수 있습니다.", 422)
    _check_day(s, day, calendar)
    if not (0 < rate <= NEWS_RATE_MAX):
        raise DomainError(
            "INVALID_RATE", f"효과 크기는 0보다 크고 {NEWS_RATE_MAX:g} 이하여야 합니다.", 422
        )
    headline = " ".join(headline.split())
    if not headline:
        raise DomainError("HEADLINE_REQUIRED", "뉴스 제목을 입력하세요.", 422)
    if len(headline) > HEADLINE_MAX:
        raise DomainError(
            "HEADLINE_TOO_LONG", f"뉴스 제목은 {HEADLINE_MAX}자 이내여야 합니다.", 422
        )
    item = s.scalar(select(NewsItem).where(NewsItem.day == day, NewsItem.code == code))
    if item is None:
        item = NewsItem(day=day, code=code, created_at=now)
        s.add(item)
    item.kind = kind
    item.rate = rate
    item.headline = headline
    item.source = NewsSource.MANUAL
    item.created_at = now
    s.flush()
    audit(
        s,
        now,
        "admin",
        "news.manual",
        day=day.isoformat(),
        code=code,
        kind=kind.value,
        rate=rate,
        headline=headline,
    )
    return item


def delete_news(s: Session, day: date, code: str, now: datetime, calendar: EventCalendar) -> None:
    """아직 정산되지 않은 운영일의 뉴스를 지운다(무작위 생성분도)."""
    batch_lock(s)
    item = s.scalar(select(NewsItem).where(NewsItem.day == day, NewsItem.code == code))
    if item is None:
        raise DomainError("NEWS_NOT_FOUND", "그날 그 종목의 뉴스가 없습니다.", 404)
    _check_day(s, day, calendar)
    s.delete(item)
    s.flush()
    audit(s, now, "admin", "news.delete", day=day.isoformat(), code=code, headline=item.headline)
