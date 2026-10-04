"""인증 코드 확인 라우트 도우미."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from ..normalize import SchoolEmail
from ..services import email_verification


def consume_code(s: Session, email: str, code: str, now: datetime) -> SchoolEmail:
    """코드를 확인한다. 반드시 요청의 첫 DB 쓰기여야 한다.

    틀린 코드면 틀린 횟수만 커밋하고 다시 던진다(오류 응답은 세션을 롤백하므로 그냥 두면
    횟수가 남지 않아 무제한으로 맞혀 볼 수 있다).
    """
    try:
        return email_verification.consume_code(s, email, code, now)
    except email_verification.InvalidCode:
        s.commit()
        raise
