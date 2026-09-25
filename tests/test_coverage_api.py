import time

import pytest
from fastapi.testclient import TestClient
from signal_arcade.api import create_app


def refreshed_learning(client, percent):
    # An invalidated dashboard may return its timestamped previous view while the
    # coalesced refresh yields to storage/market work. The save response is authoritative;
    # require the fresh API view within a bound, not necessarily on the first read.
    deadline = time.monotonic() + 10
    while True:
        learning = client.get("/api/v1/snapshot").json()["learning"]
        if learning["coverage_policy"]["percent"] == percent:
            return learning
        assert time.monotonic() < deadline, "Dashboard did not refresh the saved coverage policy"
        time.sleep(0.05)


def test_coverage_api_requires_existing_admin_authentication(settings):
    app = create_app(settings.model_copy(update={"admin_password": "fixture-password"}))
    with TestClient(app) as client:
        body = {"percent": 65, "expected_revision": 0}
        assert client.put("/api/v1/learning/coverage", json=body).status_code == 401
        assert app.state.orchestrator.learning.coverage_policy.revision == 0
        response = client.put(
            "/api/v1/learning/coverage", json=body, auth=("test", "fixture-password")
        )
        assert response.status_code == 200


@pytest.mark.parametrize("percent", [55, 60, 65, 70])
def test_coverage_api_saves_without_starting_learning_or_granting_permission(settings, percent):
    with TestClient(create_app(settings)) as client:
        before = client.get("/api/v1/snapshot").json()["learning"]
        assert before["coverage_policy"]["percent"] == 70
        assert before["coverage_policy"]["options"] == [70, 65, 60, 55]
        saved = client.put(
            "/api/v1/learning/coverage", json={"percent": percent, "expected_revision": 0}
        )
        assert saved.status_code == 200 and saved.json()["percent"] == percent
        revision = int(percent != 70)
        assert saved.json()["revision"] == revision
        after = refreshed_learning(client, percent)
        assert after["coverage_policy"]["percent"] == percent
        assert after["coverage_policy"]["revision"] == revision
        for key in ("mode", "consent_granted", "auto_participation", "active_skill_versions"):
            assert after[key] == before[key]
        conflict = client.put(
            "/api/v1/learning/coverage", json={"percent": 60, "expected_revision": revision + 1}
        )
        assert conflict.status_code == 409
    with TestClient(create_app(settings)) as client:
        assert (
            client.get("/api/v1/snapshot").json()["learning"]["coverage_policy"]["percent"]
            == percent
        )


@pytest.mark.parametrize(
    "body",
    [
        {"percent": 65.0, "expected_revision": 0},
        {"percent": "65", "expected_revision": 0},
        {"percent": True, "expected_revision": 0},
        {"percent": 54, "expected_revision": 0},
        {"percent": 56, "expected_revision": 0},
        {"percent": 55.0, "expected_revision": 0},
        {"percent": "55", "expected_revision": 0},
        {"percent": 65, "expected_revision": False},
        {"percent": 65, "expected_revision": -1},
        {"percent": 65, "expected_revision": 0, "enable": True},
    ],
)
def test_coverage_api_rejects_malformed_requests(settings, body):
    app = create_app(settings)
    # Request validation needs no background workers or live services.
    with TestClient(app) as client:
        assert client.put("/api/v1/learning/coverage", json=body).status_code == 422
        assert app.state.orchestrator.learning.coverage_policy.revision == 0


def test_coverage_api_respects_origin_and_upgrade_boundary(settings, monkeypatch):
    app = create_app(settings)
    with TestClient(app) as client:
        body = {"percent": 65, "expected_revision": 0}
        response = client.put(
            "/api/v1/learning/coverage", json=body, headers={"Origin": "http://untrusted.example"}
        )
        assert response.status_code == 403
        with monkeypatch.context() as patch:
            patch.setattr(
                type(app.state.orchestrator), "maintenance_active", property(lambda _: True)
            )
            response = client.put("/api/v1/learning/coverage", json=body)
        assert response.status_code == 409
        assert app.state.orchestrator.learning.coverage_policy.revision == 0
