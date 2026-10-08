"""호재·악재 (03-pricing §3, F-14).

전날 18:00 정산에서 다음 운영일 몫으로 뽑혀 같은 정산에서 주식 변동률에 곱으로 얹히고, 반영된
시작가와 함께 09:00에 발표된다. 관리자는 그날 시작가가 아직 정해지지 않은 운영일(전날 정산 전)에
직접 쓰거나 지울 수 있다. 서비스 함수는 커밋하지 않는다.
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
from ..news_pool import Article, articles_for
from ..params import NEWS_RATE_MAX, EventParams
from ..pricing import draw_news
from .common import DomainError, audit, batch_lock, latest_opened_day, market_day

HEADLINE_MAX = 120
SUBTITLE_MAX = 120
BODY_MAX = 600
BYLINE_MAX = 40


def pick_article(s: Session, code: str, name: str, kind: NewsKind, pick: float) -> Article:
    """종목별 기사 풀(+공통 예비)에서 하나 고른다. 이번 이벤트에서 이미 나온 제목은 피하고,
    다 썼으면 전체에서 다시 고른다. pick ~ U(0, 1) 하나만 쓴다."""
    pool = articles_for(code, name, kind.value)
    used = set(
        s.scalars(
            select(NewsItem.headline).where(
                NewsItem.code == code, NewsItem.headline.in_([a.headline for a in pool])
            )
        )
    )
    candidates = [a for a in pool if a.headline not in used] or list(pool)
    return candidates[min(int(pick * len(candidates)), len(candidates) - 1)]


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
) -> list[NewsItem]:
    """day 몫의 무작위 뉴스를 하루 최대 news_max_per_day건(서로 다른 종목) 만든다. 그날 뉴스가
    이미 있으면(관리자 작성) 만들지 않는다.

    호출자(정산)가 코인·주식 잡음 난수를 뽑은 뒤에 부른다.
    """
    if params.news_probability <= 0 or news_on(s, day):
        return []
    items: list[NewsItem] = []
    for draw in draw_news([i.code for i in STOCKS], params, rng):
        kind = NewsKind(draw.kind)
        article = pick_article(s, draw.code, BY_CODE[draw.code].name, kind, draw.headline_pick)
        item = NewsItem(
            day=day,
            code=draw.code,
            kind=kind,
            rate=draw.rate,
            headline=article.headline,
            subtitle=article.subtitle,
            body=article.body,
            byline=article.byline,
            source=NewsSource.RANDOM,
            created_at=now,
        )
        s.add(item)
        items.append(item)
    s.flush()
    return items


def is_priced(s: Session, day: date, calendar: EventCalendar) -> bool:
    """day의 시작가가 이미 정해졌는지. 전날이 정산됐거나(뉴스가 반영된 뒤) day가 공시됐으면 참."""
    if market_day(s, day) is not None:
        return True
    prev = calendar.previous_operating_day(day)
    if prev is None:
        return False
    md = market_day(s, prev)
    return md is not None and md.settled_at is not None


def _check_day(s: Session, day: date, calendar: EventCalendar) -> None:
    if not calendar.is_operating_day(day):
        raise DomainError("NOT_OPERATING_DAY", f"{day}는 운영일이 아닙니다.", 422)
    if calendar.round_of(day) is None:
        raise DomainError(
            "NO_ROUND", f"{day}는 정산(반영일)이 없어 뉴스를 반영할 수 없습니다.", 422
        )
    if calendar.previous_operating_day(day) is None:
        raise DomainError(
            "NO_PREVIOUS_SETTLEMENT",
            f"{day}는 첫 운영일이라 뉴스를 반영할 정산이 없습니다.",
            422,
        )
    if is_priced(s, day, calendar):
        raise DomainError(
            "PRICE_ALREADY_FIXED", "그날 시작가가 이미 정해져 뉴스를 바꿀 수 없습니다."
        )


def set_manual_news(
    s: Session,
    day: date,
    code: str,
    kind: NewsKind,
    rate: float,
    headline: str,
    now: datetime,
    calendar: EventCalendar,
    *,
    subtitle: str | None = None,
    body: str | None = None,
    byline: str | None = None,
) -> NewsItem:
    """시작가가 아직 정해지지 않은 운영일의 뉴스를 쓴다(같은 날·종목이 있으면 덮어쓴다).

    전날 18:00 정산에서 그 종목 변동률에 곱해져 그날 시작가에 반영된다. 부제·본문·바이라인은
    선택이다. 비우면 참가자 화면에 제목만 보인다.
    """
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
    extras = {
        "subtitle": (subtitle, SUBTITLE_MAX),
        "body": (body, BODY_MAX),
        "byline": (byline, BYLINE_MAX),
    }
    cleaned: dict[str, str | None] = {}
    for field, (value, limit) in extras.items():
        text = " ".join(value.split()) if value else ""
        if len(text) > limit:
            raise DomainError("ARTICLE_TOO_LONG", f"{field}은(는) {limit}자 이내여야 합니다.", 422)
        cleaned[field] = text or None
    item.kind = kind
    item.rate = rate
    item.headline = headline
    item.subtitle = cleaned["subtitle"]
    item.body = cleaned["body"]
    item.byline = cleaned["byline"]
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
    """시작가가 아직 정해지지 않은 운영일의 뉴스를 지운다(무작위 생성분도)."""
    batch_lock(s)
    item = s.scalar(select(NewsItem).where(NewsItem.day == day, NewsItem.code == code))
    if item is None:
        raise DomainError("NEWS_NOT_FOUND", "그날 그 종목의 뉴스가 없습니다.", 404)
    _check_day(s, day, calendar)
    s.delete(item)
    s.flush()
    audit(s, now, "admin", "news.delete", day=day.isoformat(), code=code, headline=item.headline)
