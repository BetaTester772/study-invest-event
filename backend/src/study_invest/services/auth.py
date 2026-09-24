"""참가자 등록·로그인 (F-01, 06-abuse-risk §2)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..event_calendar import EventCalendar, to_kst
from ..models import AuthSession, Participant
from ..params import INITIAL_CASH
from .common import DomainError, audit

_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}


def normalize_identity(identity: str) -> str:
    """1인 1계정 식별자 정규화: 앞뒤 공백 제거, 대소문자 무시."""
    return identity.strip().casefold()


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


def register(
    s: Session,
    identity: str,
    nickname: str,
    password: str,
    now: datetime,
    calendar: EventCalendar,
) -> tuple[Participant, str]:
    """참가 등록. 중도 참가도 시드는 동일하다(INITIAL_CASH)."""
    if to_kst(now).date() > calendar.end:
        raise DomainError("REGISTRATION_CLOSED", "이벤트가 종료되어 참가 신청을 받지 않습니다.")
    norm = normalize_identity(identity)
    nickname = nickname.strip()
    if not norm:
        raise DomainError("INVALID_IDENTITY", "식별자를 입력하세요.", 422)
    if s.scalar(select(Participant.id).where(Participant.identity == norm)):
        raise DomainError("IDENTITY_TAKEN", "이미 등록된 식별자입니다. 1인 1계정만 허용됩니다.")
    if s.scalar(select(Participant.id).where(Participant.nickname == nickname)):
        raise DomainError("NICKNAME_TAKEN", "이미 사용 중인 닉네임입니다.")
    participant = Participant(
        identity=norm,
        nickname=nickname,
        password_hash=hash_password(password),
        cash=INITIAL_CASH,
        joined_at=now,
    )
    s.add(participant)
    s.flush()
    audit(s, now, f"participant:{participant.id}", "participant.register", nickname=nickname)
    return participant, issue_token(s, participant, now)


def login(s: Session, identity: str, password: str, now: datetime) -> tuple[Participant, str]:
    participant = s.scalars(
        select(Participant).where(Participant.identity == normalize_identity(identity))
    ).first()
    if participant is None or not verify_password(password, participant.password_hash):
        raise DomainError("INVALID_CREDENTIALS", "식별자 또는 비밀번호가 올바르지 않습니다.", 401)
    return participant, issue_token(s, participant, now)
