from __future__ import annotations

import base64
import gc
import json
import weakref

import pytest
from fastapi.testclient import TestClient
from signal_arcade.api import create_app
from signal_arcade.intelligence.nonlinear import fit_xgboost, load_xgboost
from signal_arcade.models import (
    ChallengerSkill,
    ChallengerSkillArtifact,
    RiskMode,
    StatisticalModelFamily,
)
from starlette.websockets import WebSocketDisconnect
from test_v1104_training_history import training_fixture

# These tests intentionally stress internal cache boundaries and use test-only credentials.
# ruff: noqa: SLF001, S105, S106


@pytest.mark.parametrize(
    ("password", "supplied", "expected"),
    [
        ("test-password", "wrong-p\u00e4ssword", 401),
        ("test-p\u00e4ssword", "test-p\u00e4ssword", 200),
    ],
)
def test_unicode_authentication_has_an_explicit_result(settings, password, supplied, expected):
    configured = settings.model_copy(update={"admin_password": password})
    header = "Basic " + base64.b64encode(("admin:" + supplied).encode()).decode()
    with TestClient(create_app(configured), raise_server_exceptions=False) as client:
        response = client.get("/api/v1/snapshot", headers={"Authorization": header})
        assert response.status_code == expected
        if expected == 401:
            with (
                pytest.raises(WebSocketDisconnect) as closed,
                client.websocket_connect("/ws", headers={"Authorization": header}),
            ):
                pass
            assert closed.value.code == 4401
        else:
            with client.websocket_connect("/ws", headers={"Authorization": header}):
                pass


def test_nonlinear_cache_releases_old_models_and_can_reload_them(settings, monkeypatch):
    learner, database, _ = training_fixture(settings)
    loaded = []

    class Model:
        pass

    def load(version):
        loaded.append(version)
        return {
            "family": "xgboost",
            "payload_format": "json",
            "payload_digest": "digest",
            "payload": b"model",
        }

    monkeypatch.setattr(database, "load_statistical_model_artifact", load)
    monkeypatch.setattr("signal_arcade.intelligence.learning.load_xgboost", lambda _: Model())

    def artifact(index):
        return ChallengerSkillArtifact(
            version=f"model-{index}",
            skill=ChallengerSkill.ENTRY,
            model_family=StatisticalModelFamily.XGBOOST,
            payload_format="json",
            payload_digest="digest",
            risk_mode=RiskMode.BALANCED,
            configuration_fingerprint="cache-test",
            baseline_version="baseline-v1.5",
            feature_schema_version="challenger-features-v4",
        )

    try:
        frequent = learner._load_nonlinear_artifact(artifact(0))
        old = weakref.ref(learner._load_nonlinear_artifact(artifact(1)))
        for index in range(2, 40):
            learner._load_nonlinear_artifact(artifact(index))
            assert learner._load_nonlinear_artifact(artifact(0)) is frequent
        assert len(learner._nonlinear_model_cache) <= 8
        gc.collect()
        assert old() is None
        assert loaded.count("model-0") == 1
        assert learner._load_nonlinear_artifact(artifact(1)) is not None
        assert loaded.count("model-1") == 2
        # Missing payloads are cached too, but cannot grow an unbounded negative cache.
        monkeypatch.setattr(database, "load_statistical_model_artifact", lambda _: None)
        for index in range(40, 80):
            assert learner._load_nonlinear_artifact(artifact(index)) is None
        assert len(learner._nonlinear_model_cache) <= 8
        # Retention also drops decoded objects for artifacts it has just archived.
        retained = list(learner._nonlinear_model_cache)
        monkeypatch.setattr(database, "prune_challenger_artifacts", lambda *_a, **_k: retained)
        learner._prune_model_history()
        assert not learner._nonlinear_model_cache
    finally:
        database.close()


def test_reloaded_nonlinear_model_keeps_its_single_thread_budget():
    rows = [[float(index % 7), float(index % 5)] for index in range(250)]
    payload = fit_xgboost(rows, [sum(row) / 10 for row in rows])
    assert payload is not None
    restored = load_xgboost(payload)
    config = json.loads(restored.save_config())
    assert int(config["learner"]["generic_param"]["nthread"]) == 1
