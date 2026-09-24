"""FastAPI 의존성: 앱 상태, DB 세션, 시계, 인증."""

from __future__ import annotations

import random
import secrets
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session, sessionmaker

from ..config import Settings
from ..event_calendar import EventCalendar
from ..models import Participant
from ..services import auth
from ..services.common import DomainError


@dataclass
class AppState:
    settings: Settings
    session_factory: sessionmaker[Session]
    calendar: EventCalendar
    clock: Callable[[], datetime]
    rng: random.Random


def get_state(request: Request) -> AppState:
    state: AppState = request.app.state.study_invest
    return state


StateDep = Annotated[AppState, Depends(get_state)]


def get_session(state: StateDep) -> Iterator[Session]:
    """요청 단위 세션. 라우트가 명시적으로 커밋하고, 예외 시 롤백한다."""
    with state.session_factory() as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise


SessionDep = Annotated[Session, Depends(get_session)]


def get_now(state: StateDep) -> datetime:
    return state.clock()


NowDep = Annotated[datetime, Depends(get_now)]


def bearer_token(authorization: Annotated[str | None, Header()] = None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None
    return None


TokenDep = Annotated[str | None, Depends(bearer_token)]


def optional_participant(s: SessionDep, token: TokenDep) -> Participant | None:
    return auth.participant_by_token(s, token) if token else None


def current_participant(
    participant: Annotated[Participant | None, Depends(optional_participant)],
) -> Participant:
    if participant is None:
        raise DomainError("UNAUTHORIZED", "로그인이 필요합니다.", 401)
    return participant


MeDep = Annotated[Participant, Depends(current_participant)]
OptionalMeDep = Annotated[Participant | None, Depends(optional_participant)]


def require_admin(state: StateDep, x_admin_key: Annotated[str | None, Header()] = None) -> None:
    expected = state.settings.admin_key
    if not expected or not x_admin_key or not secrets.compare_digest(x_admin_key, expected):
        raise DomainError("UNAUTHORIZED", "관리자 키가 올바르지 않습니다.", 401)
