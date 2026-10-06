"""봇 확인(Turnstile): 로그인·참가 신청·코드 요청에만 걸고, 키가 없으면 확인하지 않는다."""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from conftest import ADMIN_KEY, TEST_DB_URL, Clock, FakeMailer, StubRandom, profile_for
from fastapi.testclient import TestClient

from study_invest import captcha as captcha_module
from study_invest.api.app import create_app
from study_invest.captcha import CaptchaUnavailable, NoCaptcha, TurnstileVerifier, make_captcha
from study_invest.config import Settings
from study_invest.db import Base

GOOD = "good-token"


class FakeCaptcha:
    """GOOD 토큰만 통과. down=True면 siteverify에 닿지 못한 것처럼 군다."""

    site_key: str | None = "site-key"

    def __init__(self) -> None:
        self.down = False
        self.calls: list[tuple[str, str]] = []

    def verify(self, token: str, action: str) -> bool:
        self.calls.append((token, action))
        if self.down:
            raise CaptchaUnavailable("down")
        return token == GOOD


@pytest.fixture
def fake_captcha() -> FakeCaptcha:
    return FakeCaptcha()


@pytest.fixture
def cclient(
    tmp_path: Path, clock: Clock, rng: StubRandom, mailer: FakeMailer, fake_captcha: FakeCaptcha
) -> Iterator[TestClient]:
    settings = Settings(
        database_url=TEST_DB_URL,
        admin_key=ADMIN_KEY,
        upload_dir=tmp_path / "uploads",
        auto_create_schema=True,
        loop_guard="raise",
    )
    app = create_app(settings, clock=clock, rng=rng, mailer=mailer, captcha=fake_captcha)
    engine = app.state.study_invest.session_factory.kw["bind"]
    if TEST_DB_URL != "sqlite://":
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
    with TestClient(app) as c:
        yield c
    if TEST_DB_URL != "sqlite://":
        Base.metadata.drop_all(engine)
    engine.dispose()


def _register_body(email: str, nickname: str) -> dict[str, Any]:
    return {
        "email": email,
        **profile_for(email),
        "nickname": nickname,
        "password": "tiger-moon-river-42",
        "privacy_consent": True,
    }


def _token(t: str = GOOD) -> dict[str, str]:
    return {"X-Turnstile-Token": t}


def test_site_key_is_published(cclient: TestClient, client: TestClient) -> None:
    assert cclient.get("/api/event").json()["signup"]["turnstile_site_key"] == "site-key"
    assert client.get("/api/event").json()["signup"]["turnstile_site_key"] is None


def test_without_keys_no_token_needed(client: TestClient) -> None:
    r = client.post("/api/auth/register", json=_register_body("alice@g.skku.edu", "alice"))
    assert r.status_code == 201, r.text


@pytest.mark.parametrize(
    ("path", "body", "action"),
    [
        ("/api/auth/email-code", {"email": "alice@g.skku.edu"}, "register"),
        ("/api/auth/register", _register_body("alice@g.skku.edu", "alice"), "register"),
        ("/api/auth/password-reset/code", {"identity": "2026000000"}, "password_reset"),
        ("/api/auth/login", {"identity": "2026000000", "password": "x"}, "login"),
    ],
)
def test_protected_endpoints(
    cclient: TestClient,
    fake_captcha: FakeCaptcha,
    mailer: FakeMailer,
    path: str,
    body: dict[str, Any],
    action: str,
) -> None:
    for headers in ({}, _token("bad")):
        r = cclient.post(path, json=body, headers=headers)
        assert r.status_code == 403, r.text
        assert r.json()["detail"]["code"] == "CAPTCHA_FAILED"
    assert mailer.sent == []
    r = cclient.post(path, json=body, headers=_token())
    assert r.status_code != 403, r.text
    assert fake_captcha.calls[-1] == (GOOD, action)


def test_login_fails_open_but_codes_fail_closed(
    cclient: TestClient, fake_captcha: FakeCaptcha, mailer: FakeMailer
) -> None:
    body = _register_body("alice@g.skku.edu", "alice")
    assert cclient.post("/api/auth/register", json=body, headers=_token()).status_code == 201
    fake_captcha.down = True
    # 로그인은 siteverify 장애 때도 막지 않는다(공격자가 장애를 일으킬 수 없다).
    r = cclient.post(
        "/api/auth/login",
        json={"identity": body["student_id"], "password": body["password"]},
        headers=_token("anything"),
    )
    assert r.status_code == 200, r.text
    # 메일을 보내는 요청과 가입은 막는다.
    for path, req in [
        ("/api/auth/email-code", {"email": "bob@g.skku.edu"}),
        ("/api/auth/password-reset/code", {"identity": body["student_id"]}),
        ("/api/auth/register", _register_body("bob@g.skku.edu", "bob")),
    ]:
        r = cclient.post(path, json=req, headers=_token())
        assert r.status_code == 503, r.text
        assert r.json()["detail"]["code"] == "CAPTCHA_UNAVAILABLE"
    assert mailer.sent == []


def test_other_endpoints_untouched(cclient: TestClient, fake_captcha: FakeCaptcha) -> None:
    r = cclient.post(
        "/api/auth/register", json=_register_body("alice@g.skku.edu", "alice"), headers=_token()
    )
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    calls = len(fake_captcha.calls)
    assert cclient.get("/api/me", headers=h).status_code == 200
    assert cclient.post("/api/auth/logout", headers=h).status_code == 204
    assert len(fake_captcha.calls) == calls


# ---- make_captcha / TurnstileVerifier ----


def test_make_captcha() -> None:
    assert isinstance(make_captcha(Settings()), NoCaptcha)
    v = make_captcha(Settings(turnstile_site_key="s", turnstile_secret_key="very-secret"))
    assert isinstance(v, TurnstileVerifier) and v.site_key == "s"
    with pytest.raises(ValueError):
        make_captcha(Settings(turnstile_site_key="s"))
    with pytest.raises(ValueError):
        make_captcha(Settings(turnstile_secret_key="very-secret"))
    assert "very-secret" not in repr(v)


class _Response(io.BytesIO):
    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def _siteverify(monkeypatch: pytest.MonkeyPatch, result: dict[str, Any] | Exception) -> list[Any]:
    sent: list[Any] = []

    def urlopen(req: Any, timeout: float) -> _Response:
        sent.append(req)
        if isinstance(result, Exception):
            raise result
        return _Response(json.dumps(result).encode())

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    return sent


def test_turnstile_success_checks_action(monkeypatch: pytest.MonkeyPatch) -> None:
    v = TurnstileVerifier(site_key="s", secret_key="secret")
    sent = _siteverify(monkeypatch, {"success": True, "action": "login"})
    assert v.verify("tok", "login") is True
    assert v.verify("tok", "register") is False
    _siteverify(monkeypatch, {"success": True, "action": ""})  # 테스트 키의 더미 토큰
    assert v.verify("tok", "register") is True
    assert sent[0].full_url == captcha_module.SITEVERIFY_URL
    assert sent[0].data == b"secret=secret&response=tok"


def test_turnstile_rejects_without_calling(monkeypatch: pytest.MonkeyPatch) -> None:
    v = TurnstileVerifier(site_key="s", secret_key="secret")
    sent = _siteverify(monkeypatch, {"success": True, "action": "login"})
    assert v.verify("", "login") is False
    assert v.verify("x" * (captcha_module.MAX_TOKEN_LENGTH + 1), "login") is False
    assert sent == []


def test_turnstile_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    v = TurnstileVerifier(site_key="s", secret_key="secret")
    _siteverify(monkeypatch, {"success": False, "error-codes": ["invalid-input-response"]})
    assert v.verify("tok", "login") is False
    _siteverify(monkeypatch, {"success": False, "error-codes": ["internal-error"]})
    with pytest.raises(CaptchaUnavailable):
        v.verify("tok", "login")


@pytest.mark.parametrize(
    "exc", [urllib.error.URLError("dns"), TimeoutError(), ConnectionResetError()]
)
def test_turnstile_unreachable(monkeypatch: pytest.MonkeyPatch, exc: Exception) -> None:
    v = TurnstileVerifier(site_key="s", secret_key="secret")
    _siteverify(monkeypatch, exc)
    with pytest.raises(CaptchaUnavailable):
        v.verify("tok", "login")
