"""인증 메일 발송. SMTP 설정이 없으면 로그로 남긴다(로컬 개발)."""

from __future__ import annotations

import logging
import smtplib
import ssl
from dataclasses import dataclass, field
from email.headerregistry import Address
from email.message import EmailMessage
from typing import Literal, Protocol

from .config import Settings

log = logging.getLogger("study_invest.mail")

SENDER_NAME = "공부장려 모의투자"


class Mailer(Protocol):
    def send(self, to: str, subject: str, body: str) -> None:
        """보내지 못하면 예외를 던진다."""


@dataclass(frozen=True)
class SmtpMailer:
    """요청마다 SMTP에 새로 연결한다. 동기 I/O라 스레드풀(동기 라우트)에서만 부른다."""

    host: str
    port: int
    security: Literal["starttls", "ssl", "none"]
    username: str
    password: str = field(repr=False)
    sender: str
    timeout: float = 10.0

    def send(self, to: str, subject: str, body: str) -> None:
        msg = EmailMessage()
        local, _, domain = self.sender.partition("@")
        msg["From"] = Address(SENDER_NAME, local, domain)
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        context = ssl.create_default_context()
        smtp = (
            smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout, context=context)
            if self.security == "ssl"
            else smtplib.SMTP(self.host, self.port, timeout=self.timeout)
        )
        with smtp:
            if self.security == "starttls":
                smtp.starttls(context=context)
            if self.username:
                smtp.login(self.username, self.password)
            smtp.send_message(msg)


class LogMailer:
    """메일 대신 로그로 남긴다(STUDY_INVEST_MAIL_LOG_ONLY=1, 로컬 개발·CI 전용). 코드가 로그에
    평문으로 남으므로 운영에서는 켜지 않는다."""

    def send(self, to: str, subject: str, body: str) -> None:
        log.warning(
            "SMTP 미설정 — 메일 대신 로그로 남김\nTo: %s\nSubject: %s\n\n%s", to, subject, body
        )


class NoMailer:
    """SMTP 미설정이고 로그 전용 모드도 아니다: 메일을 보낼 수 없다(fail closed).

    코드를 로그로 흘리지 않는다. 앱은 뜨고(코드 없는 가입·로그인은 된다), 코드를 요청하면
    발급 전에 503 MAIL_NOT_CONFIGURED로 거절한다(routes_public.send_code)."""

    def send(self, to: str, subject: str, body: str) -> None:
        raise RuntimeError("메일 발송이 설정되지 않았습니다(STUDY_INVEST_SMTP_HOST).")


def make_mailer(settings: Settings) -> Mailer:
    if not settings.smtp_host:
        if settings.mail_log_only:
            log.warning("STUDY_INVEST_MAIL_LOG_ONLY=1: 인증 메일을 로그로만 남깁니다(개발 전용).")
            return LogMailer()
        log.error(
            "STUDY_INVEST_SMTP_HOST가 비어 있어 인증·비밀번호 재설정 메일을 보낼 수 없습니다. "
            "로컬 개발이면 STUDY_INVEST_MAIL_LOG_ONLY=1로 로그에 남길 수 있습니다."
        )
        return NoMailer()
    if settings.smtp_security not in ("starttls", "ssl", "none"):
        raise ValueError("STUDY_INVEST_SMTP_SECURITY는 starttls, ssl, none 중 하나여야 합니다.")
    sender = settings.mail_from or settings.smtp_username
    if "@" not in sender:
        raise ValueError(
            "STUDY_INVEST_MAIL_FROM(또는 STUDY_INVEST_SMTP_USERNAME)에 메일 주소를 지정하세요."
        )
    return SmtpMailer(
        host=settings.smtp_host,
        port=settings.smtp_port,
        security=settings.smtp_security,
        username=settings.smtp_username,
        password=settings.smtp_password,
        sender=sender,
    )
