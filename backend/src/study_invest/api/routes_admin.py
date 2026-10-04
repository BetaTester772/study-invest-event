"""관리자 API (F-07, F-09, F-11, F-13). 모든 경로에 X-Admin-Key가 필요하다."""

from __future__ import annotations

import asyncio
import functools
from dataclasses import replace
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from ..clock import OffsetClock
from ..event_calendar import to_kst
from ..models import (
    AuditLog,
    CertStatus,
    Participant,
    SettlementLog,
    StudyCertification,
)
from ..params import EventParams
from ..services import auth, certification, market
from ..services.common import (
    DomainError,
    audit,
    current_prices,
    get_params,
    params_lock,
    rewards_received,
    set_params,
    valuate,
)
from ..services.market import BatchResult
from ..simulator import run as run_simulation
from . import schemas, views
from .deps import BatchSessionDep, NowDep, ParamsDep, SessionDep, StateDep, require_admin

router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])


def _admin_participant(
    p: Participant,
    prices: dict[str, int],
    counts: dict[tuple[int, CertStatus], int],
    rewards: dict[int, int],
) -> schemas.AdminParticipant:
    valuation = valuate(p, prices, rewards.get(p.id, 0))
    return schemas.AdminParticipant(
        id=p.id,
        nickname=p.nickname,
        status=p.status,
        joined_at=p.joined_at,
        identity=p.identity,
        email=p.email_address or p.email,
        masked_email=p.masked_email,
        verified=p.verified,
        email_verified=p.email_verified,
        needs_profile=p.needs_profile,
        name=p.name,
        student_id=p.student_id,
        department=p.department,
        verified_at=p.verified_at,
        verified_via=p.verified_via,
        cash=p.cash,
        total_assets=valuation.total_assets,
        principal=valuation.principal,
        return_rate=float(valuation.return_rate),
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
    rewards = rewards_received(s)
    rows = s.scalars(
        select(Participant).options(selectinload(Participant.holdings)).order_by(Participant.id)
    )
    return [_admin_participant(p, prices, counts, rewards) for p in rows]


@router.patch("/participants/{participant_id}", response_model=schemas.AdminParticipant)
def patch_participant(
    participant_id: int, body: schemas.ParticipantPatch, s: SessionDep, now: NowDep
) -> schemas.AdminParticipant:
    p = s.get(Participant, participant_id)
    if p is None:
        raise DomainError("NOT_FOUND", "참가자를 찾을 수 없습니다.", 404)
    if body.status is not None and body.status != p.status:
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
    if body.verified is not None:
        auth.set_verified(s, p, body.verified, now)
    s.commit()
    _, prices = current_prices(s)
    return _admin_participant(p, prices, _cert_counts(s), rewards_received(s, p.id))


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
    params_lock(s)
    values = body.model_dump()
    if values["verified_only_trading"] is None:  # 파라미터 폼은 이 스위치를 보내지 않는다
        values["verified_only_trading"] = get_params(s).verified_only_trading
    try:
        params = EventParams.from_dict(values)
    except ValueError as exc:
        raise DomainError("INVALID_PARAMS", str(exc), 422) from exc
    set_params(s, params, now)
    s.commit()
    return schemas.Params.model_validate(params.to_dict())


@router.get("/trading-access", response_model=schemas.TradingAccess)
def trading_access(s: SessionDep) -> schemas.TradingAccess:
    return schemas.TradingAccess(verified_only=get_params(s).verified_only_trading)


@router.put("/trading-access", response_model=schemas.TradingAccess)
def set_trading_access(
    body: schemas.TradingAccess, s: SessionDep, now: NowDep
) -> schemas.TradingAccess:
    """'인증된 참가자만 거래' 스위치. 부정 행위가 보이면 켠다(파라미터 이력·감사 로그에 남음)."""
    params_lock(s)
    set_params(s, replace(get_params(s), verified_only_trading=body.verified_only), now)
    s.commit()
    return body


@router.put("/prices/{day}/{code}", response_model=schemas.PricePoint)
def manual_price(
    day: date,
    code: str,
    body: schemas.ManualPriceRequest,
    state: StateDep,
    s: BatchSessionDep,
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
    body: schemas.BatchRequest, state: StateDep, s: BatchSessionDep, now: NowDep
) -> schemas.BatchResult:
    day = body.day or to_kst(now).date()
    result = market.open_day(s, day, now, state.calendar)
    s.commit()
    return _batch(result)


@router.post("/batch/settle", response_model=schemas.BatchResult)
def batch_settle(
    body: schemas.BatchRequest, state: StateDep, s: BatchSessionDep, now: NowDep
) -> schemas.BatchResult:
    day = body.day or to_kst(now).date()
    result = market.settle_day(s, day, now, state.calendar, state.rng)
    s.commit()
    return _batch(result)


@router.post("/batch/run-due", response_model=list[schemas.BatchResult])
def batch_run_due(state: StateDep, now: NowDep) -> list[schemas.BatchResult]:
    results = market.run_due(state.batch_session_factory, now, state.calendar, state.rng)
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


@router.get("/qa", response_model=schemas.QaStatus)
async def qa_status(state: StateDep) -> schemas.QaStatus:  # I/O 없음 → async
    """QA 도구 사용 가능 여부. 화면이 버튼을 보일지 정한다."""
    return schemas.QaStatus(enabled=state.settings.qa_tools)


@router.post("/qa/next-step", response_model=schemas.BatchResult)
def qa_next_step(state: StateDep, s: BatchSessionDep, now: NowDep) -> schemas.BatchResult:
    """공시(09:00) → 마감·정산(18:00) → 다음 날 공시 순으로 한 단계만 진행한다.

    진행한 뒤 앱 시계를 그 단계의 시각으로 옮긴다.
    """
    if not state.settings.qa_tools:
        raise DomainError("QA_DISABLED", "이 서버는 QA 도구가 꺼져 있습니다.", 403)
    result, at = market.qa_next_step(s, now, state.calendar, state.rng)
    s.commit()
    if not isinstance(state.clock, OffsetClock):
        state.clock = OffsetClock(state.clock)
    state.clock.jump_to(at)
    return _batch(result)


@router.post("/qa/advance-price", response_model=schemas.BatchResult)
def qa_advance_price(state: StateDep, s: BatchSessionDep, now: NowDep) -> schemas.BatchResult:
    """최신 공시일을 지금 정산하고 다음 운영일 시작가를 바로 공시한다. QA 서버에서만 켠다."""
    if not state.settings.qa_tools:
        raise DomainError("QA_DISABLED", "이 서버는 QA 도구가 꺼져 있습니다.", 403)
    result = market.advance_price(s, now, state.calendar, state.rng)
    s.commit()
    return _batch(result)


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


@router.get("/db-pools")
def db_pools(state: StateDep) -> dict[str, dict[str, object]]:
    """앱 쪽 연결 풀(api·batch) 사용 현황. PgBouncer 쪽은 pgAdmin·SHOW POOLS로 본다."""
    return {name: dict(stat) for name, stat in state.pools.status().items()}


@router.get("/audit", response_model=list[schemas.AuditEntry])
def audit_log(
    s: SessionDep, limit: Annotated[int, Query(ge=1, le=1000)] = 200
) -> list[schemas.AuditEntry]:
    rows = s.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit))
    return [schemas.AuditEntry.model_validate(r) for r in rows]


@router.get("/simulate/options", response_model=schemas.SimulateOptions)
async def simulate_options() -> schemas.SimulateOptions:  # I/O 없음 → async
    """시뮬레이터 입력 한계와 기본값. 화면 입력 범위의 유일한 출처."""
    return schemas.SimulateOptions(
        paths=schemas.int_range(schemas.SimulateRequest, "paths"),
        rounds=schemas.int_range(schemas.SimulateRequest, "rounds"),
    )


@router.post("/simulate")
async def simulate(
    body: schemas.SimulateRequest, state: StateDep, params: ParamsDep
) -> dict[str, object]:
    """CPU 바운드(수 초)라 스레드에서 돌리면 GIL을 잡아 다른 요청까지 느려진다.
    프로세스 풀에서 실행하고 이벤트 루프는 결과만 기다린다. 파라미터 조회(DB)는
    동기 의존성(ParamsDep)이 스레드풀에서 끝낸 뒤 넘겨준다."""
    job = functools.partial(
        run_simulation, body.paths, body.rounds, body.seed, body.use_price_cap, params
    )
    if state.cpu_executor is None:
        report = await asyncio.to_thread(job)
    else:
        report = await asyncio.get_running_loop().run_in_executor(state.cpu_executor, job)
    return report.to_dict()
