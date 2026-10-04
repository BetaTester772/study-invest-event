"""참가자 API: 포트폴리오(F-04), 주문(F-03), 공부 인증(F-06), 학교 메일 인증.

관리자가 '인증된 참가자만 거래'(verified_only_trading)를 켜면 주문만 인증된 참가자로 제한한다
(VerifiedMeDep). 조회와 공부 인증 제출은 미인증 참가자도 그대로 할 수 있다.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select

from ..models import CodePurpose, Order, Participant, StudyCertification
from ..normalize import mask_email
from ..services import auth, certification, trading
from ..services.common import DomainError, get_params
from . import schemas, views
from .deps import (
    MeDep,
    NowDep,
    ParamsDep,
    RealNowDep,
    SessionDep,
    StateDep,
    VerifiedMeDep,
)
from .email_codes import consume_code
from .routes_public import send_code

router = APIRouter(prefix="/api/me")


@router.get("", response_model=schemas.Participant)
def me(participant: MeDep) -> schemas.Participant:
    return schemas.Participant.model_validate(participant)


def _ensure_can_verify_email(participant: Participant) -> None:
    if participant.email_verified:
        raise DomainError("ALREADY_VERIFIED", "이미 학교 메일 인증을 마쳤습니다.")


@router.post("/email/code", response_model=schemas.EmailCodeResponse, status_code=202)
def request_my_email_code(
    body: schemas.MyEmailCodeRequest,
    participant: MeDep,
    state: StateDep,
    s: SessionDep,
    real_now: RealNowDep,
) -> schemas.EmailCodeResponse:
    """학교 메일 인증 코드를 보낸다. 주소를 비우면 등록 메일로 보내고 응답 주소는 가린다.

    다른 주소(email)는 등록 메일을 잘못 적었거나 메일이 없는 계정(메일 인증 도입 전)이 쓴다.
    """
    _ensure_can_verify_email(participant)
    if body.email is not None:
        return send_code(
            state, s, body.email, real_now, CodePurpose.VERIFY, requester_id=participant.id
        )
    if participant.email_address is None:
        raise DomainError(
            "EMAIL_REQUIRED", "등록된 학교 메일이 없습니다. 메일 주소를 입력하세요.", 422
        )
    return send_code(
        state,
        s,
        participant.email_address,
        real_now,
        CodePurpose.VERIFY,
        requester_id=participant.id,
        shown=mask_email,
    )


@router.post("/email", response_model=schemas.Participant)
def verify_email(
    body: schemas.VerifyEmailRequest,
    participant: MeDep,
    s: SessionDep,
    real_now: RealNowDep,
) -> schemas.Participant:
    """학교 메일 코드로 인증한다(코드는 POST /api/me/email/code). 주소를 비우면 등록 메일.

    메일 코드로 아직 인증하지 않은 계정만(미인증, 관리자 인증). 메일 인증 도입 전 계정은
    이름·학번·학과·동의도 함께 받는다.
    """
    _ensure_can_verify_email(participant)
    raw_email = body.email if body.email is not None else participant.email_address
    if raw_email is None:
        raise DomainError(
            "EMAIL_REQUIRED", "등록된 학교 메일이 없습니다. 메일 주소를 입력하세요.", 422
        )
    profile = None
    if participant.needs_profile:
        if body.name is None or body.student_id is None or body.department is None:
            raise DomainError("PROFILE_REQUIRED", "이름·학번·학과를 함께 입력하세요.", 422)
        auth.ensure_privacy_consent(body.privacy_consent)
        profile = auth.Profile(body.name, body.student_id, body.department)
    email = consume_code(s, raw_email, body.code, real_now)
    auth.verify_email(s, participant, email, profile, real_now)
    s.commit()
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
    body: schemas.OrderRequest,
    participant: VerifiedMeDep,
    state: StateDep,
    s: SessionDep,
    now: NowDep,
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


@router.get("/certification-status", response_model=schemas.CertificationStatus)
def certification_status(
    participant: MeDep, state: StateDep, s: SessionDep, now: NowDep, params: ParamsDep
) -> schemas.CertificationStatus:
    """지금 인증을 올릴 수 있는지(제출 API와 같은 판단). 화면은 이 결과만 따른다."""
    st = certification.submission_status(s, participant, now, state.calendar, params)
    return schemas.CertificationStatus(
        target_date=st.target_date,
        cutoff=params.certification_cutoff.strftime("%H:%M"),
        can_submit=st.can_submit,
        reason=st.reason,
        message=st.message,
        existing=views.certification(st.existing) if st.existing else None,
    )


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
