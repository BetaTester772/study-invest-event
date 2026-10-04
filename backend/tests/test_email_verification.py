"""학교 메일 인증(1인 1계정): 도메인 제한·두 도메인 합치기, 코드 유효시간·시도·발송 한도, 재인증."""

from __future__ import annotations

import smtplib
from datetime import date, datetime, time, timedelta
from typing import Any

import pytest
from conftest import (
    PNG,
    Clock,
    FakeMailer,
    email_code,
    kst,
    open_day,
    profile_for,
    register,
    register_with,
    student_id_for,
)
from fastapi.testclient import TestClient
from sqlalchemy import select

from study_invest import mail
from study_invest.api.deps import MAIL_CONCURRENCY
from study_invest.config import Settings
from study_invest.event_calendar import EventCalendar
from study_invest.models import EmailVerification, Participant
from study_invest.normalize import SchoolEmailError, parse_school_email
from study_invest.services import auth, email_verification

D1 = date(2026, 10, 6)
PROFILE = auth.Profile("홍길동", "2026999999", "소프트웨어학과")


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

    def test_send_failure_is_503_and_still_counted(
        self, client: TestClient, clock: Clock, mailer: FakeMailer
    ) -> None:
        mailer.fail = True
        r = request(client, "kim@g.skku.edu")
        assert r.status_code == 503 and r.json()["detail"]["code"] == "MAIL_SEND_FAILED"
        # 실패한 발송도 재요청 대기에 센다(SMTP 장애 중 무한 재시도 방지)
        mailer.fail = False
        assert request(client, "kim@g.skku.edu").json()["detail"]["code"] == "CODE_RECENTLY_SENT"
        clock.now += timedelta(minutes=1)
        assert request(client, "kim@g.skku.edu").status_code == 202

    def test_concurrent_mail_sends_are_capped(self, client: TestClient, mailer: FakeMailer) -> None:
        state = client.app.state.study_invest  # type: ignore[attr-defined]
        for _ in range(MAIL_CONCURRENCY):  # 다른 요청들이 SMTP를 기다리는 중
            assert state.mail_slots.acquire(blocking=False)
        try:
            r = request(client, "kim@g.skku.edu")
            assert r.status_code == 503 and r.json()["detail"]["code"] == "MAIL_BUSY"
        finally:
            for _ in range(MAIL_CONCURRENCY):
                state.mail_slots.release()
        assert mailer.sent == []
        assert request(client, "kim@g.skku.edu").status_code == 202  # 코드를 만들기 전에 거절


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
        assert r.json()["participant"]["masked_email"] == "k***@g.skku.edu"

    def test_register_race_same_person_other_domain(self, client: TestClient) -> None:
        # 두 도메인으로 각각 코드를 받아 두고 하나로 먼저 가입하면, 다른 쪽은 거부
        a = email_code(client, "kim@g.skku.edu")
        assert register_with(client, "kim@g.skku.edu", "kim", a).status_code == 201
        with client.app.state.study_invest.session_factory() as s:  # type: ignore[attr-defined]
            email = parse_school_email("kim@skku.edu")
            with pytest.raises(Exception) as exc:
                auth.register(s, email, PROFILE, "kim2", "password123", kst(D1), EventCalendar())
        assert getattr(exc.value, "code", None) == "EMAIL_TAKEN"

    def test_privacy_consent_required(self, client: TestClient) -> None:
        code = email_code(client, "kim@g.skku.edu")
        r = register_with(client, "kim@g.skku.edu", "kim", code, privacy_consent=False)
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


def _verify(client: TestClient, h: dict[str, str], email: str, code: str, **overrides: Any) -> Any:
    return client.post(
        "/api/me/email",
        json={
            "email": email,
            "code": code,
            **profile_for(email),
            "privacy_consent": True,
            **overrides,
        },
        headers=h,
    )


class TestLegacyReverification:
    def test_verify_then_trade_and_login_by_email(self, client: TestClient, clock: Clock) -> None:
        h = _legacy(client)
        code = email_code(client, "lee@skku.edu")
        r = _verify(client, h, "lee@skku.edu", code)
        assert r.status_code == 200
        assert r.json()["verified"] is True and r.json()["masked_email"] == "l***@skku.edu"
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
            auth.register(s, email, PROFILE, "kim", "password123", clock.now, EventCalendar())
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
        end = date(2026, 10, 16)
        assert cal.end == end
        with state.session_factory() as s:
            with pytest.raises(Exception) as exc:
                email_verification.purge(s, kst(end, time(23)), cal)
            assert getattr(exc.value, "code", None) == "EVENT_NOT_ENDED"
            after = kst(end + timedelta(days=1))
            assert email_verification.purge(s, after, cal) == (1, 2)
            s.commit()
        me = client.get("/api/me", headers=h).json()
        assert me["masked_email"] is None and me["verified"] is True


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


class TestProfile:
    def test_profile_is_stored_for_admin_only(
        self, client: TestClient, admin: dict[str, str]
    ) -> None:
        r = register_with(
            client,
            "kim@g.skku.edu",
            "kim",
            name=" 김성균 ",
            student_id="２０２１３１０１２３",  # 전각 숫자도 같은 학번
            department="소프트웨어학과",
        )
        assert r.status_code == 201, r.text
        assert "student_id" not in r.json()["participant"]  # 본인 응답·랭킹에는 없다
        row = next(
            p for p in client.get("/api/admin/participants", headers=admin).json() if p["id"]
        )
        assert (row["name"], row["student_id"], row["department"]) == (
            "김성균",
            "2021310123",
            "소프트웨어학과",
        )
        ranking = client.get("/api/ranking").json()["entries"][0]
        assert "name" not in ranking and "student_id" not in ranking

    @pytest.mark.parametrize(
        "overrides",
        [
            {"name": "  "},
            {"name": "가" * 31},
            {"student_id": "123456789"},
            {"student_id": "20213101234"},
            {"student_id": "2021-31012"},
            {"department": ""},
            {"department": "가" * 51},
        ],
    )
    def test_invalid_profile_is_422(self, client: TestClient, overrides: dict[str, str]) -> None:
        code = email_code(client, "kim@g.skku.edu")
        r = register_with(client, "kim@g.skku.edu", "kim", code, **overrides)
        assert r.status_code == 422
        # 형식 오류는 코드를 쓰지 않는다
        assert register_with(client, "kim@g.skku.edu", "kim", code).status_code == 201

    def test_one_account_per_student_id(self, client: TestClient) -> None:
        assert (
            register_with(client, "kim@g.skku.edu", "kim", student_id="2021310123").status_code
            == 201
        )
        code = email_code(client, "lee@g.skku.edu")
        r = register_with(client, "lee@g.skku.edu", "lee", code, student_id="2021310123")
        assert r.status_code == 409 and r.json()["detail"]["code"] == "STUDENT_ID_TAKEN"
        # 실패한 가입은 코드를 쓰지 않는다
        assert register_with(client, "lee@g.skku.edu", "lee", code).status_code == 201

    def test_legacy_reverification_collects_profile(
        self, client: TestClient, admin: dict[str, str]
    ) -> None:
        register_with(client, "kim@g.skku.edu", "kim", student_id="2021310123")
        h = _legacy(client)
        code = email_code(client, "lee@g.skku.edu")
        r = _verify(client, h, "lee@g.skku.edu", code, student_id="2021310123")
        assert r.json()["detail"]["code"] == "STUDENT_ID_TAKEN"
        r = _verify(client, h, "lee@g.skku.edu", code, name="이예전", student_id="2019310001")
        assert r.status_code == 200, r.text
        row = next(
            p
            for p in client.get("/api/admin/participants", headers=admin).json()
            if p["nickname"] == "legacy"
        )
        assert (row["name"], row["student_id"], row["identity"]) == (
            "이예전",
            "2019310001",
            "2020123456",
        )

    def test_purge_clears_profile(self, client: TestClient, admin: dict[str, str]) -> None:
        register(client)
        state = client.app.state.study_invest  # type: ignore[attr-defined]
        with state.session_factory() as s:
            email_verification.purge(s, kst(D1), EventCalendar(), force=True)
            s.commit()
        row = client.get("/api/admin/participants", headers=admin).json()[0]
        assert [row[k] for k in ("email", "name", "student_id", "department")] == [None] * 4


def _reset_code(client: TestClient, identity: str) -> Any:
    return client.post("/api/auth/password-reset/code", json={"identity": identity})


def _reset(client: TestClient, identity: str, code: str, password: str = "newpass456") -> Any:
    return client.post(
        "/api/auth/password-reset",
        json={"identity": identity, "code": code, "password": password},
    )


def _login(client: TestClient, identity: str, password: str) -> Any:
    return client.post("/api/auth/login", json={"identity": identity, "password": password})


class TestPasswordReset:
    def test_reset_by_student_id(
        self, client: TestClient, clock: Clock, mailer: FakeMailer
    ) -> None:
        r = register_with(client, "kim@skku.edu", "kim", student_id="2021310123")
        old = {"Authorization": f"Bearer {r.json()['token']}"}
        clock.now += timedelta(minutes=1)
        r = _reset_code(client, "2021310123")
        # 등록한 주소(입력한 도메인 그대로)로 보내고, 응답에는 가린 주소만
        assert r.status_code == 202 and r.json()["email"] == "k***@skku.edu"
        to, subject, body = mailer.sent[-1]
        assert to == "kim@skku.edu" and "비밀번호 재설정" in subject and "비밀번호" in body
        r = _reset(client, "2021310123", mailer.last_code(to))
        assert r.status_code == 200 and r.json()["participant"]["nickname"] == "kim"
        # 새 토큰은 되고, 이전 로그인은 모두 끊긴다
        new = {"Authorization": f"Bearer {r.json()['token']}"}
        assert client.get("/api/me", headers=new).status_code == 200
        assert client.get("/api/me", headers=old).status_code == 401
        assert _login(client, "2021310123", "password123").status_code == 401
        assert _login(client, "2021310123", "newpass456").status_code == 200

    def test_reset_by_email_also_works(
        self, client: TestClient, clock: Clock, mailer: FakeMailer
    ) -> None:
        register(client, "kim")  # kim@g.skku.edu
        clock.now += timedelta(minutes=1)
        assert _reset_code(client, "kim@skku.edu").json()["email"] == "k***@g.skku.edu"
        assert mailer.sent[-1][0] == "kim@g.skku.edu"  # 등록 주소로만
        r = _reset(client, "kim@skku.edu", mailer.last_code("kim@g.skku.edu"))
        assert r.status_code == 200

    def test_unknown_account(self, client: TestClient, mailer: FakeMailer) -> None:
        for identity in ("2099999999", "nobody@g.skku.edu", "whatever"):
            r = _reset_code(client, identity)
            assert r.status_code == 404 and r.json()["detail"]["code"] == "ACCOUNT_NOT_FOUND"
        # 메일이 없는 예전 계정도 재설정할 수 없다
        _legacy(client)
        assert _reset_code(client, "2020123456").json()["detail"]["code"] == "ACCOUNT_NOT_FOUND"
        assert mailer.sent == []

    def test_signup_code_cannot_reset_and_vice_versa(
        self, client: TestClient, clock: Clock, mailer: FakeMailer
    ) -> None:
        signup = email_code(client, "kim@g.skku.edu")
        assert register_with(client, "kim@g.skku.edu", "kim", signup).status_code == 201
        sid = student_id_for("kim@g.skku.edu")
        # 이미 쓴 가입 코드로는 비밀번호를 바꿀 수 없다
        assert _reset(client, sid, signup).json()["detail"]["code"] == "CODE_EXPIRED"
        clock.now += timedelta(minutes=1)
        _reset_code(client, sid)
        reset = mailer.last_code("kim@g.skku.edu")
        # 재설정 코드로는 가입할 수 없다
        r = register_with(client, "kim@g.skku.edu", "kim2", reset, student_id="2026999998")
        assert r.json()["detail"]["code"] in {"CODE_EXPIRED", "EMAIL_TAKEN"}
        assert _reset(client, sid, reset).status_code == 200

    def test_wrong_code_attempts_and_single_use(
        self, client: TestClient, clock: Clock, mailer: FakeMailer
    ) -> None:
        register(client, "kim")
        sid = student_id_for("kim@g.skku.edu")
        clock.now += timedelta(minutes=1)
        _reset_code(client, sid)
        code = mailer.last_code("kim@g.skku.edu")
        wrong = f"{(int(code) + 1) % 10**6:06d}"
        r = _reset(client, sid, wrong)
        assert r.status_code == 400 and r.json()["detail"]["code"] == "INVALID_CODE"
        assert _reset(client, sid, code).status_code == 200
        assert _reset(client, sid, code).json()["detail"]["code"] == "CODE_EXPIRED"
        assert _reset(client, sid, code, "short").status_code == 422

    def test_cooldown_shared_with_signup_code(self, client: TestClient) -> None:
        register(client, "kim")  # 방금 가입 코드를 받았다
        r = _reset_code(client, student_id_for("kim@g.skku.edu"))
        assert r.status_code == 429 and r.json()["detail"]["code"] == "CODE_RECENTLY_SENT"

    def test_reset_works_after_event(self, client: TestClient, clock: Clock) -> None:
        register(client, "kim")
        clock.set(date(2026, 10, 20))
        assert _reset_code(client, student_id_for("kim@g.skku.edu")).status_code == 202


class TestLoginByStudentId:
    def test_login_with_student_id_or_email(self, client: TestClient) -> None:
        register_with(client, "kim@g.skku.edu", "kim", student_id="2021310123")
        for identity in ("2021310123", " ２０２１３１０１２３ ", "kim@skku.edu"):
            r = _login(client, identity, "password123")
            assert r.status_code == 200 and r.json()["participant"]["nickname"] == "kim", identity
        r = _login(client, "2021310123", "wrong-pass")
        assert r.status_code == 401
        assert r.json()["detail"]["message"].startswith("학번 또는 비밀번호")

    def test_legacy_identity_that_looks_like_someone_elses_student_id(
        self, client: TestClient
    ) -> None:
        # 예전 아이디가 다른 사람의 학번과 같은 숫자여도, 비밀번호로 각자 로그인된다
        register_with(client, "kim@g.skku.edu", "kim", student_id="2020123456")
        _legacy(client, identity="2020123456")  # 비밀번호 password123
        state = client.app.state.study_invest  # type: ignore[attr-defined]
        with state.session_factory() as s:
            kim = s.scalars(select(Participant).where(Participant.nickname == "kim")).one()
            kim.password_hash = auth.hash_password("kim-secret")
            s.commit()
        assert _login(client, "2020123456", "password123").json()["participant"]["nickname"] == (
            "legacy"
        )
        assert _login(client, "2020123456", "kim-secret").json()["participant"]["nickname"] == (
            "kim"
        )


def _order(client: TestClient, h: dict[str, str]) -> Any:
    return client.post(
        "/api/me/orders", json={"code": "LB", "side": "buy", "quantity": 1}, headers=h
    )


def _set_verified_only(client: TestClient, admin: dict[str, str], on: bool) -> None:
    r = client.put("/api/admin/trading-access", json={"verified_only": on}, headers=admin)
    assert r.status_code == 200 and r.json() == {"verified_only": on}


def _register_without_code(client: TestClient, email: str, nickname: str) -> dict[str, str]:
    r = client.post(
        "/api/auth/register",
        json={
            "email": email,
            **profile_for(email),
            "nickname": nickname,
            "password": "password123",
            "privacy_consent": True,
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["participant"]["verified"] is False
    return {"Authorization": f"Bearer {r.json()['token']}"}


class TestSignupWithoutCode:
    def test_default_signup_needs_email_but_no_code(
        self, client: TestClient, mailer: FakeMailer
    ) -> None:
        h = _register_without_code(client, "kim@skku.edu", "kim")
        me = client.get("/api/me", headers=h).json()
        assert (me["masked_email"], me["verified"], me["needs_profile"]) == (
            "k***@skku.edu",
            False,
            False,
        )
        assert mailer.sent == []
        info = client.get("/api/event").json()["signup"]
        assert info == {"email_verification": False, "verified_only_trading": False}
        # 메일은 여전히 학교 메일만, 1인 1계정
        r = client.post(
            "/api/auth/register",
            json={
                "email": "kim@g.skku.edu",
                **profile_for("other"),
                "nickname": "kim2",
                "password": "password123",
                "privacy_consent": True,
            },
        )
        assert r.json()["detail"]["code"] == "EMAIL_TAKEN"
        r = client.post(
            "/api/auth/register",
            json={
                "email": "x@gmail.com",
                **profile_for("x"),
                "nickname": "xx",
                "password": "password123",
                "privacy_consent": True,
            },
        )
        assert r.json()["detail"]["code"] == "EMAIL_DOMAIN_NOT_ALLOWED"

    def test_password_reset_uses_unverified_email(
        self, client: TestClient, mailer: FakeMailer
    ) -> None:
        _register_without_code(client, "kim@g.skku.edu", "kim")
        assert _reset_code(client, "kim@g.skku.edu").status_code == 202
        r = _reset(client, "kim@g.skku.edu", mailer.last_code("kim@g.skku.edu"))
        assert r.status_code == 200
        assert _login(client, student_id_for("kim@g.skku.edu"), "newpass456").status_code == 200

    def test_code_required_when_email_verification_is_on(self, client: TestClient) -> None:
        settings = client.app.state.study_invest.settings  # type: ignore[attr-defined]
        object.__setattr__(settings, "email_verification", True)
        assert client.get("/api/event").json()["signup"]["email_verification"] is True
        r = client.post(
            "/api/auth/register",
            json={
                "email": "kim@g.skku.edu",
                **profile_for("kim@g.skku.edu"),
                "nickname": "kim",
                "password": "password123",
                "privacy_consent": True,
            },
        )
        assert r.status_code == 422 and r.json()["detail"]["code"] == "CODE_REQUIRED"
        r = register_with(client, "kim@g.skku.edu", "kim")
        assert r.status_code == 201 and r.json()["participant"]["verified"] is True


class TestVerifiedOnlyTrading:
    def test_switch_blocks_only_unverified_orders(
        self, client: TestClient, clock: Clock, admin: dict[str, str]
    ) -> None:
        unverified = _register_without_code(client, "kim@g.skku.edu", "kim")
        verified = register(client, "lee")
        open_day(client, clock, D1)
        assert _order(client, unverified).status_code == 201  # 평소에는 누구나
        _set_verified_only(client, admin, True)
        assert client.get("/api/event").json()["signup"]["verified_only_trading"] is True
        r = _order(client, unverified)
        assert r.status_code == 403 and r.json()["detail"]["code"] == "VERIFICATION_REQUIRED"
        assert _order(client, verified).status_code == 201
        # 공부 인증 제출·조회는 막지 않는다(거래만)
        clock.set(D1, time(12))
        r = client.post(
            "/api/me/certifications",
            headers=unverified,
            files={"file": ("a.png", PNG, "image/png")},
        )
        assert r.status_code == 201, r.text
        assert client.get("/api/me/portfolio", headers=unverified).status_code == 200
        _set_verified_only(client, admin, False)
        clock.set(D1, time(13))
        assert _order(client, unverified).status_code == 201

    def test_switch_survives_params_form_save(
        self, client: TestClient, admin: dict[str, str]
    ) -> None:
        _set_verified_only(client, admin, True)
        params = client.get("/api/admin/params", headers=admin).json()
        assert params["verified_only_trading"] is True
        del params["verified_only_trading"]  # 파라미터 폼은 이 값을 보내지 않는다
        params["reward_cash"] = 100_000
        assert client.put("/api/admin/params", json=params, headers=admin).status_code == 200
        assert client.get("/api/admin/trading-access", headers=admin).json() == {
            "verified_only": True
        }
        actions = [a["action"] for a in client.get("/api/admin/audit", headers=admin).json()]
        assert actions.count("params.update") == 2  # 스위치·폼 저장 모두 이력에 남는다

    def test_self_verification_with_registered_email(
        self, client: TestClient, clock: Clock, admin: dict[str, str], mailer: FakeMailer
    ) -> None:
        h = _register_without_code(client, "kim@g.skku.edu", "kim")
        _set_verified_only(client, admin, True)
        # 본인 메일(미인증 계정이 쓰는 메일)로 코드를 받을 수 있다
        code = email_code(client, "kim@skku.edu")
        r = client.post("/api/me/email", json={"email": "kim@skku.edu", "code": code}, headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["verified"] is True and r.json()["masked_email"] == "k***@skku.edu"
        open_day(client, clock, D1)
        assert _order(client, h).status_code == 201
        row = client.get("/api/admin/participants", headers=admin).json()[0]
        assert row["verified_via"] == "email" and row["student_id"] == student_id_for(
            "kim@g.skku.edu"
        )
        # 인증된 메일은 더 이상 다른 가입에 쓸 수 없다
        clock.now += timedelta(minutes=1)
        assert request(client, "kim@g.skku.edu").json()["detail"]["code"] == "EMAIL_TAKEN"

    def test_other_person_cannot_take_unverified_email(self, client: TestClient) -> None:
        _register_without_code(client, "kim@g.skku.edu", "kim")
        code = email_code(client, "kim@g.skku.edu")  # 미인증 계정의 메일이라 코드는 간다
        r = register_with(client, "kim@g.skku.edu", "intruder", code)
        assert r.json()["detail"]["code"] == "EMAIL_TAKEN"

    def test_admin_verify_and_unverify(
        self, client: TestClient, clock: Clock, admin: dict[str, str]
    ) -> None:
        h = _register_without_code(client, "kim@g.skku.edu", "kim")
        _set_verified_only(client, admin, True)
        open_day(client, clock, D1)
        pid = client.get("/api/me", headers=h).json()["id"]
        r = client.patch(f"/api/admin/participants/{pid}", json={"verified": True}, headers=admin)
        assert r.status_code == 200
        assert (r.json()["verified"], r.json()["verified_via"], r.json()["status"]) == (
            True,
            "admin",
            "normal",
        )
        assert _order(client, h).status_code == 201
        r = client.patch(f"/api/admin/participants/{pid}", json={"verified": False}, headers=admin)
        assert r.json()["verified"] is False and r.json()["verified_via"] is None
        assert _order(client, h).status_code == 403
        # 상태만 바꿔도 인증은 그대로
        r = client.patch(
            f"/api/admin/participants/{pid}", json={"status": "warning"}, headers=admin
        )
        assert (r.json()["status"], r.json()["verified"]) == ("warning", False)

    def test_legacy_account_needs_profile_to_verify(self, client: TestClient) -> None:
        h = _legacy(client)
        assert client.get("/api/me", headers=h).json()["needs_profile"] is True
        code = email_code(client, "lee@g.skku.edu")
        r = client.post(
            "/api/me/email",
            json={"email": "lee@g.skku.edu", "code": code, "privacy_consent": True},
            headers=h,
        )
        assert r.status_code == 422 and r.json()["detail"]["code"] == "PROFILE_REQUIRED"
        assert _verify(client, h, "lee@g.skku.edu", code).status_code == 200


def _my_code(client: TestClient, h: dict[str, str], email: str | None = None) -> Any:
    return client.post(
        "/api/me/email/code", json={} if email is None else {"email": email}, headers=h
    )


class TestMyEmailCode:
    def test_code_to_registered_address_then_code_only(
        self, client: TestClient, mailer: FakeMailer
    ) -> None:
        h = _register_without_code(client, "kim@skku.edu", "kim")
        r = _my_code(client, h)
        # 등록한 주소(입력한 도메인 그대로)로 보내고 응답은 가린 주소
        assert r.status_code == 202 and r.json()["email"] == "k***@skku.edu"
        assert mailer.sent[-1][0] == "kim@skku.edu"
        r = client.post("/api/me/email", json={"code": mailer.last_code("kim@skku.edu")}, headers=h)
        assert r.status_code == 200, r.text
        me = r.json()
        assert (me["verified"], me["email_verified"], me["masked_email"]) == (
            True,
            True,
            "k***@skku.edu",
        )
        # 메일 코드로 인증한 뒤에는 메일을 바꿀 수 없다
        assert _my_code(client, h).json()["detail"]["code"] == "ALREADY_VERIFIED"
        assert _my_code(client, h, "other@g.skku.edu").json()["detail"]["code"] == (
            "ALREADY_VERIFIED"
        )

    def test_other_address_replaces_registered_email(
        self, client: TestClient, admin: dict[str, str], mailer: FakeMailer
    ) -> None:
        h = _register_without_code(client, "typo@g.skku.edu", "kim")
        r = _my_code(client, h, "kim@g.skku.edu")
        assert r.status_code == 202 and r.json()["email"] == "kim@g.skku.edu"  # 직접 입력은 그대로
        code = mailer.last_code("kim@g.skku.edu")
        r = client.post("/api/me/email", json={"email": "kim@g.skku.edu", "code": code}, headers=h)
        assert r.status_code == 200 and r.json()["masked_email"] == "k***@g.skku.edu"
        row = client.get("/api/admin/participants", headers=admin).json()[0]
        assert (row["email"], row["verified_via"]) == ("kim@g.skku.edu", "email")
        # 바뀐 뒤 옛 주소는 비어 새로 가입할 수 있다
        assert request(client, "typo@g.skku.edu").status_code == 202

    def test_admin_verified_account_can_still_fix_email(
        self, client: TestClient, clock: Clock, admin: dict[str, str], mailer: FakeMailer
    ) -> None:
        h = _register_without_code(client, "typo@g.skku.edu", "kim")
        pid = client.get("/api/me", headers=h).json()["id"]
        client.patch(f"/api/admin/participants/{pid}", json={"verified": True}, headers=admin)
        me = client.get("/api/me", headers=h).json()
        assert (me["verified"], me["email_verified"]) == (True, False)
        # 관리자 인증은 메일을 확인하지 않으므로 메일 인증으로 바로잡을 수 있다
        assert _my_code(client, h, "kim@g.skku.edu").status_code == 202
        r = client.post(
            "/api/me/email",
            json={"email": "kim@g.skku.edu", "code": mailer.last_code("kim@g.skku.edu")},
            headers=h,
        )
        assert r.status_code == 200 and r.json()["email_verified"] is True
        row = client.get("/api/admin/participants", headers=admin).json()[0]
        assert (row["email"], row["verified_via"]) == ("kim@g.skku.edu", "email")

    def test_other_persons_verified_email_is_refused(self, client: TestClient) -> None:
        register(client, "kim")  # kim@g.skku.edu, 메일 인증
        h = _register_without_code(client, "lee@g.skku.edu", "lee")
        r = _my_code(client, h, "kim@skku.edu")
        assert r.json()["detail"]["code"] == "EMAIL_TAKEN"

    def test_legacy_account_without_email_must_type_one(self, client: TestClient) -> None:
        h = _legacy(client)
        r = _my_code(client, h)
        assert r.status_code == 422 and r.json()["detail"]["code"] == "EMAIL_REQUIRED"
        assert _my_code(client, h, "lee@g.skku.edu").status_code == 202


class TestNoConnectionHeldDuringSend:
    def test_pool_is_free_while_smtp_runs(self, tmp_path: Any) -> None:
        """메일을 보내는 동안 DB 연결을 잡고 있지 않다(느린 SMTP가 api 풀을 막지 않게).

        메모리 SQLite(StaticPool)로는 확인할 수 없어 파일 SQLite(QueuePool)로 앱을 따로 띄운다.
        """
        from study_invest.api.app import create_app

        seen: list[int] = []

        class PoolProbe(FakeMailer):
            def send(self, to: str, subject: str, body: str) -> None:
                seen.append(app.state.study_invest.pools.api.pool.checkedout())
                super().send(to, subject, body)

        mailer = PoolProbe()
        app = create_app(
            Settings(
                database_url=f"sqlite:///{tmp_path / 'pool.db'}",
                upload_dir=tmp_path / "uploads",
                auto_create_schema=True,
            ),
            mailer=mailer,
        )
        with TestClient(app) as c:
            assert (
                c.post("/api/auth/email-code", json={"email": "kim@g.skku.edu"}).status_code == 202
            )
            mailer.fail = True
            r = c.post("/api/auth/email-code", json={"email": "lee@g.skku.edu"})
            assert r.status_code == 503
        assert seen == [0, 0]
