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
from zxcvbn import zxcvbn  # type: ignore[import-untyped]

from ..event_calendar import EventCalendar, to_kst
from ..models import AuthSession, Participant, VerifyMethod
from ..normalize import (
    SchoolEmail,
    SchoolEmailError,
    mask_value,
    normalize_identity,
    normalize_nickname,
    normalize_student_id,
    parse_school_email,
)
from ..params import INITIAL_CASH
from .common import DomainError, audit
from .email_verification import email_taken, ensure_email_free

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


def session_id(token: str) -> str:
    """로그 추적용 로그인 세션 ID. 토큰 해시(DB 키)의 앞 12자라 토큰을 복원할 수 없고, 같은
    토큰이면 항상 같다. 로그인할 때 발급 로그와 이후 모든 요청 로그가 이 값으로 이어진다."""
    return _token_hash(token)[:12]


def issue_token(s: Session, participant: Participant, now: datetime) -> str:
    token = secrets.token_urlsafe(32)
    s.add(AuthSession(token_hash=_token_hash(token), participant_id=participant.id, created_at=now))
    return token


def participant_by_token(s: Session, token: str) -> Participant | None:
    session = s.get(AuthSession, _token_hash(token))
    return s.get(Participant, session.participant_id) if session else None


def revoke_token(s: Session, token: str) -> None:
    s.execute(delete(AuthSession).where(AuthSession.token_hash == _token_hash(token)))


MIN_PASSWORD_SCORE = 2
"""zxcvbn 점수(0~4) 하한. 2 미만은 흔한 비밀번호·키보드 패턴·연속 숫자처럼 금방 맞힐 수 있다."""
PASSWORD_CHECK_CHARS = 100
"""zxcvbn은 긴 입력에서 느려질 수 있어 앞부분만 본다(비밀번호는 최대 128자)."""


def ensure_strong_password(password: str, *personal: str | None) -> None:
    """너무 쉬운 비밀번호를 거부한다(zxcvbn). personal: 학번·이름·닉네임·메일 등 그 사람의 정보.

    그 정보가 들어간 비밀번호(예: 학번 그대로, 이름+학번)도 쉽게 맞힐 수 있는 것으로 본다.
    """
    hints = [value for value in personal if value]
    if zxcvbn(password[:PASSWORD_CHECK_CHARS], user_inputs=hints)["score"] < MIN_PASSWORD_SCORE:
        raise DomainError(
            "WEAK_PASSWORD",
            "너무 쉬운 비밀번호입니다. 흔한 단어·연속된 숫자·학번·이름을 피하고 더 길게 정하세요.",
            422,
            context={"password_length": len(password), "min_score": MIN_PASSWORD_SCORE},
        )


def _personal(
    email: str | None, name: str | None, student_id: str | None, nickname: str | None
) -> tuple[str | None, ...]:
    local = email.partition("@")[0] if email else None
    return (email, local, name, student_id, nickname)


def ensure_registration_open(now: datetime, calendar: EventCalendar) -> None:
    if calendar.is_ended(to_kst(now).date()):
        raise DomainError("REGISTRATION_CLOSED", "이벤트가 종료되어 참가 신청을 받지 않습니다.")


def ensure_verification_open(now: datetime, calendar: EventCalendar) -> None:
    """이벤트가 끝나면 학교 메일 인증을 받지 않는다. 종료 후 개인정보를 지운(purge) 뒤 미인증
    계정이 메일·학번 등을 다시 등록해 재수집되지 않게 한다."""
    if calendar.is_ended(to_kst(now).date()):
        raise DomainError("EVENT_ENDED", "이벤트가 종료되어 학교 메일 인증을 받지 않습니다.")


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


def _student_id_taken(student_id: str = "") -> DomainError:
    return DomainError(
        "STUDENT_ID_TAKEN",
        "이미 다른 계정에 등록된 학번입니다. 1인 1계정만 허용됩니다."
        " 본인 학번이 맞다면 운영진에게 문의하세요.",
        context={"student_id": mask_value(student_id)},
    )


def ensure_student_id_free(s: Session, student_id: str, exclude_id: int | None = None) -> None:
    query = select(Participant.id).where(Participant.student_id == student_id)
    if exclude_id is not None:
        query = query.where(Participant.id != exclude_id)
    if s.scalar(query):
        raise _student_id_taken(student_id)


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
        raise DomainError(
            "NICKNAME_TAKEN", "이미 사용 중인 닉네임입니다.", context={"nickname": nickname}
        )


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
    ensure_strong_password(
        password, *_personal(email.address, profile.name, profile.student_id, nickname)
    )
    _ensure_unique(s, email, profile, nickname)
    participant = Participant(
        email=email.canonical,
        email_address=email.address,
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
            "CONFLICT",
            "같은 요청이 동시에 처리되어 충돌했습니다. 다시 시도하세요.",
            context={"during": "register", "db_error": type(exc.orig).__name__},
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
    """학교 메일 코드로 인증한다. 메일 코드로 아직 인증하지 않은 계정만(미인증 또는 관리자 인증).

    관리자 인증은 메일을 확인하지 않으므로, 잘못 적은 메일도 여기서 바로잡을 수 있다. 메일 코드로
    인증된 계정은 등록 메일이 본인 것으로 확인됐으므로 바꿀 수 없다(세션 탈취 → 메일 변경 →
    비밀번호 재설정으로 계정을 가져가는 경로 차단).
    메일을 인증한 주소로 바꾸고, profile이 있으면 이름·학번·학과도 채운다(도입 전 계정).
    자기 계정이 이미 쓰는 메일·학번은 그대로 써도 된다.
    """
    if participant.email_verified:
        raise DomainError("ALREADY_VERIFIED", "이미 학교 메일 인증을 마쳤습니다.")
    ensure_email_free(s, email, participant.id)
    if profile is not None:
        ensure_student_id_free(s, profile.student_id, participant.id)
    try:
        with s.begin_nested():
            participant.email = email.canonical
            participant.email_address = email.address
            participant.verified_at = now
            participant.verified_via = VerifyMethod.EMAIL
            if profile is not None:
                participant.name = profile.name
                participant.student_id = profile.student_id
                participant.department = profile.department
    except IntegrityError as exc:  # 다른 참가자가 같은 메일·학번으로 동시에 인증
        if s.scalar(
            select(Participant.id).where(
                Participant.email == email.canonical, Participant.id != participant.id
            )
        ):
            raise email_taken(email) from exc
        raise _student_id_taken(
            profile.student_id if profile else participant.student_id or ""
        ) from exc
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


def _accounts(s: Session, identity: str) -> list[Participant]:
    """입력에 맞는 계정: 학번 → 학교 메일(두 도메인 어느 쪽이든) → 메일 인증 도입 전 식별자 순."""
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
    return candidates


def login(s: Session, identity: str, password: str, now: datetime) -> tuple[Participant, str]:
    """학번으로 로그인한다. 학교 메일(두 도메인 어느 쪽이든)이나 메일 인증 도입 전 식별자도 받는다.

    입력에 맞는 계정을 학번 → 학교 메일 → 예전 식별자 순으로 찾고, 비밀번호가 맞는 첫 계정으로
    로그인한다(예전 식별자가 다른 사람의 학번과 같은 숫자여도 각자 로그인할 수 있다).
    """
    candidates = 0
    for participant in _accounts(s, identity):
        candidates += 1
        stored = participant.password_hash
        if not verify_password(password, stored):
            continue
        # 비밀번호 확인(scrypt, 느림) 동안 재설정이 끝났을 수 있다. 행을 공유 잠금으로 다시 읽어
        # 그대로일 때만 토큰을 만든다. 재설정의 UPDATE는 이 잠금을 기다리고, 그 뒤의 로그인 삭제가
        # 이 토큰까지 지운다. 그러지 않으면 옛 비밀번호 로그인이 재설정 뒤에도 살아남는다.
        current = s.scalars(
            select(Participant)
            .where(Participant.id == participant.id)
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        ).one()
        if current.password_hash != stored:
            continue
        return current, issue_token(s, current, now)
    raise DomainError(
        "INVALID_CREDENTIALS",
        "학번 또는 비밀번호가 올바르지 않습니다.",
        401,
        context={
            "why": "wrong_password" if candidates else "no_such_account",
            "identity": mask_value(identity),
            "matched_accounts": candidates,
        },
    )


def account_for_reset(s: Session, identity: str) -> Participant:
    """비밀번호 재설정 대상: 학번(또는 학교 메일)으로 찾은, 학교 메일이 등록된 계정.

    코드는 항상 이 계정의 등록 메일로만 보낸다. 다른 주소로 받을 수 있으면 남의 학번만 알아도
    계정을 가져갈 수 있다.
    """
    for participant in _accounts(s, identity):
        if participant.email_address:
            return participant
    raise DomainError(
        "ACCOUNT_NOT_FOUND",
        "이 학번으로 가입했거나 학교 메일을 등록한 계정이 없습니다. 학번을 확인하거나 운영진에게"
        " 문의하세요.",
        404,
        context={"identity": mask_value(identity)},
    )


def reset_password(
    s: Session, participant: Participant, password: str, now: datetime
) -> tuple[Participant, str]:
    """등록 메일 코드로 확인한 참가자의 비밀번호를 바꾼다. 다른 기기의 로그인은 모두 끊는다."""
    ensure_strong_password(
        password,
        *_personal(
            participant.email_address,
            participant.name,
            participant.student_id,
            participant.nickname,
        ),
        participant.identity,
    )
    participant.password_hash = hash_password(password)
    # UPDATE를 먼저 보내 행 잠금을 잡는다. 진행 중인 로그인(공유 잠금)이 끝나길 기다린 뒤라
    # 아래 DELETE가 그 로그인의 토큰까지 지운다(login 참고).
    s.flush()
    s.execute(delete(AuthSession).where(AuthSession.participant_id == participant.id))
    audit(s, now, f"participant:{participant.id}", "participant.reset_password")
    return participant, issue_token(s, participant, now)
