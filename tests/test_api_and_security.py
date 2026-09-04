from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from signal_arcade import __version__
from signal_arcade.api import create_app
from signal_arcade.config import Settings
from signal_arcade.strategy import BASELINE_VERSION, INTEGRITY_POLICY_VERSION
from starlette.websockets import WebSocketDisconnect


def wait_for_season_operation(client: TestClient, state: str = "completed") -> dict[str, object]:
    for _ in range(200):
        operation = client.get("/api/v1/season-operation").json()
        if operation and operation["state"] == state:
            return operation
        time.sleep(0.01)
    raise AssertionError(f"season operation did not reach {state}")


def test_health_and_snapshot_are_paper_only(settings) -> None:  # type: ignore[no-untyped-def]
    app = create_app(settings)
    assert app.version == __version__
    with TestClient(app) as client:
        health = client.get("/api/v1/health")
        assert health.status_code == 200
        assert health.json()["ok"] is True
        assert health.json()["database_ok"] is True
        assert all(health.json()["background_tasks"].values())
        assert health.json()["paper_only"] is True
        assert health.json()["version"] == __version__
        snapshot = client.get("/api/v1/snapshot")
        assert snapshot.status_code == 200
        assert snapshot.json()["paper_only"] is True
        assert snapshot.json()["version"] == __version__
        assert all(snapshot.json()["background_tasks"].values())
        assert snapshot.json()["running"] is False
        assert snapshot.json()["portfolio"]["initialized"] is False
        assert snapshot.json()["learning"]["mode"] == "shadow"
        assert snapshot.json()["learning"]["demo_excluded"] is True
        assert snapshot.json()["ai_lab"]["mode"] == "off"
        assert snapshot.json()["coach"]["mode"] == "off"
        assert snapshot.json()["coach"]["influence"] == "none"
        assert snapshot.json()["coach"]["worker_running"] is True
        assert snapshot.json()["season_automation"]["enabled"] is False
        assert snapshot.json()["season_automation"]["state"] == "off"
        assert snapshot.json()["storage"]["model_storage_included"] is False
        assert snapshot.json()["storage"]["coach_reviews"] == 0
        assert snapshot.json()["storage"]["coach_hypotheses"] == 0
        assert snapshot.json()["storage"]["max_database_bytes"] == 5 * 1024**3
        learning = snapshot.json()["learning"]
        assert learning["nonlinear_entry"]["entry_only"] is True
        assert learning["champion_records"] == []
        assert learning["champion_journey_total"] == 0
        journey = client.get("/api/v1/learning/champion-journey?limit=8")
        assert journey.status_code == 200
        assert journey.json() == {"events": [], "total": 0, "next_cursor": None}
        stale_cursor = client.get(
            "/api/v1/learning/champion-journey?limit=8&cursor=old-cohort-event"
        )
        assert stale_cursor.status_code == 409


def test_automatic_season_policy_is_opt_in_validated_and_persistent(settings) -> None:  # type: ignore[no-untyped-def]
    with TestClient(create_app(settings)) as client:
        enabled = client.put("/api/v1/season-automation", json={"enabled": True})
        assert enabled.status_code == 200
        assert enabled.json()["enabled"] is True
        assert enabled.json()["state"] == "no_bankroll"
        assert (
            client.put(
                "/api/v1/season-automation",
                json={"enabled": False, "unexpected": True},
            ).status_code
            == 422
        )

    with TestClient(create_app(settings)) as restarted:
        policy = restarted.get("/api/v1/snapshot").json()["season_automation"]
        assert policy["enabled"] is True
        assert policy["grace_seconds"] == 24 * 60 * 60


def test_storage_budget_is_validated_saved_and_visible(settings) -> None:  # type: ignore[no-untyped-def]
    with TestClient(create_app(settings)) as client:
        assert (
            client.put(
                "/api/v1/storage-settings",
                json={"max_database_gb": 0.1, "raw_trade_retention_hours": 6},
            ).status_code
            == 422
        )
        saved = client.put(
            "/api/v1/storage-settings",
            json={"max_database_gb": 1.5, "raw_trade_retention_hours": 12},
        )
        assert saved.status_code == 200
        assert saved.json()["max_database_bytes"] == int(1.5 * 1024**3)
        assert saved.json()["raw_trade_retention_hours"] == 12
        snapshot = client.get("/api/v1/snapshot").json()
        assert snapshot["storage"]["raw_trade_retention_hours"] == 12


def test_empty_leaderboard_and_missing_decision_are_explicit(settings) -> None:  # type: ignore[no-untyped-def]
    with TestClient(create_app(settings)) as client:
        leaderboard = client.get("/api/v1/leaderboard?sort=profit")
        assert leaderboard.status_code == 200
        body = leaderboard.json()
        assert body["rows"] == []
        assert body["available_rows"] == 0
        assert body["summary"]["closed_trades"] == 0
        assert body["summary"]["open_trades"] == 0
        assert body["summary"]["total_fees_minor"] == 0
        assert body["summary"]["quote_currency"] == "SOL"
        assert body["summary"]["quote_decimals"] == 9
        setup = client.post(
            "/api/v1/portfolio/setup",
            json={"quote_currency": "USDC", "starting_amount": "100"},
        )
        assert setup.status_code == 200
        usdc_body = client.get("/api/v1/leaderboard?sort=profit").json()
        assert usdc_body["rows"] == []
        assert usdc_body["available_rows"] == 0
        assert usdc_body["summary"]["total_realized_pnl_minor"] == 0
        assert usdc_body["summary"]["total_fees_minor"] == 0
        assert usdc_body["summary"]["quote_currency"] == "USDC"
        assert usdc_body["summary"]["quote_decimals"] == 6
        assert client.get("/api/v1/decisions/missing").status_code == 404


def test_learning_starts_in_shadow_and_rejects_unproven_activation(settings) -> None:  # type: ignore[no-untyped-def]
    app = create_app(settings)
    with TestClient(app) as client:
        active = client.put("/api/v1/learning", json={"mode": "active"})
        assert active.status_code == 409
        assert "Solana Mainnet" in active.json()["detail"]
        paused = client.put("/api/v1/learning", json={"mode": "off"})
        assert paused.status_code == 200
        assert paused.json()["mode"] == "off"
        shadow = client.put("/api/v1/learning", json={"mode": "shadow"})
        assert shadow.status_code == 200
        assert shadow.json()["mode"] == "shadow"

    mainnet_settings = settings.model_copy(
        update={"demo_mode": False, "data_dir": settings.data_dir / "mainnet"}
    )
    with TestClient(create_app(mainnet_settings)) as client:
        active = client.put("/api/v1/learning", json={"mode": "active"})
        assert active.status_code == 409
        assert "forward and suspension gates" in active.json()["detail"]


def test_ai_lab_is_opt_in_curated_and_veto_gated(settings) -> None:  # type: ignore[no-untyped-def]
    with TestClient(create_app(settings)) as client:
        status = client.get("/api/v1/ai-lab")
        assert status.status_code == 200
        assert status.json()["mode"] == "off"
        assert status.json()["model_storage_counts_toward_app_limit"] is False
        assert {model["name"] for model in status.json()["catalog"]} == {
            "qwen3.5:2b",
            "phi4-mini:3.8b",
            "qwen3.5:4b",
            "qwen3.5:9b",
            "qwen3.5:27b",
        }
        shadow = client.put("/api/v1/ai-lab/mode", json={"mode": "shadow"})
        assert shadow.status_code == 200
        assert shadow.json()["mode"] == "shadow"
        guarded = client.put("/api/v1/ai-lab/mode", json={"mode": "guarded"})
        assert guarded.status_code == 409
        assert (
            client.post(
                "/api/v1/ai-lab/models/pull",
                json={"model": "unreviewed/model:latest"},
            ).status_code
            == 422
        )


def test_coach_research_and_contribution_permissions_are_independent_and_persistent(
    settings,
) -> None:  # type: ignore[no-untyped-def]
    with TestClient(create_app(settings)) as client:
        assert (
            client.put("/api/v1/ai-lab/coach-research", json={"enabled": True}).status_code == 409
        )
        assert (
            client.put(
                "/api/v1/ai-lab/coach-contribution",
                json={"enabled": True},
            ).status_code
            == 409
        )
        assert client.put("/api/v1/ai-lab/mode", json={"mode": "shadow"}).status_code == 200
        assert client.get("/api/v1/snapshot").json()["coach"]["research_enabled"] is True

        paused = client.put("/api/v1/ai-lab/coach-research", json={"enabled": False})
        assert paused.status_code == 200
        assert paused.json()["research_enabled"] is False
        assert paused.json()["mode"] == "off"
        assert client.get("/api/v1/ai-lab").json()["mode"] == "shadow"

        permission = client.put(
            "/api/v1/ai-lab/coach-contribution",
            json={"enabled": True},
        )
        assert permission.status_code == 200
        assert permission.json()["contribution_enabled"] is True
        assert (
            client.put(
                "/api/v1/ai-lab/coach-research",
                json={"enabled": False, "unexpected": True},
            ).status_code
            == 422
        )

    with TestClient(create_app(settings)) as restarted:
        coach = restarted.get("/api/v1/snapshot").json()["coach"]
        assert coach["research_enabled"] is False
        assert coach["contribution_enabled"] is True
        resumed = restarted.put(
            "/api/v1/ai-lab/coach-research",
            json={"enabled": True},
        )
        assert resumed.status_code == 200
        assert resumed.json()["research_enabled"] is True
        assert resumed.json()["mode"] == "shadow"


def test_coach_contribution_permission_can_be_revoked_while_local_ai_is_off(settings) -> None:  # type: ignore[no-untyped-def]
    with TestClient(create_app(settings)) as client:
        assert client.put("/api/v1/ai-lab/mode", json={"mode": "shadow"}).status_code == 200
        enabled = client.put(
            "/api/v1/ai-lab/coach-contribution",
            json={"enabled": True},
        )
        assert enabled.status_code == 200
        assert enabled.json()["contribution_enabled"] is True
        assert client.put("/api/v1/ai-lab/mode", json={"mode": "off"}).status_code == 200

        disabled = client.put(
            "/api/v1/ai-lab/coach-contribution",
            json={"enabled": False},
        )

        assert disabled.status_code == 200
        assert disabled.json()["contribution_enabled"] is False


def test_user_must_create_bankroll_before_explicit_start(settings) -> None:  # type: ignore[no-untyped-def]
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.post("/api/v1/engine/start").status_code == 409
        setup = client.post(
            "/api/v1/portfolio/setup",
            json={"quote_currency": "USDC", "starting_amount": "1250.50"},
        )
        assert setup.status_code == 200
        assert setup.json() == {
            "initialized": True,
            "quote_currency": "USDC",
            "starting_minor": 1_250_500_000,
            "running": False,
        }
        stopped = client.get("/api/v1/snapshot").json()
        assert stopped["running"] is False
        assert stopped["portfolio"]["cash_lamports"] == 1_250_500_000
        assert stopped["portfolio"]["quote_currency"] == "USDC"

        assert client.post("/api/v1/engine/start").json() == {"running": True}
        assert client.get("/api/v1/snapshot").json()["running"] is True
        assert client.post("/api/v1/engine/stop").json()["running"] is False
        after_stop = client.get("/api/v1/snapshot").json()
        assert after_stop["running"] is False
        assert after_stop["portfolio"]["initialized"] is True
        assert after_stop["portfolio"]["quote_currency"] == "USDC"


def test_bankroll_setup_rejects_excess_precision_and_reinitialization(settings) -> None:  # type: ignore[no-untyped-def]
    app = create_app(settings)
    with TestClient(app) as client:
        too_precise = client.post(
            "/api/v1/portfolio/setup",
            json={"quote_currency": "USDC", "starting_amount": "1.0000001"},
        )
        assert too_precise.status_code == 422
        assert client.get("/api/v1/snapshot").json()["portfolio"]["initialized"] is False

        assert (
            client.post(
                "/api/v1/portfolio/setup",
                json={"quote_currency": "SOL", "starting_amount": "2.5"},
            ).status_code
            == 200
        )
        duplicate = client.post(
            "/api/v1/portfolio/setup",
            json={"quote_currency": "USDC", "starting_amount": "1000"},
        )
        assert duplicate.status_code == 409


def test_reset_requires_exact_confirmation(settings) -> None:  # type: ignore[no-untyped-def]
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.post("/api/v1/reset", json={"confirmation": "reset"}).status_code == 400
        assert (
            client.post("/api/v1/reset", json={"confirmation": "RESET PAPER PORTFOLIO"}).status_code
            == 202
        )
        assert wait_for_season_operation(client)["stage"] == "completed"


def test_season_scorecards_survive_reset_and_number_the_next_bankroll(settings) -> None:  # type: ignore[no-untyped-def]
    app = create_app(settings)
    with TestClient(app) as client:
        assert (
            client.post(
                "/api/v1/portfolio/setup",
                json={"quote_currency": "SOL", "starting_amount": "1"},
            ).status_code
            == 200
        )
        first = client.get("/api/v1/seasons")
        assert first.status_code == 200
        first_body = first.json()
        assert first_body["summary"]["season_count"] == 1
        assert first_body["summary"]["comparison_group_count"] == 1
        assert first_body["summary"]["comparison_claims_available"] is True
        assert first_body["seasons"][0]["status"] == "current"
        assert first_body["seasons"][0]["net_return_fraction"] == 0
        assert first_body["current_profile_fingerprint"]
        comparison_key = (
            f"SOL:bankroll:1000000000:profile:"
            f"{first_body['current_profile_fingerprint']}:"
            "terminal:executable-boundary-v2"
        )
        assert first_body["current_comparison_key"] == comparison_key
        assert first_body["seasons"][0]["comparison_key"] == comparison_key
        assert first_body["comparison_groups"] == [
            {
                "comparison_key": comparison_key,
                "quote_currency": "SOL",
                "quote_decimals": 9,
                "starting_minor": 1_000_000_000,
                "terminal_policy_version": "executable-boundary-v2",
                "profile_provenance": "exact",
                "profile_fingerprint": first_body["current_profile_fingerprint"],
                "risk_mode": "balanced",
                "drawdown_policy": {
                    "kind": "default",
                    "custom_threshold_bps": None,
                },
                "effective_drawdown_bps": 1_500,
                "baseline_version": BASELINE_VERSION,
                "integrity_policy_version": INTEGRITY_POLICY_VERSION,
                "sizing_policy_version": "quality-size-v1",
                "first_season_number": 1,
                "last_season_number": 1,
                "has_current": True,
                "completed_count": 0,
                "comparable_count": 0,
                "boundary_types": ["open"],
                "season_count": 1,
            }
        ]
        assert first_body["profiles"] == [
            {
                "profile_fingerprint": first_body["current_profile_fingerprint"],
                "risk_mode": "balanced",
                "drawdown_policy": {
                    "kind": "default",
                    "custom_threshold_bps": None,
                },
                "effective_drawdown_bps": 1_500,
                "season_count": 1,
            }
        ]

        assert (
            client.post(
                "/api/v1/reset",
                json={"confirmation": "RESET PAPER PORTFOLIO"},
            ).status_code
            == 202
        )
        wait_for_season_operation(client)
        archived = client.get("/api/v1/seasons").json()
        assert archived["seasons"][0]["status"] == "completed"
        assert archived["seasons"][0]["ending_equity_minor"] == 1_000_000_000
        assert archived["seasons"][0]["terminal_reason"] == "manual_reset"
        archived_group = archived["comparison_groups"][0]
        assert archived_group["first_season_number"] == 1
        assert archived_group["last_season_number"] == 1
        assert archived_group["has_current"] is False
        assert archived_group["completed_count"] == 1
        assert archived_group["comparable_count"] == 0
        assert archived_group["boundary_types"] == ["reset"]

        assert (
            client.post(
                "/api/v1/portfolio/setup",
                json={"quote_currency": "USDC", "starting_amount": "100"},
            ).status_code
            == 200
        )
        mixed_currency = client.get("/api/v1/seasons").json()
        seasons = mixed_currency["seasons"]
        assert [(row["season_number"], row["status"]) for row in seasons] == [
            (1, "completed"),
            (2, "current"),
        ]
        assert seasons[1]["quote_currency"] == "USDC"
        assert mixed_currency["current_comparison_key"] == (
            f"USDC:bankroll:100000000:profile:"
            f"{mixed_currency['current_profile_fingerprint']}:"
            "terminal:executable-boundary-v2"
        )
        assert [group["quote_currency"] for group in mixed_currency["comparison_groups"]] == [
            "SOL",
            "USDC",
        ]
        assert [group["season_count"] for group in mixed_currency["comparison_groups"]] == [1, 1]
        assert mixed_currency["summary"]["comparison_group_count"] == 2
        assert mixed_currency["summary"]["comparison_claims_available"] is False
        assert mixed_currency["profiles"][0]["season_count"] == 2


def test_typed_drawdown_profiles_validate_and_persist_from_setup(settings) -> None:  # type: ignore[no-untyped-def]
    app = create_app(settings)
    with TestClient(app) as client:
        invalid = client.post(
            "/api/v1/portfolio/setup",
            json={
                "quote_currency": "SOL",
                "starting_amount": "1",
                "risk_mode": "balanced",
                "drawdown_policy": {
                    "kind": "custom",
                    "custom_threshold_bps": 10_000,
                },
            },
        )
        assert invalid.status_code == 422

        created = client.post(
            "/api/v1/portfolio/setup",
            json={
                "quote_currency": "SOL",
                "starting_amount": "1",
                "risk_mode": "balanced",
                "drawdown_policy": {"kind": "disabled"},
            },
        )
        assert created.status_code == 200
        snapshot = client.get("/api/v1/snapshot").json()
        assert snapshot["season_profile"]["drawdown_policy"] == {
            "kind": "disabled",
            "custom_threshold_bps": None,
        }
        assert snapshot["season_profile"]["effective_drawdown_bps"] is None
        assert snapshot["portfolio"]["risk_halted"] is False


def test_profile_transition_strategy_is_typed_and_persisted(settings) -> None:  # type: ignore[no-untyped-def]
    app = create_app(settings)
    with TestClient(app) as client:
        assert (
            client.post(
                "/api/v1/portfolio/setup",
                json={"quote_currency": "SOL", "starting_amount": "1"},
            ).status_code
            == 200
        )
        assert client.post("/api/v1/engine/start").status_code == 200
        invalid = client.put(
            "/api/v1/risk",
            json={"mode": "safe", "transition_strategy": "pretend_everything_sold"},
        )
        assert invalid.status_code == 422

        requested = client.put(
            "/api/v1/risk",
            json={"mode": "safe", "transition_strategy": "end_now"},
        )
        assert requested.status_code == 200
        assert requested.json()["transition_strategy"] == "end_now"
        assert requested.json()["manual_settlement_deadline"] is not None


def test_next_season_request_validates_and_persists_exact_bankroll(settings) -> None:  # type: ignore[no-untyped-def]
    app = create_app(settings)
    with TestClient(app) as client:
        uninitialized = client.put(
            "/api/v1/risk",
            json={
                "mode": "safe",
                "quote_currency": "USDC",
                "starting_amount": "200",
            },
        )
        assert uninitialized.status_code == 409
        assert "create a paper bankroll" in uninitialized.json()["detail"]

        assert (
            client.post(
                "/api/v1/portfolio/setup",
                json={"quote_currency": "SOL", "starting_amount": "1"},
            ).status_code
            == 200
        )

        partial = client.put(
            "/api/v1/risk",
            json={"mode": "safe", "quote_currency": "USDC"},
        )
        assert partial.status_code == 422
        too_precise = client.put(
            "/api/v1/risk",
            json={
                "mode": "safe",
                "quote_currency": "USDC",
                "starting_amount": "1.0000001",
            },
        )
        assert too_precise.status_code == 422

        exact = client.put(
            "/api/v1/risk",
            json={
                "mode": "aggressive",
                "drawdown_policy": {"kind": "disabled"},
                "quote_currency": "USDC",
                "starting_amount": "200",
            },
        )
        assert exact.status_code == 200
        assert exact.json()["transition_required"] is False
        snapshot = client.get("/api/v1/snapshot").json()
        assert snapshot["portfolio"]["quote_currency"] == "USDC"
        assert snapshot["portfolio"]["starting_lamports"] == 200_000_000
        assert snapshot["season_profile"]["risk_mode"] == "aggressive"
        assert snapshot["season_profile"]["drawdown_policy"]["kind"] == "disabled"


def test_state_changes_and_websockets_reject_cross_origin_requests(settings) -> None:  # type: ignore[no-untyped-def]
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.put(
            "/api/v1/risk",
            json={"mode": "safe"},
            headers={"Origin": "http://testserver:9999"},
        )
        assert response.status_code == 403
        with (
            pytest.raises(WebSocketDisconnect) as closed,
            client.websocket_connect("/ws", headers={"Origin": "http://untrusted.example"}),
        ):
            pass
        assert closed.value.code == 4403


def test_non_loopback_http_and_websocket_require_password(tmp_path: Path) -> None:
    settings = Settings(
        bind="0.0.0.0",  # noqa: S104 - deliberate non-loopback security test
        admin_password="test-password",  # noqa: S106 - test-only credential
        data_dir=tmp_path,
        demo_mode=True,
        _env_file=None,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/api/v1/health").status_code == 200
        assert client.get("/api/v1/snapshot").status_code == 401
        assert client.get("/api/v1/snapshot", auth=("any-user", "test-password")).status_code == 200
        with pytest.raises(WebSocketDisconnect) as closed, client.websocket_connect("/ws"):
            pass
        assert closed.value.code == 4401


def test_backend_contains_no_live_execution_primitives() -> None:
    backend = Path(__file__).parents[1] / "backend" / "signal_arcade"
    forbidden = ("keypair.from_secret", "sendtransaction", "signtransaction", "seed_phrase")
    text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore").lower() for path in backend.rglob("*.py")
    )
    for primitive in forbidden:
        assert primitive not in text


def _provider_configuration(client: TestClient) -> dict[str, object]:
    providers = client.get("/api/v1/provider-settings").json()["providers"]
    return {name: provider["policy"] for name, provider in providers.items()}


def test_free_rpc_presets_reserve_capacity_for_byte_metered_streams(settings) -> None:  # type: ignore[no-untyped-def]
    with TestClient(create_app(settings)) as client:
        provider_settings = client.get("/api/v1/provider-settings").json()
        presets = {item["id"]: item for item in provider_settings["presets"]["solana"]}
        assert presets["helius_free"]["monthly_limit"] == 500_000
        assert presets["helius_economy"] == {
            "id": "helius_economy",
            "label": "Helius Economy (keyed HTTP + public stream)",
            "requests_per_minute": 600,
            "monthly_limit": 500_000,
            "paid_mode": False,
        }
        assert presets["alchemy_free"]["monthly_limit"] == 1_500_000
        assert presets["alchemy_free"]["requests_per_minute"] == 3_000
        assert "uncompressed bytes" in provider_settings["notes"]["streaming"]


def test_provider_secrets_are_write_only_and_endpoints_are_redacted(settings) -> None:  # type: ignore[no-untyped-def]
    app = create_app(settings)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        secret = "test-helius-secret"  # noqa: S105 - test-only sentinel
        response = client.put(
            "/api/v1/provider-settings",
            json={
                "configuration": _provider_configuration(client),
                "secrets": {
                    "solana_http": f"https://mainnet.helius-rpc.com/?api-key={secret}",
                    "solana_ws": f"wss://mainnet.helius-rpc.com/?api-key={secret}",
                    "jupiter_api_key": "test-jupiter-secret",
                },
            },
        )
        assert response.status_code == 200
        serialized = response.text
        assert secret not in serialized
        assert "test-jupiter-secret" not in serialized
        provider_settings = response.json()["provider_settings"]
        assert provider_settings["providers"]["solana"]["endpoint"] == (
            "https://mainnet.helius-rpc.com"
        )
        assert provider_settings["providers"]["jupiter"]["api_key_configured"] is True
        assert provider_settings["providers"]["solana"]["http_source"] == "saved_override"
        assert provider_settings["providers"]["solana"]["stream_source"] == "saved_override"

    restarted = create_app(settings)
    with TestClient(restarted, base_url="http://127.0.0.1") as client:
        saved = client.get("/api/v1/provider-settings").json()
        assert saved["providers"]["solana"]["custom_endpoint"] is True
        assert saved["providers"]["jupiter"]["api_key_configured"] is True
        assert "test-helius-secret" not in str(saved)
        assert "test-jupiter-secret" not in str(saved)


def test_provider_secret_submission_requires_https_or_localhost(settings) -> None:  # type: ignore[no-untyped-def]
    app = create_app(settings)
    with TestClient(app, base_url="http://192.168.1.20") as client:
        response = client.put(
            "/api/v1/provider-settings",
            json={
                "configuration": _provider_configuration(client),
                "secrets": {"jupiter_api_key": "must-not-cross-plaintext-lan"},
            },
        )
        assert response.status_code == 400
        assert not (settings.data_dir / "provider-secrets.json").exists()


def test_paid_provider_plan_requires_a_monthly_hard_cap(settings) -> None:  # type: ignore[no-untyped-def]
    app = create_app(settings)
    with TestClient(app) as client:
        configuration = _provider_configuration(client)
        assert isinstance(configuration["jupiter"], dict)
        configuration["jupiter"] = {
            **configuration["jupiter"],
            "label": "Unbounded paid plan",
            "monthly_limit": None,
            "paid_mode": True,
        }
        response = client.put(
            "/api/v1/provider-settings",
            json={"configuration": configuration},
        )
        assert response.status_code == 422


def test_provider_endpoint_rejects_remote_plaintext_transport(settings) -> None:  # type: ignore[no-untyped-def]
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.put(
            "/api/v1/provider-settings",
            json={
                "configuration": _provider_configuration(client),
                "secrets": {"solana_http": "http://rpc.example.test/api-key"},
            },
        )
        assert response.status_code == 422


def test_health_endpoint_remains_bounded_if_sqlite_probe_stalls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(data_dir=tmp_path, demo_mode=True, _env_file=None)
    app = create_app(settings)

    def stalled_probe() -> bool:
        time.sleep(0.8)
        return True

    monkeypatch.setattr(app.state.orchestrator.database, "health_check", stalled_probe)
    with TestClient(app) as client:
        started = time.monotonic()
        response = client.get("/api/v1/health")
        elapsed = time.monotonic() - started

    assert response.status_code == 200
    assert response.json()["database_ok"] is False
    assert response.json()["ok"] is False
    assert elapsed < 0.75
