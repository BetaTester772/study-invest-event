"""참가자 등록·로그인 (F-01, 06-abuse-risk §2). 1인 1계정은 학교 메일 인증으로 확인한다."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..event_calendar import EventCalendar, to_kst
from ..models import AuthSession, Participant, VerifyMethod
from ..normalize import (
    SchoolEmail,
    SchoolEmailError,
    normalize_identity,
    normalize_nickname,
    normalize_student_id,
    parse_school_email,
)
from ..params import INITIAL_CASH
from .common import DomainError, audit
from .email_verification import email_taken, ensure_email_free, registered_participant

_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}

STUDENT_ID = re.compile(r"[0-9]{10}")
"""학번 형식(숫자 10자리). api/schemas.py의 StudentId와 같다."""


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
    if calendar.is_ended(to_kst(now).date()):
        raise DomainError("REGISTRATION_CLOSED", "이벤트가 종료되어 참가 신청을 받지 않습니다.")


def ensure_privacy_consent(consent: bool) -> None:
    if not consent:
        raise DomainError(
            "PRIVACY_CONSENT_REQUIRED",
            "개인정보(학교 메일·이름·학번·학과) 수집·이용에 동의해야 참가할 수 있습니다.",
            422,
        )


@dataclass(frozen=True)
class Profile:
    """참가자 신상 정보(관리자만 본다). 값은 API 스키마에서 정규화·검사된 것."""

    name: str
    student_id: str
    department: str


def _student_id_taken() -> DomainError:
    return DomainError(
        "STUDENT_ID_TAKEN",
        "이미 다른 계정에 등록된 학번입니다. 1인 1계정만 허용됩니다."
        " 본인 학번이 맞다면 운영진에게 문의하세요.",
    )


def ensure_student_id_free(s: Session, student_id: str, exclude_id: int | None = None) -> None:
    query = select(Participant.id).where(Participant.student_id == student_id)
    if exclude_id is not None:
        query = query.where(Participant.id != exclude_id)
    if s.scalar(query):
        raise _student_id_taken()


def _ensure_unique(
    s: Session,
    email: SchoolEmail,
    profile: Profile,
    nickname: str | None,
    exclude_id: int | None = None,
) -> None:
    """유니크 제약 위반 원인을 업무 오류로 알려 준다(동시 요청은 제약이 판정).

    exclude_id: 자기 자신(재인증하는 계정)이 이미 쓰는 메일·학번은 충돌로 보지 않는다.
    """
    ensure_email_free(s, email, exclude_id)
    ensure_student_id_free(s, profile.student_id, exclude_id)
    if nickname is not None and s.scalar(
        select(Participant.id).where(Participant.nickname == nickname)
    ):
        raise DomainError("NICKNAME_TAKEN", "이미 사용 중인 닉네임입니다.")


def register(
    s: Session,
    email: SchoolEmail,
    profile: Profile,
    nickname: str,
    password: str,
    now: datetime,
    calendar: EventCalendar,
    *,
    verified: bool = True,
) -> tuple[Participant, str]:
    """참가 등록. 중도 참가도 시드는 같다(INITIAL_CASH).

    verified: 인증 코드로 email을 확인했는지. 메일 인증을 끈 운영이면 False(미인증으로 가입하고
    관리자가 확인한다). email은 어느 쪽이든 비밀번호 재설정 코드를 받는 주소로 저장한다.
    """
    ensure_registration_open(now, calendar)
    nickname = normalize_nickname(nickname)
    _ensure_unique(s, email, profile, nickname)
    participant = Participant(
        email=email.canonical,
        verified_at=now if verified else None,
        verified_via=VerifyMethod.EMAIL if verified else None,
        name=profile.name,
        student_id=profile.student_id,
        department=profile.department,
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
        _ensure_unique(s, email, profile, nickname)
        raise DomainError(
            "CONFLICT", "같은 요청이 동시에 처리되어 충돌했습니다. 다시 시도하세요."
        ) from exc
    audit(s, now, f"participant:{participant.id}", "participant.register", nickname=nickname)
    return participant, issue_token(s, participant, now)


def verify_email(
    s: Session,
    participant: Participant,
    email: SchoolEmail,
    profile: Profile | None,
    now: datetime,
) -> None:
    """미인증 참가자(메일 인증 도입 전 가입, 또는 메일 인증을 끈 채 가입)의 학교 메일 인증.

    메일을 인증한 주소로 바꾸고, profile이 있으면 이름·학번·학과도 채운다(도입 전 계정).
    자기 계정이 이미 쓰는 메일·학번은 그대로 써도 된다.
    """
    if participant.verified:
        raise DomainError("ALREADY_VERIFIED", "이미 인증을 마쳤습니다.")
    ensure_email_free(s, email, participant.id)
    if profile is not None:
        ensure_student_id_free(s, profile.student_id, participant.id)
    try:
        with s.begin_nested():
            participant.email = email.canonical
            participant.verified_at = now
            participant.verified_via = VerifyMethod.EMAIL
            if profile is not None:
                participant.name = profile.name
                participant.student_id = profile.student_id
                participant.department = profile.department
    except IntegrityError as exc:  # 다른 참가자가 같은 메일·학번으로 동시에 인증
        if s.scalar(select(Participant.id).where(Participant.email == email.canonical)):
            raise email_taken() from exc
        raise _student_id_taken() from exc
    audit(s, now, f"participant:{participant.id}", "participant.verify_email")


def set_verified(s: Session, participant: Participant, verified: bool, now: datetime) -> None:
    """관리자가 인증 처리하거나 취소한다(메일 인증을 끈 운영에서 학번·이름을 확인한 뒤)."""
    if participant.verified == verified:
        return
    before = participant.verified_via.value if participant.verified_via else None
    participant.verified_at = now if verified else None
    participant.verified_via = VerifyMethod.ADMIN if verified else None
    audit(
        s,
        now,
        "admin",
        "participant.verify" if verified else "participant.unverify",
        participant_id=participant.id,
        before=before,
    )


def login(s: Session, identity: str, password: str, now: datetime) -> tuple[Participant, str]:
    """학번으로 로그인한다. 학교 메일(두 도메인 어느 쪽이든)이나 메일 인증 도입 전 식별자도 받는다.

    입력에 맞는 계정을 학번 → 학교 메일 → 예전 식별자 순으로 찾고, 비밀번호가 맞는 첫 계정으로
    로그인한다(예전 식별자가 다른 사람의 학번과 같은 숫자여도 각자 로그인할 수 있다).
    """
    candidates: list[Participant] = []
    student_id = normalize_student_id(identity)
    if STUDENT_ID.fullmatch(student_id):
        candidates += s.scalars(select(Participant).where(Participant.student_id == student_id))
    try:
        email = parse_school_email(identity)
    except SchoolEmailError:
        pass
    else:
        candidates += s.scalars(select(Participant).where(Participant.email == email.canonical))
    candidates += s.scalars(
        select(Participant).where(Participant.identity == normalize_identity(identity))
    )
    for participant in candidates:
        if verify_password(password, participant.password_hash):
            return participant, issue_token(s, participant, now)
    raise DomainError("INVALID_CREDENTIALS", "학번 또는 비밀번호가 올바르지 않습니다.", 401)


def reset_password(
    s: Session, email: SchoolEmail, password: str, now: datetime
) -> tuple[Participant, str]:
    """학교 메일 코드로 확인한 참가자의 비밀번호를 바꾼다. 다른 기기의 로그인은 모두 끊는다."""
    participant = registered_participant(s, email)
    participant.password_hash = hash_password(password)
    s.execute(delete(AuthSession).where(AuthSession.participant_id == participant.id))
    audit(s, now, f"participant:{participant.id}", "participant.reset_password")
    return participant, issue_token(s, participant, now)
