"""참가자 API: 포트폴리오(F-04), 주문(F-03), 공부 인증(F-06)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select

from ..models import Order, StudyCertification
from ..services import certification, trading
from ..services.common import DomainError, get_params
from . import schemas, views
from .deps import MeDep, NowDep, SessionDep, StateDep

router = APIRouter(prefix="/api/me")


@router.get("", response_model=schemas.Participant)
def me(participant: MeDep) -> schemas.Participant:
    return schemas.Participant.model_validate(participant)


@router.get("/portfolio", response_model=schemas.Portfolio)
def portfolio(participant: MeDep, s: SessionDep, now: NowDep) -> schemas.Portfolio:
    return views.portfolio(trading.portfolio(s, participant, now, get_params(s)))


@router.get("/orders", response_model=list[schemas.Order])
def orders(
    participant: MeDep, s: SessionDep, limit: Annotated[int, Query(ge=1, le=500)] = 100
) -> list[schemas.Order]:
    rows = s.scalars(
        select(Order)
        .where(Order.participant_id == participant.id)
        .order_by(Order.id.desc())
        .limit(limit)
    )
    return [views.order(o) for o in rows]


@router.post("/orders", response_model=schemas.Order, status_code=201)
def place_order(
    body: schemas.OrderRequest, participant: MeDep, state: StateDep, s: SessionDep, now: NowDep
) -> schemas.Order:
    order = trading.place_order(
        s, participant, body.code, body.side, body.quantity, now, state.calendar, get_params(s)
    )
    s.commit()
    return views.order(order)


@router.get("/certifications", response_model=list[schemas.Certification])
def certifications(participant: MeDep, s: SessionDep) -> list[schemas.Certification]:
    rows = s.scalars(
        select(StudyCertification)
        .where(StudyCertification.participant_id == participant.id)
        .order_by(StudyCertification.target_date.desc())
    )
    return [views.certification(c) for c in rows]


@router.post("/certifications", response_model=schemas.Certification, status_code=201)
def submit_certification(
    participant: MeDep,
    state: StateDep,
    s: SessionDep,
    now: NowDep,
    file: Annotated[UploadFile, File()],
) -> schemas.Certification:
    # 동기 def: DB 조회·해시·파일 저장이 모두 블로킹이므로 스레드풀에서 실행한다.
    limit = state.settings.max_upload_bytes
    data = file.file.read(limit + 1)
    cert = certification.submit(
        s, participant, data, now, state.calendar, get_params(s), state.settings.upload_dir, limit
    )
    s.commit()
    return views.certification(cert)


@router.get("/certifications/{cert_id}/image")
def certification_image(
    cert_id: int, participant: MeDep, state: StateDep, s: SessionDep
) -> FileResponse:
    cert = s.get(StudyCertification, cert_id)
    if cert is None or cert.participant_id != participant.id:
        raise DomainError("NOT_FOUND", "인증을 찾을 수 없습니다.", 404)
    path = certification.image_file(cert, state.settings.upload_dir)
    if path is None:
        raise DomainError("NOT_FOUND", "사진이 삭제되었습니다.", 404)
    return FileResponse(path, media_type=cert.image_content_type)
