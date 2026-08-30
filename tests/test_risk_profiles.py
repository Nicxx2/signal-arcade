from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from signal_arcade.database import SCHEMA_VERSION, Database
from signal_arcade.models import RiskMode
from signal_arcade.risk_profiles import (
    DrawdownPolicy,
    DrawdownPolicyKind,
    build_season_profile,
)


def test_profile_fingerprint_is_stable_and_behavior_specific() -> None:
    first = build_season_profile(RiskMode.BALANCED, learning_fingerprint="learning-a")
    second = build_season_profile(RiskMode.BALANCED, learning_fingerprint="learning-b")
    safer = build_season_profile(RiskMode.SAFE, learning_fingerprint="learning-a")

    assert first.profile_fingerprint == second.profile_fingerprint
    assert first.profile_fingerprint != safer.profile_fingerprint
    assert first.effective_drawdown_bps == 1_500
    assert first.risk_limits["max_open_positions"] == 4


def test_drawdown_policy_is_typed_and_bounded() -> None:
    disabled = build_season_profile(
        RiskMode.BALANCED,
        drawdown_policy=DrawdownPolicy(kind=DrawdownPolicyKind.DISABLED),
    )
    custom = build_season_profile(
        RiskMode.BALANCED,
        drawdown_policy=DrawdownPolicy(
            kind=DrawdownPolicyKind.CUSTOM,
            custom_threshold_bps=2_000,
        ),
    )

    assert disabled.effective_drawdown_bps is None
    assert custom.effective_drawdown_bps == 2_000
    assert disabled.profile_fingerprint != custom.profile_fingerprint
    with pytest.raises(ValueError, match="requires a threshold"):
        DrawdownPolicy(kind=DrawdownPolicyKind.CUSTOM)
    with pytest.raises(ValueError):
        DrawdownPolicy(kind=DrawdownPolicyKind.CUSTOM, custom_threshold_bps=10_000)


def test_default_equivalent_custom_drawdown_is_canonicalized() -> None:
    default = build_season_profile(RiskMode.BALANCED)
    equivalent = build_season_profile(
        RiskMode.BALANCED,
        drawdown_policy=DrawdownPolicy(
            kind=DrawdownPolicyKind.CUSTOM,
            custom_threshold_bps=1_500,
        ),
    )

    assert equivalent.drawdown_policy.kind == DrawdownPolicyKind.DEFAULT
    assert equivalent.drawdown_policy.custom_threshold_bps is None
    assert equivalent.profile_fingerprint == default.profile_fingerprint


def test_drawdown_profiles_separate_seasons_without_fragmenting_personality_learning() -> None:
    learning = "balanced-learning-lineage"
    default = build_season_profile(RiskMode.BALANCED, learning_fingerprint=learning)
    custom = build_season_profile(
        RiskMode.BALANCED,
        drawdown_policy=DrawdownPolicy(
            kind=DrawdownPolicyKind.CUSTOM,
            custom_threshold_bps=8_000,
        ),
        learning_fingerprint=learning,
    )
    disabled = build_season_profile(
        RiskMode.BALANCED,
        drawdown_policy=DrawdownPolicy(kind=DrawdownPolicyKind.DISABLED),
        learning_fingerprint=learning,
    )
    aggressive = build_season_profile(
        RiskMode.AGGRESSIVE,
        learning_fingerprint="aggressive-learning-lineage",
    )

    assert (
        len(
            {
                default.profile_fingerprint,
                custom.profile_fingerprint,
                disabled.profile_fingerprint,
            }
        )
        == 3
    )
    assert {
        default.learning_fingerprint,
        custom.learning_fingerprint,
        disabled.learning_fingerprint,
    } == {learning}
    assert aggressive.learning_fingerprint != default.learning_fingerprint


def test_new_season_persists_exact_profile_without_relabelling_legacy(tmp_path: Path) -> None:
    path = tmp_path / "profiles.sqlite3"
    database = Database(path)
    profile = build_season_profile(RiskMode.SAFE).model_dump(mode="json")
    database.initialize_portfolio("season-exact", 1_000_000_000, "SOL", profile)

    exact = database.current_paper_season()
    assert exact is not None
    assert exact["profile_provenance"] == "exact"
    assert exact["profile"]["profile_fingerprint"] == profile["profile_fingerprint"]
    database.close()

    legacy_path = tmp_path / "legacy-v7.sqlite3"
    connection = sqlite3.connect(legacy_path)
    connection.executescript(
        """
        CREATE TABLE paper_seasons (
            season_id TEXT PRIMARY KEY,
            season_number INTEGER NOT NULL UNIQUE,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            quote_currency TEXT NOT NULL,
            quote_decimals INTEGER NOT NULL,
            starting_minor INTEGER NOT NULL,
            ending_equity_minor INTEGER,
            last_known_ending_equity_minor INTEGER,
            peak_equity_minor INTEGER NOT NULL DEFAULT 0,
            realized_pnl_minor INTEGER NOT NULL DEFAULT 0,
            net_pnl_minor INTEGER NOT NULL DEFAULT 0,
            total_fees_minor INTEGER NOT NULL DEFAULT 0,
            closed_trades INTEGER NOT NULL DEFAULT 0,
            wins INTEGER NOT NULL DEFAULT 0,
            losses INTEGER NOT NULL DEFAULT 0,
            break_even INTEGER NOT NULL DEFAULT 0,
            ending_drawdown_fraction REAL NOT NULL DEFAULT 0,
            open_positions INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL
        );
        INSERT INTO paper_seasons(
            season_id,season_number,started_at,quote_currency,quote_decimals,
            starting_minor,peak_equity_minor,status
        ) VALUES('legacy',1,'2026-01-01T00:00:00+00:00','SOL',9,100,100,'completed');
        PRAGMA user_version=7;
        """
    )
    connection.close()

    migrated = Database(legacy_path)
    assert SCHEMA_VERSION == 9
    legacy = migrated.list_paper_seasons()[0]
    assert legacy["profile"] is None
    assert legacy["profile_provenance"] == "legacy_unknown"
    migrated.close()
