"""Real API authentication boundaries, with no market workers or database state."""

import base64
import logging
from types import SimpleNamespace

import pytest
import signal_arcade.api as api_module
import signal_arcade.dashboard_auth as sessions_module
from fastapi import HTTPException
from fastapi.testclient import TestClient
from signal_arcade.dashboard_auth import SESSION_SECONDS, DashboardSessions
from starlette.websockets import WebSocketDisconnect

AUTH = ("fixture", "fixture-password")
ORIGIN = "http://testserver"


@pytest.fixture
def browser_app(settings, monkeypatch):
    async def snapshot():
        return {"snapshot_age_seconds": 0, "database_ok": True}

    async def subscribe():
        yield {"type": "fixture-notification"}

    engine = SimpleNamespace(snapshot_view=snapshot, bus=SimpleNamespace(subscribe=subscribe))
    monkeypatch.setattr(api_module, "Orchestrator", lambda _: engine)
    app = api_module.create_app(settings.model_copy(update={"admin_password": AUTH[1]}))
    return app


def client_for(app, base_url=ORIGIN):
    # Deliberately no lifespan: these tests exercise actual middleware/routes only.
    return TestClient(app, base_url=base_url, follow_redirects=False)


@pytest.mark.parametrize("path", ["/", "/api/v1/snapshot"])
def test_page_and_poll_supply_notification_only_cookie(browser_app, path):
    client = client_for(browser_app)
    try:
        response = client.get(path, auth=AUTH)
        assert response.status_code == 200
        cookie = response.headers["set-cookie"]
        assert "HttpOnly" in cookie and "SameSite=strict" in cookie
        assert "Path=/ws" in cookie and "Max-Age=300" in cookie
        assert "Domain=" not in cookie and "Secure" not in cookie
        assert AUTH[1] not in cookie
        assert response.headers["cache-control"] == "private, no-store"
        with client.websocket_connect("/ws", headers={"Origin": ORIGIN}) as socket:
            assert socket.receive_json() == {"type": "fixture-notification"}
        # Even manually sending that cookie to API endpoints cannot grant authority.
        cookie_header = cookie.split(";", 1)[0]
        for method, target in [("GET", "/api/v1/snapshot"), ("PUT", "/api/v1/risk")]:
            result = client.request(method, target, headers={"Cookie": cookie_header})
            assert result.status_code == 401
            assert "set-cookie" not in result.headers
    finally:
        client.close()


@pytest.mark.parametrize("origin", [None, "null", "http://other.test", "http://testserver:8765"])
def test_cookie_cannot_bypass_origin(browser_app, origin):
    client = client_for(browser_app)
    client.get("/", auth=AUTH)
    headers = {} if origin is None else {"Origin": origin}
    with (
        pytest.raises(WebSocketDisconnect) as closed,
        client.websocket_connect("/ws", headers=headers),
    ):
        pass
    assert closed.value.code == (4401 if origin is None else 4403)
    client.close()


@pytest.mark.parametrize("header", ["", "Basic ###", "Bearer invalid", "Basic dGVzdDp3cm9uZw=="])
def test_bad_explicit_credentials_do_not_fall_back_to_cookie(browser_app, header):
    client = client_for(browser_app)
    client.get("/", auth=AUTH)
    with (
        pytest.raises(WebSocketDisconnect) as closed,
        client.websocket_connect("/ws", headers={"Origin": ORIGIN, "Authorization": header}),
    ):
        pass
    assert closed.value.code == 4401
    client.close()


def test_direct_basic_clients_and_passwordless_local_mode_remain_supported(browser_app, settings):
    client = client_for(browser_app)
    authorization = "Basic " + base64.b64encode(":".join(AUTH).encode()).decode()
    with client.websocket_connect("/ws", headers={"Authorization": authorization}) as socket:
        assert socket.receive_json()["type"] == "fixture-notification"
    client.close()
    local = client_for(api_module.create_app(settings))
    assert "set-cookie" not in local.get("/").headers
    with local.websocket_connect("/ws") as socket:
        assert socket.receive_json()["type"] == "fixture-notification"
    local.close()


def test_expiry_recovered_by_existing_poll_and_restart_revokes_cookie(
    browser_app, settings, monkeypatch
):
    clock = [1000]
    monkeypatch.setattr(sessions_module.time, "time", lambda: clock[0])
    client = client_for(browser_app)
    response = client.get("/", auth=AUTH)
    original = response.headers["set-cookie"].split(";", 1)[0]
    clock[0] += SESSION_SECONDS
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/ws", headers={"Origin": ORIGIN, "Cookie": original}),
    ):
        pass
    refreshed = client.get("/api/v1/snapshot", auth=AUTH)
    current = refreshed.headers["set-cookie"].split(";", 1)[0]
    assert current != original
    with client.websocket_connect("/ws", headers={"Origin": ORIGIN}) as socket:
        assert socket.receive_json()["type"] == "fixture-notification"
    restarted = client_for(
        api_module.create_app(settings.model_copy(update={"admin_password": "changed-password"}))
    )
    with (
        pytest.raises(WebSocketDisconnect),
        restarted.websocket_connect("/ws", headers={"Origin": ORIGIN, "Cookie": current}),
    ):
        pass
    assert restarted.get("/", auth=AUTH).status_code == 401
    assert restarted.get("/", auth=("fixture", "changed-password")).status_code == 200
    with restarted.websocket_connect("/ws", headers={"Origin": ORIGIN}) as socket:
        assert socket.receive_json()["type"] == "fixture-notification"
    client.close()
    restarted.close()


def test_https_cookie_and_two_ports_do_not_collide(browser_app):
    secure = client_for(browser_app, "https://testserver:8443")
    response = secure.get("/", auth=AUTH)
    assert "Secure" in response.headers["set-cookie"]
    with secure.websocket_connect(
        "wss://testserver:8443/ws", headers={"Origin": "https://testserver:8443"}
    ) as socket:
        assert socket.receive_json()["type"] == "fixture-notification"
    first = client_for(browser_app, "http://testserver:8765")
    second = client_for(browser_app, "http://testserver:8766")
    first_cookie = first.get("/", auth=AUTH).headers["set-cookie"].split(";", 1)[0]
    second_cookie = second.get("/", auth=AUTH).headers["set-cookie"].split(";", 1)[0]
    assert first_cookie.split("=", 1)[0] != second_cookie.split("=", 1)[0]
    for client, origin in [(first, "http://testserver:8765"), (second, "http://testserver:8766")]:
        with client.websocket_connect(
            origin.replace("http:", "ws:") + "/ws",
            headers={"Origin": origin, "Cookie": first_cookie + "; " + second_cookie},
        ) as socket:
            assert socket.receive_json()["type"] == "fixture-notification"
        client.close()
    secure.close()


@pytest.mark.parametrize("target", ["http://host:8765", "https://host", "http://[::1]:8765"])
def test_tokens_are_origin_bound_and_independent_of_latest_tab(target, monkeypatch):
    clock = [1000]
    monkeypatch.setattr(sessions_module.time, "time", lambda: clock[0])
    sessions = DashboardSessions()
    first = sessions.issue(target)
    clock[0] += 10
    second = sessions.issue(target)
    assert first != second
    assert sessions.valid(first, target) and sessions.valid(second, target)
    assert sessions.valid(first, target.replace("http", "ws", 1) + "/ws")
    assert not sessions.valid(first, "http://other:8765/ws")
    assert not sessions.valid(first, "https://host:8765/ws")
    assert not DashboardSessions().valid(first, target)


@pytest.mark.parametrize(
    "token",
    [
        None,
        "",
        "x" * 129,
        "v1.1000.x",
        "v1.9999999999999." + "a" * 64,
        "v1.001300." + "a" * 64,
        "v1.١٣٠٠." + "a" * 64,
        "v2.1300." + "a" * 64,
        "v1.1300." + "é" * 64,
        "v1.-1." + "a" * 64,
    ],
)
def test_malformed_tokens_fail_closed(token):
    assert not DashboardSessions().valid(token, ORIGIN)


@pytest.mark.parametrize(
    "target",
    [
        "http://host:bad",
        "file://host/ws",
        "http:///ws",
        "http://user:pass@host/ws",
        "http://[invalid/ws",
    ],
)
def test_malformed_targets_fail_closed(target):
    sessions = DashboardSessions()
    assert sessions.cookie_name(target) is None
    assert sessions.issue(target) is None
    assert not sessions.valid("irrelevant", target)


def test_tamper_expiry_and_backward_clock_are_rejected(monkeypatch):
    clock = [1000]
    monkeypatch.setattr(sessions_module.time, "time", lambda: clock[0])
    sessions = DashboardSessions()
    token = sessions.issue(ORIGIN)
    assert token is not None
    assert not sessions.valid(token[:-1] + ("a" if token[-1] != "a" else "b"), ORIGIN)
    clock[0] = 999
    assert not sessions.valid(token, ORIGIN)
    clock[0] = 1299
    assert sessions.valid(token, ORIGIN)
    clock[0] = 1300
    assert not sessions.valid(token, ORIGIN)


@pytest.mark.parametrize("path", ["/", "/api/v1/snapshot"])
def test_unauthenticated_reads_never_mint_cookie(browser_app, path):
    client = client_for(browser_app)
    for auth in (None, ("fixture", "incorrect")):
        response = client.get(path, auth=auth)
        assert response.status_code == 401
        assert "set-cookie" not in response.headers
    client.close()


@pytest.mark.parametrize("code", [401, 429, 503])
def test_failed_snapshot_does_not_issue_cookie(browser_app, code):
    async def unavailable():
        raise HTTPException(code, "fixture unavailable")

    browser_app.state.orchestrator.snapshot_view = unavailable
    client = client_for(browser_app)
    response = client.get("/api/v1/snapshot", auth=AUTH)
    assert response.status_code == code
    assert "set-cookie" not in response.headers
    client.close()


def test_cookie_cannot_be_relabelled_to_another_origin(browser_app):
    client = client_for(browser_app)
    cookie = client.get("/", auth=AUTH).headers["set-cookie"].split(";", 1)[0]
    name, token = cookie.split("=", 1)
    other_origin = "http://testserver:8766"
    other_name = DashboardSessions().cookie_name(other_origin)
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect(
            "ws://testserver:8766/ws",
            headers={"Origin": other_origin, "Cookie": f"{other_name}={token}"},
        ),
    ):
        pass
    authorization = "Basic " + base64.b64encode(":".join(AUTH).encode()).decode()
    # An obsolete/malformed cookie cannot block an otherwise valid native client.
    with client.websocket_connect(
        "/ws", headers={"Authorization": authorization, "Cookie": f"{name}=invalid"}
    ) as socket:
        assert socket.receive_json()["type"] == "fixture-notification"
    client.close()


def test_untrusted_forwarding_headers_do_not_change_cookie_origin(browser_app):
    client = client_for(browser_app)
    response = client.get(
        "/", auth=AUTH, headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "other.test"}
    )
    assert "Secure" not in response.headers["set-cookie"]
    assert response.headers["set-cookie"].startswith(DashboardSessions().cookie_name(ORIGIN) + "=")
    with client.websocket_connect("/ws", headers={"Origin": ORIGIN}) as socket:
        assert socket.receive_json()["type"] == "fixture-notification"
    client.close()


def test_handshake_rejection_logging_is_bounded_and_contains_no_secrets(browser_app, caplog):
    caplog.set_level(logging.INFO, logger="signal_arcade.api")
    client = client_for(browser_app)
    for _ in range(10):
        with (
            pytest.raises(WebSocketDisconnect),
            client.websocket_connect(
                "/ws",
                headers={"Origin": ORIGIN, "Cookie": "private-fixture-cookie=value"},
            ),
        ):
            pass
    records = [r.getMessage() for r in caplog.records if r.name == "signal_arcade.api"]
    assert records == ["Dashboard notification rejected: session"]
    assert "private-fixture-cookie" not in caplog.text
    assert AUTH[1] not in caplog.text
    client.close()
