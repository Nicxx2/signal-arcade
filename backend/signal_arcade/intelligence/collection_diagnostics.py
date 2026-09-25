"""Bounded, process-local collection counters, never evidence or qualification inputs."""

from __future__ import annotations

import time
from collections import OrderedDict
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from ..diagnostics_store import MAX_EVENT_PAYLOAD, encode


def _expiry_parts(event: dict[str, Any]) -> list[dict[str, Any]]:
    """Keep exact counters even near saturation, within the unchanged event byte limit."""
    try:
        encode(event, max_payload=MAX_EVENT_PAYLOAD)
        return [event]
    except ValueError:
        # Fixed valid metadata and one horizon always fit. Retain the recorder's
        # normal error handling if an unexpected malformed event reaches this point.
        if len(event["horizons"]) <= 1:
            return [event]
        middle = len(event["horizons"]) // 2
        result = []
        for start, end in ((0, middle), (middle, len(event["horizons"]))):
            result.extend(
                _expiry_parts(
                    {
                        **event,
                        "horizons": event["horizons"][start:end],
                        "last_rpc": event["last_rpc"][start:end],
                    }
                )
            )
        return result


class CollectionTargets(dict[str, list[tuple[str, int]]]):
    """Request-local identities; never exported or used to choose evidence."""

    def __init__(self) -> None:
        super().__init__()
        self.identities: dict[str, list[tuple[str, int, str]]] = {}


MAX_TRACKED_CHECKPOINTS = 20_000
SELECTION_REASONS = ("eligible", "fresh_cache", "excluded_identity", "missing_state", "expired")
EXPIRY_RPC_STAGES = (
    "unknown",
    "no_rpc_selection",
    "rpc_selected",
    "rpc_requested",
    "rpc_accepted",
    "rpc_rejected",
    "rpc_identity",
    "rpc_address_limit",
    "rpc_unavailable",
    "rpc_timeout",
    "rpc_error",
    "rpc_cancelled",
    "rpc_discarded",
)
COLLECTION_STAGES = frozenset(
    {
        "cache_due",
        "cache_selected",
        "rpc_due",
        "rpc_selected",
        "rpc_requested",
        "rpc_accepted",
        "rpc_rejected",
        "rpc_identity",
        "rpc_address_limit",
        "rpc_unavailable",
        "rpc_timeout",
        "rpc_error",
        "rpc_cancelled",
        "rpc_discarded",
        "usable",
        "unavailable",
        "expired",
    }
)


class CollectionDiagnostics:
    def __init__(self) -> None:
        self.scope = uuid4().hex[:12]
        self.started_at = datetime.now(UTC).isoformat()
        self._counts: dict[str, dict[str, int]] = {}
        self._pending: OrderedDict[tuple[str, int, str], list[str]] = OrderedDict()
        self._expiry: dict[str, dict[str, int]] = {}
        self._selection_passes = 0
        self._selection_latest: dict[str, Any] | None = None
        self._selection_next_monotonic = 0.0

    def selection_sample_due(self) -> bool:
        """Sample at most once a minute; blocked/cached passes consume no slot."""
        return self._selection_latest is None or time.monotonic() >= self._selection_next_monotonic

    def selection_sample(
        self,
        now: datetime,
        counts: dict[str, list[list[int]]],
        routes: dict[str, list[int]],
        budget: list[int],
        *,
        clock_unclassified: dict[str, int] | None = None,
        selected_bands: dict[str, list[int]] | None = None,
        guards_passed: bool = False,
    ) -> None:
        """One admitted RPC pass, not unique losses or a history-wide population."""
        self._selection_passes = min(2**53 - 1, self._selection_passes + 1)
        self._selection_latest = {
            "sampled_at": now.timestamp(),
            "pass": self._selection_passes,
            "counts": counts,
            "routes": routes,
            "budget": budget,
            "clock_unclassified": clock_unclassified or {"discovery": 0, "policy": 0},
            "selected_bands": selected_bands,
            "guard_context": "preselection_passed" if guards_passed else "not_reported",
        }
        self._selection_next_monotonic = time.monotonic() + 60

    def selection_events(self) -> list[dict[str, Any]]:
        sample = self._selection_latest
        if sample is None:
            return []
        # Separate small lane events preserve the existing compressed event cap.
        return [
            {
                "kind": "collection_selection",
                "version": 1,
                "at": time.time(),
                "scope": self.scope,
                "lane": lane,
                "sampled_at": sample["sampled_at"],
                "pass": sample["pass"],
                "horizons": [60, 300, 600, 900, 1200],
                "reasons": list(SELECTION_REASONS),
                "counts": sample["counts"][lane],
                # Excluded trajectories with unresolved work but an incomparable
                # clock. Their due/expired status is unknown, not a healthy zero.
                "clock_unclassified": sample["clock_unclassified"][lane],
                # Eligible unique mints with <=5s, (5,15]s and >15s remaining;
                # selected unique mints in this lane (shared mints count in both).
                "routes": sample["routes"][lane],
                # Configured cap, eligible deduplicated mints, scheduler selections.
                # Actual request rejection/address/account results are separate.
                "budget": sample["budget"],
                # Same pass and original lane clocks, before shared-mint deduplication.
                # Unselected work is a sampled opportunity, never a unique lost outcome.
                "selected_bands": (
                    sample["selected_bands"][lane] if sample.get("selected_bands") else None
                ),
                "unselected_bands": (
                    [
                        sample["routes"][lane][i] - sample["selected_bands"][lane][i]
                        for i in range(3)
                    ]
                    if sample.get("selected_bands")
                    else None
                ),
                "guard_context": sample.get("guard_context", "not_reported"),
            }
            for lane in ("discovery", "policy")
        ]

    def track(self, lane: str, horizon: int, trajectory_id: str, *, enrolled: bool = False) -> None:
        if (
            not trajectory_id
            or lane not in {"policy", "discovery"}
            or horizon not in {60, 300, 600, 900, 1200}
        ):
            return
        key = (lane, horizon, trajectory_id)
        if key not in self._pending:
            self._pending[key] = ["no_rpc_selection" if enrolled else "unknown"]
            while len(self._pending) > MAX_TRACKED_CHECKPOINTS:
                self._pending.popitem(last=False)

    def enrolled(self, lane: str, trajectory_id: str) -> None:
        for horizon in (60, 300, 600, 900, 1200):
            self.track(lane, horizon, trajectory_id, enrolled=True)

    def record(self, lane: str, horizon: int, stage: str, *, trajectory_id: str = "") -> None:
        if lane not in {"policy", "discovery"} or horizon not in {60, 300, 600, 900, 1200}:
            return
        if stage not in COLLECTION_STAGES:
            return
        counts = self._counts.setdefault(f"{lane}_{horizon}", {})
        counts[stage] = min(2**63 - 1, counts.get(stage, 0) + 1)
        if stage in {"usable", "unavailable", "expired"}:
            last = self._pending.pop((lane, horizon, trajectory_id), ["unknown"])[0]
            if stage == "expired":
                expiry = self._expiry.setdefault(f"{lane}_{horizon}", {})
                expiry[last] = min(2**63 - 1, expiry.get(last, 0) + 1)

    def record_targets(
        self,
        targets: dict[str, list[tuple[str, int]]],
        stage: str,
        mints: Iterable[str] | None = None,
    ) -> None:
        for mint in targets if mints is None else mints:
            for lane, horizon in targets.get(mint, ()):
                self.record(lane, horizon, stage)
            if isinstance(targets, CollectionTargets) and stage in EXPIRY_RPC_STAGES:
                for key in targets.identities.get(mint, ()):
                    # A stream/clock update may already have closed this checkpoint while
                    # the request was in flight. Late telemetry must not resurrect it.
                    if (entry := self._pending.get(key)) is not None:
                        entry[0] = stage

    def expiry_events(self) -> list[dict[str, Any]]:
        """Last known RPC stage, not a claim that this stage caused the expiry."""
        horizons = [60, 300, 600, 900, 1200]
        events = [
            {
                "kind": "collection_expiry",
                "version": 1,
                "at": time.time(),
                "scope": self.scope,
                "since": self.started_at,
                "lane": lane,
                "stages": list(EXPIRY_RPC_STAGES),
                "horizons": horizons,
                "last_rpc": [
                    [
                        self._expiry.get(f"{lane}_{horizon}", {}).get(stage, 0)
                        for stage in EXPIRY_RPC_STAGES
                    ]
                    for horizon in horizons
                ],
            }
            for lane in ("discovery", "policy")
            if any(key.startswith(lane + "_") for key in self._expiry)
        ]
        return [part for event in events for part in _expiry_parts(event)]

    def snapshot(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "since": self.started_at,
            "counts": {key: dict(value) for key, value in self._counts.items()},
        }

    def events(self) -> list[dict[str, Any]]:
        """Two compact events; detail must not enlarge the core interval payload."""
        if not self._counts:
            return []
        stages = sorted(COLLECTION_STAGES)
        horizons = [60, 300, 600, 900, 1200]
        return [
            {
                "kind": "collection",
                "version": 1,
                "at": time.time(),
                "scope": self.scope,
                "since": self.started_at,
                "lane": lane,
                "stages": stages,
                "horizons": horizons,
                "counts": [
                    [self._counts.get(f"{lane}_{horizon}", {}).get(stage, 0) for stage in stages]
                    for horizon in horizons
                ],
            }
            for lane in ("discovery", "policy")
        ]


def rejection_category(reason: str) -> str:
    """Keep exported dimensions finite, without account addresses or provider messages."""
    if reason in {"context_changed_or_market_pressure", "provider_unavailable"}:
        return reason
    if reason in {"route_identity_unavailable", "route_changed_during_request", "curve_migrated"}:
        return "route_identity"
    if reason == "stale_slot_or_timestamp":
        return "slot_or_time"
    if reason in {
        "invalid_fee_tiers",
        "unordered_fee_tiers",
        "missing_fees",
        "invalid_fee_rates",
        "invalid_fee_supply",
    }:
        return "fees"
    if reason in {
        "invalid_real_reserves",
        "no_executable_reserves",
        "pool_sells_disabled",
        "unsupported_negative_virtual_reserves",
    }:
        return "reserves"
    if reason in {"unsupported_venue", "unsupported_quote_mint", "unsupported_token_program"}:
        return "unsupported_route"
    return "account_validation"
