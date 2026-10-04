"""참가자 등록·로그인 (F-01, 06-abuse-risk §2). 1인 1계정은 학교 메일 인증으로 확인한다."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..event_calendar import EventCalendar, to_kst
from ..models import AuthSession, Participant
from ..normalize import (
    SchoolEmail,
    SchoolEmailError,
    normalize_identity,
    normalize_nickname,
    parse_school_email,
)
from ..params import INITIAL_CASH
from .common import DomainError, audit
from .email_verification import email_taken, ensure_email_free

_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), **_SCRYPT)
    return hmac.compare_digest(digest.hex(), digest_hex)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_token(s: Session, participant: Participant, now: datetime) -> str:
    token = secrets.token_urlsafe(32)
    s.add(AuthSession(token_hash=_token_hash(token), participant_id=participant.id, created_at=now))
    return token


def participant_by_token(s: Session, token: str) -> Participant | None:
    session = s.get(AuthSession, _token_hash(token))
    return s.get(Participant, session.participant_id) if session else None


def revoke_token(s: Session, token: str) -> None:
    s.execute(delete(AuthSession).where(AuthSession.token_hash == _token_hash(token)))


def ensure_registration_open(now: datetime, calendar: EventCalendar) -> None:
    if to_kst(now).date() > calendar.end:
        raise DomainError("REGISTRATION_CLOSED", "이벤트가 종료되어 참가 신청을 받지 않습니다.")


def ensure_privacy_consent(consent: bool) -> None:
    if not consent:
        raise DomainError(
            "PRIVACY_CONSENT_REQUIRED",
            "개인정보(학교 메일) 수집·이용에 동의해야 참가할 수 있습니다.",
            422,
        )


def register(
    s: Session,
    email: SchoolEmail,
    nickname: str,
    password: str,
    now: datetime,
    calendar: EventCalendar,
) -> tuple[Participant, str]:
    """참가 등록. email은 인증 코드로 확인한 학교 메일. 중도 참가도 시드는 같다(INITIAL_CASH)."""
    ensure_registration_open(now, calendar)
    nickname = normalize_nickname(nickname)
    ensure_email_free(s, email)
    if s.scalar(select(Participant.id).where(Participant.nickname == nickname)):
        raise DomainError("NICKNAME_TAKEN", "이미 사용 중인 닉네임입니다.")
    participant = Participant(
        email=email.canonical,
        email_verified_at=now,
        nickname=nickname,
        password_hash=hash_password(password),
        cash=INITIAL_CASH,
        joined_at=now,
    )
    try:
        # 동시 등록은 앞선 중복 검사를 둘 다 통과할 수 있다 → 유니크 제약으로 판정
        with s.begin_nested():
            s.add(participant)
    except IntegrityError as exc:
        ensure_email_free(s, email)
        raise DomainError("NICKNAME_TAKEN", "이미 사용 중인 닉네임입니다.") from exc
    audit(s, now, f"participant:{participant.id}", "participant.register", nickname=nickname)
    return participant, issue_token(s, participant, now)


def verify_email(s: Session, participant: Participant, email: SchoolEmail, now: datetime) -> None:
    """메일 인증 도입 전에 가입한 참가자의 재인증. 인증하면 학교 메일로도 로그인할 수 있다."""
    if participant.email_verified_at is not None:
        raise DomainError("ALREADY_VERIFIED", "이미 학교 메일 인증을 마쳤습니다.")
    ensure_email_free(s, email)
    try:
        with s.begin_nested():
            participant.email = email.canonical
            participant.email_verified_at = now
    except IntegrityError as exc:  # 다른 참가자가 같은 메일로 동시에 인증
        raise email_taken() from exc
    audit(s, now, f"participant:{participant.id}", "participant.verify_email")


def login(s: Session, identity: str, password: str, now: datetime) -> tuple[Participant, str]:
    """학교 메일(@skku.edu·@g.skku.edu 어느 쪽이든) 또는 인증 도입 전 식별자로 로그인한다."""
    participant = None
    try:
        email = parse_school_email(identity)
    except SchoolEmailError:
        pass
    else:
        participant = s.scalars(
            select(Participant).where(Participant.email == email.canonical)
        ).first()
    if participant is None:
        participant = s.scalars(
            select(Participant).where(Participant.identity == normalize_identity(identity))
        ).first()
    if participant is None or not verify_password(password, participant.password_hash):
        raise DomainError(
            "INVALID_CREDENTIALS", "학교 메일 또는 비밀번호가 올바르지 않습니다.", 401
        )
    return participant, issue_token(s, participant, now)
