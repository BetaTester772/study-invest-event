"""공부 인증 제출·검수·보상 지급 (05-certification, F-06~F-08, 06-abuse-risk §3)."""

from __future__ import annotations

import hashlib
import uuid
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..event_calendar import EventCalendar, to_kst
from ..instruments import COIN
from ..models import (
    CertStatus,
    Holding,
    Participant,
    ParticipantStatus,
    StudyCertification,
)
from ..params import EventParams
from .common import DomainError, audit

# 매직 바이트로 형식을 확인한다(Content-Type 헤더는 신뢰하지 않는다).
IMAGE_TYPES: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
}


def sniff_image(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[4:8] == b"ftyp" and data[8:12] in {b"heic", b"heix", b"mif1", b"msf1", b"heim"}:
        return "image/heic"
    return None


def submit(
    s: Session,
    participant: Participant,
    data: bytes,
    now: datetime,
    calendar: EventCalendar,
    params: EventParams,
    upload_dir: Path,
    max_bytes: int,
) -> StudyCertification:
    """인증 사진 1장 제출. 1인 1일 1회, 마감 시각 이후는 다음 날짜로 집계한다."""
    if participant.status is ParticipantStatus.DISQUALIFIED:
        raise DomainError("DISQUALIFIED", "실격 처리된 참가자는 인증할 수 없습니다.", 403)
    if not data or len(data) > max_bytes:
        raise DomainError(
            "INVALID_IMAGE", f"사진은 {max_bytes // (1024 * 1024)}MB 이하여야 합니다.", 422
        )
    content_type = sniff_image(data)
    if content_type is None:
        raise DomainError("INVALID_IMAGE", "JPEG·PNG·WEBP·HEIC 사진만 올릴 수 있습니다.", 422)
    target = calendar.certification_target_date(now, params.certification_cutoff)
    if not calendar.is_operating_day(target):
        raise DomainError("OUTSIDE_EVENT", f"{target}는 이벤트 기간이 아닙니다.", 422)
    exists = s.scalar(
        select(StudyCertification.id).where(
            StudyCertification.participant_id == participant.id,
            StudyCertification.target_date == target,
        )
    )
    if exists:
        raise DomainError("ALREADY_CERTIFIED", f"{target} 인증은 이미 제출했습니다(1일 1회).")

    digest = hashlib.sha256(data).hexdigest()
    duplicate_of = s.scalar(
        select(StudyCertification.id)
        .where(StudyCertification.image_hash == digest)
        .order_by(StudyCertification.id)
        .limit(1)
    )
    filename = f"{uuid.uuid4().hex}{IMAGE_TYPES[content_type]}"
    cert = StudyCertification(
        participant_id=participant.id,
        target_date=target,
        image_path=filename,
        image_content_type=content_type,
        image_hash=digest,
        duplicate_of=duplicate_of,
        status=CertStatus.PENDING,
        submitted_at=now,
    )
    try:
        # 유니크 제약 위반을 파일 저장 전에 확인. 동시 제출은 앞선 검사를 둘 다 통과할 수 있다.
        with s.begin_nested():
            s.add(cert)
    except IntegrityError as exc:
        raise DomainError(
            "ALREADY_CERTIFIED", f"{target} 인증은 이미 제출했습니다(1일 1회)."
        ) from exc
    upload_dir.mkdir(parents=True, exist_ok=True)
    (upload_dir / filename).write_bytes(data)
    audit(
        s,
        now,
        f"participant:{participant.id}",
        "certification.submit",
        certification_id=cert.id,
        target_date=target.isoformat(),
        duplicate_of=duplicate_of,
    )
    return cert


def review(
    s: Session, cert_id: int, approve: bool, reason: str | None, now: datetime
) -> StudyCertification:
    cert = s.get(StudyCertification, cert_id)
    if cert is None:
        raise DomainError("NOT_FOUND", "인증을 찾을 수 없습니다.", 404)
    if cert.status is not CertStatus.PENDING:
        raise DomainError("ALREADY_REVIEWED", "이미 검수한 인증입니다.")
    reason = (reason or "").strip()
    if not approve and not reason:
        raise DomainError("REASON_REQUIRED", "반려 사유를 입력하세요.", 422)
    cert.status = CertStatus.APPROVED if approve else CertStatus.REJECTED
    cert.reject_reason = None if approve else reason[:500]
    cert.reviewed_at = now
    audit(
        s,
        now,
        "admin",
        "certification.review",
        certification_id=cert.id,
        approved=approve,
        reason=cert.reject_reason,
    )
    return cert


def pay_rewards(s: Session, day: date, now: datetime, params: EventParams) -> list[dict[str, int]]:
    """day 09:00 공시 시, 이전 날짜로 승인되고 아직 지급되지 않은 인증에 병더리움을 지급한다.

    지급 수량은 시세와 무관한 고정 수량(reward_coin_quantity)이며 매입금액 0원으로 편입한다.
    """
    certs = s.scalars(
        select(StudyCertification)
        .join(Participant)
        .where(
            StudyCertification.status == CertStatus.APPROVED,
            StudyCertification.rewarded_at.is_(None),
            StudyCertification.target_date < day,
            Participant.status != ParticipantStatus.DISQUALIFIED,
        )
        .order_by(StudyCertification.id)
    ).all()
    quantity = params.reward_coin_quantity
    paid: list[dict[str, int]] = []
    for cert in certs:
        holding = s.get(Holding, (cert.participant_id, COIN.code))
        if holding is None:
            holding = Holding(
                participant_id=cert.participant_id, code=COIN.code, quantity=0, cost=0
            )
            s.add(holding)
        holding.quantity += quantity
        cert.rewarded_at = now
        cert.reward_quantity = quantity
        paid.append(
            {
                "certification_id": cert.id,
                "participant_id": cert.participant_id,
                "quantity": quantity,
            }
        )
        audit(
            s,
            now,
            "system",
            "reward.pay",
            certification_id=cert.id,
            participant_id=cert.participant_id,
            code=COIN.code,
            quantity=quantity,
        )
    s.flush()
    return paid


def purge_images(
    s: Session, upload_dir: Path, now: datetime, calendar: EventCalendar, force: bool = False
) -> int:
    """개인정보: 이벤트 종료 후 인증 사진을 삭제한다(05-certification §4, 30일 이내)."""
    if not force and to_kst(now).date() <= calendar.end:
        raise DomainError("EVENT_NOT_ENDED", "이벤트 종료 후에 삭제할 수 있습니다.")
    certs = s.scalars(
        select(StudyCertification).where(StudyCertification.image_path.is_not(None))
    ).all()
    for cert in certs:
        assert cert.image_path is not None
        (upload_dir / cert.image_path).unlink(missing_ok=True)
        cert.image_path = None
    audit(s, now, "system", "certification.purge_images", count=len(certs))
    return len(certs)


def image_file(cert: StudyCertification, upload_dir: Path) -> Path | None:
    if cert.image_path is None:
        return None
    path = upload_dir / cert.image_path
    return path if path.is_file() else None
