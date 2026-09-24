"""관리자 API (F-07, F-09, F-11, F-13). 모든 경로에 X-Admin-Key가 필요하다."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from ..event_calendar import to_kst
from ..models import (
    AuditLog,
    CertStatus,
    Participant,
    SettlementLog,
    StudyCertification,
)
from ..params import EventParams
from ..services import certification, market
from ..services.common import (
    DomainError,
    audit,
    current_prices,
    get_params,
    set_params,
    total_assets,
)
from ..services.market import BatchResult
from ..simulator import run as run_simulation
from . import schemas, views
from .deps import NowDep, SessionDep, StateDep, require_admin

router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])


def _admin_participant(
    p: Participant, prices: dict[str, int], counts: dict[tuple[int, CertStatus], int]
) -> schemas.AdminParticipant:
    return schemas.AdminParticipant(
        id=p.id,
        nickname=p.nickname,
        status=p.status,
        joined_at=p.joined_at,
        identity=p.identity,
        cash=p.cash,
        total_assets=total_assets(p, prices),
        rejected_certifications=counts.get((p.id, CertStatus.REJECTED), 0),
        approved_certifications=counts.get((p.id, CertStatus.APPROVED), 0),
    )


def _cert_counts(s: SessionDep) -> dict[tuple[int, CertStatus], int]:
    rows = s.execute(
        select(StudyCertification.participant_id, StudyCertification.status, func.count()).group_by(
            StudyCertification.participant_id, StudyCertification.status
        )
    )
    return {(pid, status): n for pid, status, n in rows}


@router.get("/participants", response_model=list[schemas.AdminParticipant])
def participants(s: SessionDep) -> list[schemas.AdminParticipant]:
    _, prices = current_prices(s)
    counts = _cert_counts(s)
    rows = s.scalars(
        select(Participant).options(selectinload(Participant.holdings)).order_by(Participant.id)
    )
    return [_admin_participant(p, prices, counts) for p in rows]


@router.patch("/participants/{participant_id}", response_model=schemas.AdminParticipant)
def patch_participant(
    participant_id: int, body: schemas.ParticipantPatch, s: SessionDep, now: NowDep
) -> schemas.AdminParticipant:
    p = s.get(Participant, participant_id)
    if p is None:
        raise DomainError("NOT_FOUND", "참가자를 찾을 수 없습니다.", 404)
    before = p.status
    p.status = body.status
    audit(
        s,
        now,
        "admin",
        "participant.status",
        participant_id=p.id,
        before=before.value,
        after=body.status.value,
    )
    s.commit()
    _, prices = current_prices(s)
    return _admin_participant(p, prices, _cert_counts(s))


@router.get("/certifications", response_model=list[schemas.AdminCertification])
def list_certifications(
    s: SessionDep, status: CertStatus | None = None
) -> list[schemas.AdminCertification]:
    query = select(StudyCertification).options(selectinload(StudyCertification.participant))
    if status is not None:
        query = query.where(StudyCertification.status == status)
    rows = s.scalars(query.order_by(StudyCertification.submitted_at, StudyCertification.id))
    return [views.admin_certification(c) for c in rows]


@router.get("/certifications/{cert_id}/image")
def certification_image(cert_id: int, state: StateDep, s: SessionDep) -> FileResponse:
    cert = s.get(StudyCertification, cert_id)
    if cert is None:
        raise DomainError("NOT_FOUND", "인증을 찾을 수 없습니다.", 404)
    path = certification.image_file(cert, state.settings.upload_dir)
    if path is None:
        raise DomainError("NOT_FOUND", "사진이 삭제되었습니다.", 404)
    return FileResponse(path, media_type=cert.image_content_type)


@router.post("/certifications/{cert_id}/review", response_model=schemas.AdminCertification)
def review_certification(
    cert_id: int, body: schemas.ReviewRequest, s: SessionDep, now: NowDep
) -> schemas.AdminCertification:
    cert = certification.review(s, cert_id, body.approve, body.reason, now)
    s.commit()
    return views.admin_certification(cert)


@router.get("/params", response_model=schemas.Params)
def read_params(s: SessionDep) -> schemas.Params:
    return schemas.Params.model_validate(get_params(s).to_dict())


@router.put("/params", response_model=schemas.Params)
def update_params(body: schemas.Params, s: SessionDep, now: NowDep) -> schemas.Params:
    try:
        params = EventParams.from_dict(body.model_dump())
    except ValueError as exc:
        raise DomainError("INVALID_PARAMS", str(exc), 422) from exc
    set_params(s, params, now)
    s.commit()
    return schemas.Params.model_validate(params.to_dict())


@router.put("/prices/{day}/{code}", response_model=schemas.PricePoint)
def manual_price(
    day: date,
    code: str,
    body: schemas.ManualPriceRequest,
    state: StateDep,
    s: SessionDep,
    now: NowDep,
) -> schemas.PricePoint:
    record = market.set_manual_price(s, day, code, body.price, body.reason, now, state.calendar)
    s.commit()
    return schemas.PricePoint(
        day=record.day,
        price=record.price,
        change_rate=market.change_rate(record),
        source=record.source,
    )


def _batch(result: BatchResult) -> schemas.BatchResult:
    return schemas.BatchResult(action=result.action, day=result.day, detail=result.detail)


@router.post("/batch/open", response_model=schemas.BatchResult)
def batch_open(
    body: schemas.BatchRequest, state: StateDep, s: SessionDep, now: NowDep
) -> schemas.BatchResult:
    day = body.day or to_kst(now).date()
    result = market.open_day(s, day, now, state.calendar)
    s.commit()
    return _batch(result)


@router.post("/batch/settle", response_model=schemas.BatchResult)
def batch_settle(
    body: schemas.BatchRequest, state: StateDep, s: SessionDep, now: NowDep
) -> schemas.BatchResult:
    day = body.day or to_kst(now).date()
    result = market.settle_day(s, day, now, state.calendar, state.rng)
    s.commit()
    return _batch(result)


@router.post("/batch/run-due", response_model=list[schemas.BatchResult])
def batch_run_due(state: StateDep, now: NowDep) -> list[schemas.BatchResult]:
    results = market.run_due(state.session_factory, now, state.calendar, state.rng)
    out = []
    for r in results:
        if isinstance(r, BatchResult):
            out.append(_batch(r))
        else:
            out.append(
                schemas.BatchResult(
                    action=str(r["action"]),
                    day=r["day"],
                    detail={k: v for k, v in r.items() if k not in {"action", "day"}},
                )
            )
    return out


@router.get("/settlements", response_model=list[schemas.SettlementLog])
def settlements(s: SessionDep) -> list[schemas.SettlementLog]:
    rows = s.scalars(select(SettlementLog).order_by(SettlementLog.round_no))
    return [
        schemas.SettlementLog(
            id=r.id,
            round=r.round_no,
            trade_day=r.trade_day,
            effective_day=r.effective_day,
            created_at=r.created_at,
            stocks=[schemas.StockSettlement.model_validate(x) for x in r.stocks],
            coin=schemas.CoinSettlement.model_validate(r.coin),
            params=schemas.Params.model_validate(EventParams.from_dict(r.params).to_dict()),
        )
        for r in rows
    ]


@router.get("/audit", response_model=list[schemas.AuditEntry])
def audit_log(
    s: SessionDep, limit: Annotated[int, Query(ge=1, le=1000)] = 200
) -> list[schemas.AuditEntry]:
    rows = s.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit))
    return [schemas.AuditEntry.model_validate(r) for r in rows]


@router.post("/simulate")
def simulate(body: schemas.SimulateRequest, s: SessionDep) -> dict[str, object]:
    report = run_simulation(body.paths, body.rounds, body.seed, body.use_price_cap, get_params(s))
    return report.to_dict()
