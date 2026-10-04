"""학교 메일 인증(1인 1계정): 도메인 제한·두 도메인 합치기, 코드 유효시간·시도·발송 한도, 재인증."""

from __future__ import annotations

import smtplib
from datetime import date, datetime, time, timedelta
from typing import Any

import pytest
from conftest import (
    Clock,
    FakeMailer,
    email_code,
    kst,
    open_day,
    register,
    register_with,
)
from fastapi.testclient import TestClient
from sqlalchemy import select

from study_invest import mail
from study_invest.config import Settings
from study_invest.event_calendar import EventCalendar
from study_invest.models import EmailVerification, Participant
from study_invest.normalize import SchoolEmailError, parse_school_email
from study_invest.services import auth, email_verification

D1 = date(2026, 10, 6)


def request(client: TestClient, email: str) -> Any:
    return client.post("/api/auth/email-code", json={"email": email})


class TestParse:
    @pytest.mark.parametrize(
        ("raw", "address", "canonical"),
        [
            ("abc@g.skku.edu", "abc@g.skku.edu", "abc@g.skku.edu"),
            ("abc@skku.edu", "abc@skku.edu", "abc@g.skku.edu"),
            ("  ABC@SKKU.EDU ", "abc@skku.edu", "abc@g.skku.edu"),
            ("ａｂｃ＠ｇ.ｓｋｋｕ.ｅｄｕ", "abc@g.skku.edu", "abc@g.skku.edu"),
            ("a.b_c-1@g.skku.edu", "a.b_c-1@g.skku.edu", "a.b_c-1@g.skku.edu"),
        ],
    )
    def test_accepts_school_domains(self, raw: str, address: str, canonical: str) -> None:
        assert parse_school_email(raw) == (address, canonical)

    @pytest.mark.parametrize(
        ("raw", "code"),
        [
            ("abc@gmail.com", "EMAIL_DOMAIN_NOT_ALLOWED"),
            ("abc@evilskku.edu", "EMAIL_DOMAIN_NOT_ALLOWED"),
            ("abc@mail.skku.edu", "EMAIL_DOMAIN_NOT_ALLOWED"),
            ("abc@skku.edu.evil.com", "EMAIL_DOMAIN_NOT_ALLOWED"),
            ("abc@g.skku.edu@gmail.com", "EMAIL_DOMAIN_NOT_ALLOWED"),
            ("abc", "INVALID_EMAIL"),
            ("@g.skku.edu", "INVALID_EMAIL"),
            ("abc+1@g.skku.edu", "INVALID_EMAIL"),  # 별칭으로 여러 계정 만들기 차단
            ("a..b@g.skku.edu", "INVALID_EMAIL"),
            (".ab@g.skku.edu", "INVALID_EMAIL"),
            ("a b@g.skku.edu", "INVALID_EMAIL"),
            ("한글@g.skku.edu", "INVALID_EMAIL"),
            ('"a"@g.skku.edu', "INVALID_EMAIL"),
        ],
    )
    def test_rejects(self, raw: str, code: str) -> None:
        with pytest.raises(SchoolEmailError) as exc:
            parse_school_email(raw)
        assert exc.value.code == code

    def test_api_returns_code(self, client: TestClient, mailer: FakeMailer) -> None:
        r = request(client, "abc@gmail.com")
        assert r.status_code == 422 and r.json()["detail"]["code"] == "EMAIL_DOMAIN_NOT_ALLOWED"
        assert mailer.sent == []


class TestCodeRequest:
    def test_mail_goes_to_address_as_typed(self, client: TestClient, mailer: FakeMailer) -> None:
        r = request(client, "Kim@SKKU.edu")
        assert r.status_code == 202
        assert r.json() == {"email": "kim@skku.edu", "expires_in": 600, "resend_after": 60}
        to, subject, body = mailer.sent[-1]
        assert to == "kim@skku.edu"
        code = mailer.last_code(to)
        assert code in subject and code in body

    def test_code_is_stored_hashed(self, client: TestClient, mailer: FakeMailer) -> None:
        request(client, "kim@g.skku.edu")
        code = mailer.last_code("kim@g.skku.edu")
        with client.app.state.study_invest.session_factory() as s:  # type: ignore[attr-defined]
            row = s.scalars(select(EmailVerification)).one()
        assert row.email == "kim@g.skku.edu" and code not in row.code_hash

    def test_resend_cooldown_and_latest_code_only(
        self, client: TestClient, clock: Clock, mailer: FakeMailer
    ) -> None:
        first = email_code(client, "kim@g.skku.edu")
        r = request(client, "kim@skku.edu")  # 같은 사람(다른 도메인)도 같은 대기 시간
        assert r.status_code == 429 and r.json()["detail"]["code"] == "CODE_RECENTLY_SENT"
        assert r.json()["detail"]["message"].startswith("60초")
        clock.now += timedelta(seconds=60)
        second = email_code(client, "kim@skku.edu")
        if first != second:
            r = register_with(client, "kim@g.skku.edu", "kim", first)
            assert r.json()["detail"]["code"] == "INVALID_CODE"
        assert register_with(client, "kim@g.skku.edu", "kim", second).status_code == 201

    def test_per_email_daily_limit(self, client: TestClient, clock: Clock) -> None:
        for _ in range(email_verification.MAX_CODES_PER_EMAIL):
            email_code(client, "kim@g.skku.edu")
            clock.now += timedelta(minutes=1)
        r = request(client, "kim@g.skku.edu")
        assert r.status_code == 429 and r.json()["detail"]["code"] == "TOO_MANY_CODES"
        assert request(client, "lee@g.skku.edu").status_code == 202  # 다른 메일은 괜찮다
        clock.now += timedelta(hours=24)
        assert request(client, "kim@g.skku.edu").status_code == 202

    def test_global_daily_limit(self, client: TestClient, mailer: FakeMailer) -> None:
        settings = client.app.state.study_invest.settings  # type: ignore[attr-defined]
        object.__setattr__(settings, "mail_daily_limit", 2)
        assert request(client, "a@g.skku.edu").status_code == 202
        assert request(client, "b@g.skku.edu").status_code == 202
        r = request(client, "c@g.skku.edu")
        assert r.status_code == 503 and r.json()["detail"]["code"] == "MAIL_QUOTA_EXCEEDED"
        assert len(mailer.sent) == 2

    def test_send_failure_is_503_and_not_counted(
        self, client: TestClient, mailer: FakeMailer
    ) -> None:
        mailer.fail = True
        r = request(client, "kim@g.skku.edu")
        assert r.status_code == 503 and r.json()["detail"]["code"] == "MAIL_SEND_FAILED"
        mailer.fail = False
        assert request(client, "kim@g.skku.edu").status_code == 202  # 대기 없이 바로 재요청


class TestCodeCheck:
    def test_wrong_code_attempts_are_counted(self, client: TestClient) -> None:
        code = email_code(client, "kim@g.skku.edu")
        wrong = f"{(int(code) + 1) % 10**6:06d}"
        for left in range(email_verification.MAX_ATTEMPTS - 1, -1, -1):
            r = register_with(client, "kim@g.skku.edu", "kim", wrong)
            assert r.status_code == 400 and r.json()["detail"]["code"] == "INVALID_CODE"
            assert (f"{left}번" in r.json()["detail"]["message"]) == (left > 0)
        r = register_with(client, "kim@g.skku.edu", "kim", code)  # 맞는 코드도 이제 무효
        assert r.json()["detail"]["code"] == "CODE_ATTEMPTS_EXCEEDED"

    def test_expired(self, client: TestClient, clock: Clock) -> None:
        code = email_code(client, "kim@g.skku.edu")
        clock.now += timedelta(minutes=10)
        r = register_with(client, "kim@g.skku.edu", "kim", code)
        assert r.status_code == 400 and r.json()["detail"]["code"] == "CODE_EXPIRED"

    def test_code_without_request(self, client: TestClient) -> None:
        r = register_with(client, "kim@g.skku.edu", "kim", "123456")
        assert r.json()["detail"]["code"] == "CODE_EXPIRED"

    def test_bad_code_format_is_422(self, client: TestClient) -> None:
        email_code(client, "kim@g.skku.edu")
        for code in ("12345", "abcdef", "1234567"):
            assert register_with(client, "kim@g.skku.edu", "kim", code).status_code == 422

    def test_code_is_single_use(self, client: TestClient) -> None:
        code = email_code(client, "kim@g.skku.edu")
        assert register_with(client, "kim@g.skku.edu", "kim", code).status_code == 201
        r = register_with(client, "kim@g.skku.edu", "kim2", code)
        assert r.json()["detail"]["code"] in {"EMAIL_TAKEN", "CODE_EXPIRED"}

    def test_failed_registration_keeps_code(self, client: TestClient) -> None:
        register(client, "taken")
        code = email_code(client, "kim@g.skku.edu")
        r = register_with(client, "kim@g.skku.edu", "taken", code)
        assert r.json()["detail"]["code"] == "NICKNAME_TAKEN"
        assert register_with(client, "kim@g.skku.edu", "kim", code).status_code == 201

    def test_code_for_other_domain_same_person(self, client: TestClient) -> None:
        code = email_code(client, "kim@skku.edu")
        r = register_with(client, "kim@g.skku.edu", "kim", code)
        assert r.status_code == 201
        assert r.json()["participant"]["email"] == "kim@g.skku.edu"

    def test_register_race_same_person_other_domain(self, client: TestClient) -> None:
        # 두 도메인으로 각각 코드를 받아 두고 하나로 먼저 가입하면, 다른 쪽은 거부
        a = email_code(client, "kim@g.skku.edu")
        assert register_with(client, "kim@g.skku.edu", "kim", a).status_code == 201
        with client.app.state.study_invest.session_factory() as s:  # type: ignore[attr-defined]
            email = parse_school_email("kim@skku.edu")
            with pytest.raises(Exception) as exc:
                auth.register(s, email, "kim2", "password123", kst(D1), EventCalendar())
        assert getattr(exc.value, "code", None) == "EMAIL_TAKEN"

    def test_privacy_consent_required(self, client: TestClient) -> None:
        code = email_code(client, "kim@g.skku.edu")
        r = client.post(
            "/api/auth/register",
            json={
                "email": "kim@g.skku.edu",
                "code": code,
                "nickname": "kim",
                "password": "password123",
                "privacy_consent": False,
            },
        )
        assert r.status_code == 422 and r.json()["detail"]["code"] == "PRIVACY_CONSENT_REQUIRED"
        assert register_with(client, "kim@g.skku.edu", "kim", code).status_code == 201


def _legacy(client: TestClient, identity: str = "2020123456") -> dict[str, str]:
    """메일 인증 도입 전에 가입한 참가자를 만들고 예전 식별자로 로그인한다."""
    state = client.app.state.study_invest  # type: ignore[attr-defined]
    with state.session_factory() as s:
        s.add(
            Participant(
                identity=identity,
                nickname="legacy",
                password_hash=auth.hash_password("password123"),
                cash=1_000_000,
                joined_at=kst(D1, time(7)),
            )
        )
        s.commit()
    r = client.post("/api/auth/login", json={"identity": identity, "password": "password123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _verify(client: TestClient, h: dict[str, str], email: str, code: str) -> Any:
    return client.post(
        "/api/me/email",
        json={"email": email, "code": code, "privacy_consent": True},
        headers=h,
    )


class TestLegacyReverification:
    def test_unverified_cannot_trade_or_certify(self, client: TestClient, clock: Clock) -> None:
        h = _legacy(client)
        me = client.get("/api/me", headers=h).json()
        assert me["email_verified"] is False and me["email"] is None
        open_day(client, clock, D1)
        r = client.post(
            "/api/me/orders", json={"code": "LB", "side": "buy", "quantity": 1}, headers=h
        )
        assert r.status_code == 403
        assert r.json()["detail"]["code"] == "EMAIL_VERIFICATION_REQUIRED"
        r = client.post(
            "/api/me/certifications", headers=h, files={"file": ("a.png", b"x", "image/png")}
        )
        assert r.json()["detail"]["code"] == "EMAIL_VERIFICATION_REQUIRED"
        assert client.get("/api/me/portfolio", headers=h).status_code == 200  # 조회는 된다

    def test_verify_then_trade_and_login_by_email(self, client: TestClient, clock: Clock) -> None:
        h = _legacy(client)
        code = email_code(client, "lee@skku.edu")
        r = _verify(client, h, "lee@skku.edu", code)
        assert r.status_code == 200
        assert r.json()["email_verified"] is True and r.json()["email"] == "lee@g.skku.edu"
        open_day(client, clock, D1)
        r = client.post(
            "/api/me/orders", json={"code": "LB", "side": "buy", "quantity": 1}, headers=h
        )
        assert r.status_code == 201
        for identity in ("lee@g.skku.edu", "2020123456"):
            r = client.post(
                "/api/auth/login", json={"identity": identity, "password": "password123"}
            )
            assert r.status_code == 200
        # 다시 인증할 수 없다
        assert request(client, "lee@g.skku.edu").json()["detail"]["code"] == "EMAIL_TAKEN"

    def test_email_used_by_other_account(self, client: TestClient, clock: Clock) -> None:
        h = _legacy(client)
        code = email_code(client, "kim@g.skku.edu")
        # 그 사이 같은 사람이 다른 도메인으로 새 계정을 만들었다
        with client.app.state.study_invest.session_factory() as s:  # type: ignore[attr-defined]
            email = parse_school_email("kim@skku.edu")
            auth.register(s, email, "kim", "password123", clock.now, EventCalendar())
            s.commit()
        r = _verify(client, h, "kim@g.skku.edu", code)
        assert r.json()["detail"]["code"] == "EMAIL_TAKEN"

    def test_already_verified(self, client: TestClient) -> None:
        h = register(client)
        code = email_code(client, "other@g.skku.edu")
        r = _verify(client, h, "other@g.skku.edu", code)
        assert r.json()["detail"]["code"] == "ALREADY_VERIFIED"

    def test_wrong_code_is_counted(self, client: TestClient) -> None:
        h = _legacy(client)
        code = email_code(client, "lee@g.skku.edu")
        wrong = f"{(int(code) + 1) % 10**6:06d}"
        for _ in range(email_verification.MAX_ATTEMPTS):
            assert _verify(client, h, "lee@g.skku.edu", wrong).status_code == 400
        r = _verify(client, h, "lee@g.skku.edu", code)
        assert r.json()["detail"]["code"] == "CODE_ATTEMPTS_EXCEEDED"


class TestPurge:
    def test_purge_after_event(self, client: TestClient) -> None:
        h = register(client)
        email_code(client, "pending@g.skku.edu")
        state = client.app.state.study_invest  # type: ignore[attr-defined]
        cal = EventCalendar()
        with state.session_factory() as s:
            with pytest.raises(Exception) as exc:
                email_verification.purge(s, kst(cal.end, time(23)), cal)
            assert getattr(exc.value, "code", None) == "EVENT_NOT_ENDED"
            after = kst(cal.end + timedelta(days=1))
            assert email_verification.purge(s, after, cal) == (1, 2)
            s.commit()
        me = client.get("/api/me", headers=h).json()
        assert me["email"] is None and me["email_verified"] is True


class TestScaledClock:
    def test_code_ttl_uses_real_time(self, client: TestClient) -> None:
        from study_invest.clock import ScaledClock

        real = [datetime(2026, 10, 1, 12, tzinfo=kst(D1).tzinfo)]
        state = client.app.state.study_invest  # type: ignore[attr-defined]
        state.clock = ScaledClock(
            origin=real[0], virtual_origin=kst(D1, time(0)), scale=24, source=lambda: real[0]
        )
        code = email_code(client, "kim@g.skku.edu")
        real[0] += timedelta(minutes=5)  # 앱 시계로는 2시간
        assert register_with(client, "kim@g.skku.edu", "kim", code).status_code == 201


class TestSmtpMailer:
    def test_starttls_login_send(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[Any] = []

        class FakeSMTP:
            def __init__(self, host: str, port: int, timeout: float) -> None:
                calls.append(("connect", host, port))

            def __enter__(self) -> FakeSMTP:
                return self

            def __exit__(self, *exc: object) -> None:
                calls.append(("quit",))

            def starttls(self, context: object) -> None:
                calls.append(("starttls",))

            def login(self, user: str, password: str) -> None:
                calls.append(("login", user, password))

            def send_message(self, msg: Any) -> None:
                calls.append(("send", msg["To"], str(msg["From"]), msg["Subject"]))

        monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
        mailer = mail.make_mailer(
            Settings(
                smtp_host="smtp.gmail.com",
                smtp_username="event@gmail.com",
                smtp_password="app-password",
            )
        )
        assert "app-password" not in repr(mailer)
        mailer.send("kim@g.skku.edu", "제목", "본문")
        assert calls == [
            ("connect", "smtp.gmail.com", 587),
            ("starttls",),
            ("login", "event@gmail.com", "app-password"),
            ("send", "kim@g.skku.edu", "공부장려 모의투자 <event@gmail.com>", "제목"),
            ("quit",),
        ]

    def test_without_host_logs(self) -> None:
        assert isinstance(mail.make_mailer(Settings()), mail.LogMailer)

    def test_settings_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("STUDY_INVEST_SMTP_HOST", "smtp.gmail.com")
        monkeypatch.setenv("STUDY_INVEST_SMTP_PORT", "465")
        monkeypatch.setenv("STUDY_INVEST_SMTP_SECURITY", "ssl")
        monkeypatch.setenv("STUDY_INVEST_SMTP_USERNAME", "event@gmail.com")
        monkeypatch.setenv("STUDY_INVEST_SMTP_PASSWORD", "secret")
        monkeypatch.setenv("STUDY_INVEST_MAIL_DAILY_LIMIT", "300")
        settings = Settings.from_env()
        assert (settings.smtp_port, settings.smtp_security, settings.mail_daily_limit) == (
            465,
            "ssl",
            300,
        )
        assert "secret" not in repr(settings)
        monkeypatch.setenv("STUDY_INVEST_SMTP_SECURITY", "tls")
        with pytest.raises(ValueError):
            mail.make_mailer(Settings.from_env())
