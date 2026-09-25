"""Compact display construction preserves live feature caches and later decision evidence."""

from copy import deepcopy
from datetime import timedelta

import pytest
import signal_arcade.intelligence.features as features_module
from signal_arcade.orchestrator import _UI_TOKEN_VALUE_NAMES, _compact_feature_snapshot
from test_activity_evidence import NOW, snapshot_with, trade


@pytest.mark.parametrize("age", [0, 0.999, 1.0, 60, 301])
@pytest.mark.parametrize("scenario", ["normal", "stale", "unverified", "unknown"])
def test_projection_matches_full_view_and_preserves_following_snapshot(age, scenario):
    engine, state, _ = snapshot_with(
        [trade(10_000, wallet="dust"), trade(25_000_000, wallet="buyer")]
    )
    state.rolling_trade_metrics = None
    if scenario == "stale":
        state.last_event_at = NOW - timedelta(seconds=600)
    elif scenario == "unverified":
        state.venue = "pump_swap"
        state.route_verified = False
    elif scenario == "unknown":
        state.name = "Unknown token"
        state.symbol = "?"
        state.identity_source = "unavailable"
    original = deepcopy(state)
    projected_state = deepcopy(state)
    now = NOW + timedelta(seconds=age)
    full = engine._snapshot_state(original, now)
    compact = engine._snapshot_state(projected_state, now, value_names=_UI_TOKEN_VALUE_NAMES)
    assert compact.model_dump(mode="json") == _compact_feature_snapshot(full, _UI_TOKEN_VALUE_NAMES)
    assert projected_state == original
    assert engine._snapshot_state(
        original, now + timedelta(milliseconds=500), include_activity=True
    ) == engine._snapshot_state(
        projected_state, now + timedelta(milliseconds=500), include_activity=True
    )


def test_projection_allocates_only_served_values_and_does_not_change_default(monkeypatch):
    engine, state, _ = snapshot_with([trade(25_000_000, wallet="buyer")])
    calls = []
    constructor = features_module.DataValue

    def counted(**kwargs):
        calls.append(kwargs)
        return constructor(**kwargs)

    monkeypatch.setattr(features_module, "DataValue", counted)
    compact = engine._snapshot_state(state, NOW, value_names=_UI_TOKEN_VALUE_NAMES)
    assert set(compact.values) == _UI_TOKEN_VALUE_NAMES
    assert len(calls) == len(_UI_TOKEN_VALUE_NAMES)
    calls.clear()
    assert engine._snapshot_state(state, NOW, value_names=frozenset()).values == {}
    assert not calls
    full = engine._snapshot_state(state, NOW)
    assert len(full.values) > len(compact.values)
    assert len(calls) == len(full.values)
