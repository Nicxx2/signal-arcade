"""Finite optional report identities; scopes never grow the cadence map."""

from typing import Any

from .diagnostics_store import MAX_EVENT_PAYLOAD, encode
from .runtime_evidence import SLOW_FIELDS

HORIZONS = (60, 300, 600, 900, 1200)
HORIZON_PARTS = frozenset(
    HORIZONS[start:end] for start in range(len(HORIZONS)) for end in range(start + 1, 6)
)
OPTIONAL_LANES = {
    "collection": ("discovery", "policy"),
    "collection_expiry": ("discovery", "policy"),
    "collection_selection": ("discovery", "policy"),
    "reserve_validation": ("",),
    "reserve_layout": ("",),
    "diagnostic_loss": ("",),
    "heartbeat_work": ("",),
    "runtime_work": ("", "guards", "snapshot", "rpc"),
    "work_detail": ("persist", "broker", "equity", "decision", "rpc", "candidate", "governance"),
    "collector_work": ("", "writer"),
    "slow_work": tuple(SLOW_FIELDS),
    "provider_health": ("http", "ws"),
    "retention_sample": ("",),
}
CUMULATIVE_REPORTS = frozenset(
    {
        "collection",
        "collection_expiry",
        "diagnostic_loss",
        "heartbeat_work",
        "runtime_work",
        "work_detail",
        "collector_work",
        "provider_health",
        # Like counters, a queued storage snapshot is replaced by its latest sample.
        "retention_sample",
    }
)


def runtime_work_parts(event: dict[str, Any]) -> list[dict[str, Any]]:
    """Split unusually large counters into finite streams without raising byte limits.

    Normal reports retain their existing shape. Parts share scope/time; counters appear
    once, and optional admission/cadence tracks each lane independently under pressure.
    """
    try:
        encode(event, max_payload=MAX_EVENT_PAYLOAD)
        return [event]
    except ValueError:
        if any(not name.startswith(("snapshot_", "rpc_")) for name in event["seconds_since_boot"]):
            # An unrecognized future field must remain an honest recorder error, not vanish.
            return [event]
        common = {key: event[key] for key in ("kind", "version", "at", "scope")}
        guards = {
            key: value
            for key, value in event.items()
            if key not in common and key != "seconds_since_boot"
        }
        result = [{**common, **guards, "lane": "guards", "seconds_since_boot": {}}]
        for lane in ("snapshot", "rpc"):
            timing = {
                name: values
                for name, values in event["seconds_since_boot"].items()
                if name.startswith(lane + "_")
            }
            if timing:
                result.append({**common, "lane": lane, "seconds_since_boot": timing})
        return result


def optional_key(event: dict[str, Any]) -> tuple[str, str, tuple[int, ...]] | None:
    kind, lane = event.get("kind"), event.get("lane", "")
    if not isinstance(kind, str) or kind not in OPTIONAL_LANES:
        return None
    if not isinstance(lane, str) or lane not in OPTIONAL_LANES[kind]:
        return None
    scope = event.get("scope")
    if not isinstance(scope, str) or not scope or len(scope) > 64:
        return None
    if kind == "slow_work":
        elapsed = event.get("elapsed")
        # Replacement compares these values before JSON encoding. Enforce the same
        # finite range as RuntimeEvidence, including for generic queued events.
        if (
            isinstance(elapsed, bool)
            or not isinstance(elapsed, (int, float))
            or not 0 <= elapsed <= 1e12
        ):
            return None
    horizons = event.get("horizons", [])
    if (
        not isinstance(horizons, (list, tuple))
        or len(horizons) > 5
        or any(type(h) is not int for h in horizons)
    ):
        return None
    part = tuple(horizons)
    if kind.startswith("collection"):
        allowed = HORIZON_PARTS if kind == "collection_expiry" else {HORIZONS}
        if part not in allowed:
            return None
    elif part:
        return None
    return kind, lane, part
