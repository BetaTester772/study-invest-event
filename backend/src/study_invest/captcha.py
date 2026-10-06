"""봇 확인(Cloudflare Turnstile). 사이트 키·비밀 키가 없으면 확인하지 않는다(로컬 개발·테스트).

프론트엔드 위젯이 만든 토큰을 `X-Turnstile-Token` 헤더로 받아 Cloudflare siteverify로 확인한다.
토큰은 한 번만 쓸 수 있고 5분 뒤 만료된다. 사이트의 DNS·호스팅이 Cloudflare가 아니어도 된다(예: Route 53).
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Protocol

from .config import Settings

log = logging.getLogger("study_invest.captcha")

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
MAX_TOKEN_LENGTH = 2048
"""Cloudflare 문서상 토큰 최대 길이. 넘으면 siteverify에 보내지 않고 거절한다."""


class CaptchaUnavailable(Exception):
    """siteverify에 묻지 못했다(네트워크 오류·시간 초과·5xx). 토큰이 틀린 것과 구분한다."""


class CaptchaVerifier(Protocol):
    @property
    def site_key(self) -> str | None:
        """프론트엔드 위젯용 공개 키. None이면 봇 확인을 하지 않는다."""

    def verify(self, token: str, action: str) -> bool:
        """토큰이 유효하고 action이 맞으면 True. 확인할 수 없으면 CaptchaUnavailable."""


class NoCaptcha:
    """봇 확인을 하지 않는다(키 미설정)."""

    site_key: str | None = None

    def verify(self, token: str, action: str) -> bool:
        return True


@dataclass(frozen=True)
class TurnstileVerifier:
    """동기 HTTP 호출이라 스레드풀(동기 의존성)에서만 부른다."""

    site_key: str | None
    secret_key: str = field(repr=False)
    timeout: float = 5.0

    def verify(self, token: str, action: str) -> bool:
        if not token or len(token) > MAX_TOKEN_LENGTH:
            return False
        data = urllib.parse.urlencode({"secret": self.secret_key, "response": token}).encode()
        req = urllib.request.Request(SITEVERIFY_URL, data=data, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as res:
                body = json.load(res)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise CaptchaUnavailable(str(exc)) from exc
        if not body.get("success"):
            codes = body.get("error-codes") or []
            if "internal-error" in codes:
                raise CaptchaUnavailable("siteverify internal-error")
            log.info("봇 확인 실패: %s", codes)
            return False
        # 다른 화면(action)에서 받은 토큰을 돌려쓰지 못하게 한다. 우리 위젯은 모두 action을
        # 붙이므로 빈 action은 Cloudflare 테스트 키(QA 서버)의 더미 토큰뿐이다.
        if body.get("action") not in (action, ""):
            log.info("봇 확인 action 불일치: %r != %r", body.get("action"), action)
            return False
        return True


def make_captcha(settings: Settings) -> CaptchaVerifier:
    site, secret = settings.turnstile_site_key, settings.turnstile_secret_key
    if not site and not secret:
        return NoCaptcha()
    if not (site and secret):
        # 하나만 있으면 위젯이 안 뜨거나(사이트 키 없음) 확인을 못 해(비밀 키 없음) 모두 막힌다.
        raise ValueError(
            "STUDY_INVEST_TURNSTILE_SITE_KEY와 STUDY_INVEST_TURNSTILE_SECRET_KEY는 함께 설정하세요."
        )
    return TurnstileVerifier(site_key=site, secret_key=secret)
