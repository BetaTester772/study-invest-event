"""ORM·서비스 결과 → 응답 스키마 변환."""

from __future__ import annotations

from ..models import REJECT_MESSAGES, Order, StudyCertification
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
        reward_quantity=c.reward_quantity,
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
        return_rate=p.return_rate,
        day=p.day,
        buy_limit=schemas.BuyLimit(
            ratio=p.limit_ratio, limit_amount=p.limit_amount, remaining=p.remaining
        ),
    )
