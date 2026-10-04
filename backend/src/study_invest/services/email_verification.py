"""학교 메일 인증 코드 (06-abuse-risk §2, 1인 1계정).

skku.edu·g.skku.edu 주소만 받고, 같은 ID의 두 도메인은 한 사람으로 본다(normalize.py).
코드는 6자리 숫자, 10분 유효, 5번 틀리면 무효. 메일마다 가장 최근 코드만 쓸 수 있다.

유효시간·재요청 간격의 시각(now)은 테스트 시계 배속(STUDY_INVEST_TIME_SCALE)과 상관없이 실제
시각이다(라우트가 RealNowDep을 넘긴다). 배속을 따르면 10분이 몇십 초로 줄어들기 때문이다.
"""

from __future__ import annotations

import hashlib
import hmac
import math
import secrets
from datetime import datetime, timedelta

from sqlalchemy import delete, func, or_, select, text, update
from sqlalchemy.orm import Session

from ..event_calendar import EventCalendar, to_kst
from ..models import CodePurpose, EmailVerification, Participant
from ..normalize import SchoolEmail, SchoolEmailError, parse_school_email
from .common import DomainError, audit

CODE_TTL = timedelta(minutes=10)
RESEND_COOLDOWN = timedelta(seconds=60)
MAX_ATTEMPTS = 5
MAX_CODES_PER_EMAIL = 5
"""메일 하나에 24시간 동안 보낼 수 있는 코드 수."""
WINDOW = timedelta(hours=24)

CODE_LOCK_KEY = 7_720_261_007
"""인증 코드 발급 직렬화용 PostgreSQL advisory lock 키(common.BATCH_LOCK_KEY와 다르게)."""

_EMAIL_ERRORS = {
    "INVALID_EMAIL": "메일 주소 형식이 올바르지 않습니다.",
    "EMAIL_DOMAIN_NOT_ALLOWED": "학교 메일(@skku.edu 또는 @g.skku.edu)만 사용할 수 있습니다.",
}


class InvalidCode(DomainError):
    """틀린 코드. 요청은 실패해도 틀린 횟수는 커밋해야 한다(라우트가 커밋 후 다시 던진다)."""

    def __init__(self, remaining: int) -> None:
        super().__init__(
            "INVALID_CODE",
            f"인증 코드가 맞지 않습니다. {remaining}번 더 시도할 수 있습니다."
            if remaining
            else "인증 코드가 맞지 않습니다. 코드를 다시 받아 주세요.",
            400,
        )


def parse(raw: str) -> SchoolEmail:
    try:
        return parse_school_email(raw)
    except SchoolEmailError as exc:
        raise DomainError(exc.code, _EMAIL_ERRORS[exc.code], 422) from exc


def _hash(canonical: str, code: str) -> str:
    return hashlib.sha256(f"{canonical}:{code}".encode()).hexdigest()


def email_taken() -> DomainError:
    return DomainError(
        "EMAIL_TAKEN",
        "이미 참가한 학교 메일입니다. 1인 1계정만 허용됩니다"
        " (@skku.edu와 @g.skku.edu는 같은 계정으로 봅니다).",
    )


def ensure_email_free(s: Session, email: SchoolEmail, exclude_id: int | None = None) -> None:
    """다른 계정(exclude_id 제외)이 이 메일을 쓰고 있으면 EMAIL_TAKEN."""
    query = select(Participant.id).where(Participant.email == email.canonical)
    if exclude_id is not None:
        query = query.where(Participant.id != exclude_id)
    if s.scalar(query):
        raise email_taken()


def registered_participant(s: Session, email: SchoolEmail) -> Participant:
    """학교 메일로 가입(또는 재인증)한 참가자. 없으면 EMAIL_NOT_REGISTERED."""
    participant = s.scalars(select(Participant).where(Participant.email == email.canonical)).first()
    if participant is None:
        raise DomainError(
            "EMAIL_NOT_REGISTERED",
            "이 학교 메일로 가입한 계정이 없습니다. 메일 주소를 확인하거나 참가 신청을 하세요.",
            404,
        )
    return participant


def request_code(
    s: Session,
    raw_email: str,
    now: datetime,
    daily_limit: int,
    purpose: CodePurpose = CodePurpose.VERIFY,
    requester_id: int | None = None,
) -> tuple[SchoolEmail, EmailVerification, str]:
    """새 코드를 만든다. 반환한 코드를 메일로 보내는 것은 호출자 몫이다(커밋 후, 연결 반납 후).

    VERIFY는 다른 사람의 인증된 계정이 쓰지 않는 메일, RESET_PASSWORD는 가입한 메일에만 보낸다.
    requester_id: 로그인한 본인의 요청이면 그 계정(자기 메일이면 인증 여부와 상관없이 보낸다).
    재요청 대기·하루 한도는 용도와 상관없이 메일마다 센다(메일함 폭탄 방지). 발송에 실패해도
    기록은 남아 한도에 센다(SMTP 장애 중 무한 재시도 방지).
    """
    email = parse(raw_email)
    # 재요청 대기·하루 한도 검사와 발급을 직렬화한다. 그러지 않으면 동시 요청이 둘 다 "최근 코드
    # 없음"을 보고 코드를 여러 통 보내거나 전체 한도를 넘는다. 트랜잭션 잠금이라 호출자가 커밋
    # (메일 발송 전)하면 풀린다. 발급은 드물고 잠금 구간이 짧아 전체를 한 줄로 세워도 충분하다.
    if s.get_bind().dialect.name == "postgresql":
        s.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": CODE_LOCK_KEY})
    if purpose is CodePurpose.VERIFY:
        # 다른 사람의 인증된 계정이 쓰는 메일이면 거부. 미인증 계정의 메일이면 보낸다(그 주인이
        # 나중에 인증할 수 있게). 다른 사람은 그 메일로 가입·인증할 수 없다(사용할 때 다시 검사).
        owner = s.scalars(select(Participant).where(Participant.email == email.canonical)).first()
        if owner is not None and owner.id != requester_id and owner.verified:
            raise email_taken()
    else:
        registered_participant(s, email)
    recent = s.scalars(
        select(EmailVerification.created_at)
        .where(
            EmailVerification.email == email.canonical, EmailVerification.created_at > now - WINDOW
        )
        .order_by(EmailVerification.created_at.desc())
    ).all()
    if recent and now - recent[0] < RESEND_COOLDOWN:
        wait = math.ceil((recent[0] + RESEND_COOLDOWN - now).total_seconds())
        raise DomainError("CODE_RECENTLY_SENT", f"{wait}초 뒤에 다시 요청할 수 있습니다.", 429)
    if len(recent) >= MAX_CODES_PER_EMAIL:
        raise DomainError(
            "TOO_MANY_CODES", "인증 코드를 너무 많이 요청했습니다. 내일 다시 시도하세요.", 429
        )
    sent = s.scalar(
        select(func.count())
        .select_from(EmailVerification)
        .where(EmailVerification.created_at > now - WINDOW)
    )
    if (sent or 0) >= daily_limit:
        raise DomainError(
            "MAIL_QUOTA_EXCEEDED",
            "오늘 보낼 수 있는 인증 메일을 모두 보냈습니다. 운영진에게 문의하세요.",
            503,
        )
    code = f"{secrets.randbelow(10**6):06d}"
    row = EmailVerification(
        email=email.canonical,
        purpose=purpose,
        code_hash=_hash(email.canonical, code),
        created_at=now,
        expires_at=now + CODE_TTL,
        attempts=0,
    )
    s.add(row)
    return email, row, code


def message(code: str, purpose: CodePurpose = CodePurpose.VERIFY) -> tuple[str, str]:
    minutes = int(CODE_TTL.total_seconds() // 60)
    if purpose is CodePurpose.RESET_PASSWORD:
        subject = f"[공부장려 모의투자] 비밀번호 재설정 코드 {code}"
        guide = "비밀번호 재설정 화면에 위 6자리 코드를 입력하세요."
        ignore = "직접 요청하지 않았다면 이 메일은 무시하세요. 비밀번호는 바뀌지 않습니다."
    else:
        subject = f"[공부장려 모의투자] 학교 메일 인증 코드 {code}"
        guide = "참가 신청(또는 학교 메일 인증) 화면에 위 6자리 코드를 입력하세요."
        ignore = "직접 요청하지 않았다면 이 메일은 무시하세요."
    body = (
        f"인증 코드: {code}\n\n"
        f"{guide} 코드는 {minutes}분 동안 유효합니다.\n"
        f"{ignore} 코드를 다른 사람에게 알려 주지 마세요.\n"
    )
    return subject, body


def consume_code(
    s: Session,
    raw_email: str,
    code: str,
    now: datetime,
    purpose: CodePurpose = CodePurpose.VERIFY,
) -> SchoolEmail:
    """코드를 확인하고 사용 처리한다. 틀리면 InvalidCode(틀린 횟수는 세션에 반영됨).

    메일마다 가장 최근 코드만 본다. 그 코드가 다른 용도로 받은 것이면 만료로 본다.
    """
    email = parse(raw_email)
    row = s.scalars(
        select(EmailVerification)
        .where(EmailVerification.email == email.canonical)
        .order_by(EmailVerification.id.desc())
        .limit(1)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()
    if (
        row is None
        or row.purpose is not purpose
        or row.consumed_at is not None
        or row.expires_at <= now
    ):
        raise DomainError(
            "CODE_EXPIRED", "인증 코드가 없거나 만료되었습니다. 코드를 다시 받아 주세요.", 400
        )
    if row.attempts >= MAX_ATTEMPTS:
        raise DomainError(
            "CODE_ATTEMPTS_EXCEEDED",
            "인증 코드를 너무 많이 틀렸습니다. 코드를 다시 받아 주세요.",
            400,
        )
    if not hmac.compare_digest(row.code_hash, _hash(email.canonical, code.strip())):
        row.attempts += 1
        raise InvalidCode(MAX_ATTEMPTS - row.attempts)
    row.consumed_at = now
    return email


def purge(
    s: Session, now: datetime, calendar: EventCalendar, force: bool = False
) -> tuple[int, int]:
    """개인정보: 이벤트 종료 후 참가자의 학교 메일·이름·학번·학과와 인증 코드 기록을 지운다.

    인증 시각(verified_at)은 남겨 계속 인증된 계정으로 본다. (참가자 수, 코드 수).
    """
    if not force and not calendar.is_ended(to_kst(now).date()):
        raise DomainError("EVENT_NOT_ENDED", "이벤트 종료 후에 삭제할 수 있습니다.")
    has_info = or_(
        Participant.email.is_not(None),
        Participant.email_address.is_not(None),
        Participant.name.is_not(None),
        Participant.student_id.is_not(None),
        Participant.department.is_not(None),
    )
    participants = s.scalar(select(func.count()).select_from(Participant).where(has_info))
    codes = s.scalar(select(func.count()).select_from(EmailVerification))
    s.execute(
        update(Participant)
        .where(has_info)
        .values(email=None, email_address=None, name=None, student_id=None, department=None)
    )
    s.execute(delete(EmailVerification))
    audit(
        s, now, "system", "participant.purge_personal_info", participants=participants, codes=codes
    )
    return participants or 0, codes or 0
