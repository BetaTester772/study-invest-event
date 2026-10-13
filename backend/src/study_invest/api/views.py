"""ORM·서비스 결과 → 응답 스키마 변환."""

from __future__ import annotations

from ..instruments import BY_CODE
from ..models import REJECT_MESSAGES, NewsItem, Order, StudyCertification
from ..services import notifications
from ..services.trading import PortfolioView
from . import schemas


def order(o: Order) -> schemas.Order:
    return schemas.Order(
        id=o.id,
        code=o.code,
        side=o.side,
        quantity=o.quantity,
        price=o.price,
        amount=o.amount,
        status=o.status,
        reject_reason=o.reject_reason,
        reject_message=REJECT_MESSAGES[o.reject_reason] if o.reject_reason else None,
        trade_day=o.trade_day,
        created_at=o.created_at,
    )


def certification(c: StudyCertification) -> schemas.Certification:
    return schemas.Certification(
        id=c.id,
        target_date=c.target_date,
        status=c.status,
        reject_reason=c.reject_reason,
        submitted_at=c.submitted_at,
        reviewed_at=c.reviewed_at,
        rewarded_at=c.rewarded_at,
        reward_cash=c.reward_cash,
        image_url=f"/api/me/certifications/{c.id}/image" if c.image_path else None,
    )


def admin_certification(c: StudyCertification) -> schemas.AdminCertification:
    base = certification(c).model_dump()
    base["image_url"] = f"/api/admin/certifications/{c.id}/image" if c.image_path else None
    return schemas.AdminCertification(
        **base,
        participant_id=c.participant_id,
        nickname=c.participant.nickname,
        image_hash=c.image_hash,
        duplicate_of=c.duplicate_of,
    )


def portfolio(p: PortfolioView) -> schemas.Portfolio:
    return schemas.Portfolio(
        cash=p.cash,
        holdings=[schemas.HoldingView.model_validate(h) for h in p.holdings],
        holdings_value=p.holdings_value,
        total_assets=p.total_assets,
        initial_cash=p.initial_cash,
        rewards_received=p.rewards_received,
        principal=p.principal,
        profit=p.profit,
        return_rate=p.return_rate,
        day=p.day,
        buy_limit=None
        if p.limit_ratio is None or p.limit_amount is None or p.remaining is None
        else schemas.BuyLimit(
            ratio=p.limit_ratio, limit_amount=p.limit_amount, remaining=p.remaining
        ),
    )


def news_item(n: NewsItem) -> schemas.NewsItem:
    return schemas.NewsItem(
        id=n.id,
        day=n.day,
        code=n.code,
        name=BY_CODE[n.code].name if n.code in BY_CODE else n.code,
        kind=n.kind.value,
        rate=n.rate,
        headline=n.headline,
        subtitle=n.subtitle,
        body=n.body,
        byline=n.byline,
    )


def admin_news_item(n: NewsItem, applied: bool) -> schemas.AdminNewsItem:
    base = news_item(n)
    return schemas.AdminNewsItem(
        **base.model_dump(),
        source=n.source.value,
        created_at=n.created_at,
        applied=applied,
    )


def notification_inbox(items: list[notifications.InboxItem]) -> schemas.NotificationInbox:
    return schemas.NotificationInbox(
        unread=sum(1 for i in items if i.read_at is None),
        items=[
            schemas.NotificationItem(
                id=i.notification.id,
                title=i.notification.title,
                body=i.notification.body,
                created_at=i.notification.created_at,
                personal=i.notification.participant_id is not None,
                updated_at=i.notification.updated_at,
                read_at=i.read_at,
            )
            for i in items
        ],
    )


def admin_notification(i: notifications.AdminItem) -> schemas.AdminNotification:
    n = i.notification
    return schemas.AdminNotification(
        id=n.id,
        title=n.title,
        body=n.body,
        created_at=n.created_at,
        updated_at=n.updated_at,
        participant_id=n.participant_id,
        nickname=i.nickname,
        read_count=i.read_count,
        recipients=i.recipients,
    )


def admin_notification_detail(
    i: notifications.AdminItem, readers: list[notifications.Reader]
) -> schemas.AdminNotificationDetail:
    # 읽음 수·받는 사람 수는 함께 돌려주는 readers에서 센다. 따로 센 값(admin_list)을 쓰면 그 사이에
    # 누가 읽거나 가입했을 때 '0 / 2'와 '1명 읽음'처럼 서로 어긋난 숫자가 보인다.
    base = admin_notification(i).model_dump()
    base["read_count"] = sum(1 for r in readers if r.read_at is not None)
    base["recipients"] = len(readers)
    return schemas.AdminNotificationDetail(
        **base,
        readers=[
            schemas.NotificationReader(
                participant_id=r.participant_id, nickname=r.nickname, read_at=r.read_at
            )
            for r in readers
        ],
    )
