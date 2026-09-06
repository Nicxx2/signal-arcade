"""Shared persistence/runtime contract for confirmed paper inventory write-offs."""

from datetime import datetime
from typing import Any

TERMINAL_PROBE_POLICY = "validated-route-probes-v2"
TERMINAL_PROBE_MAX_AGE_SECONDS = 180


def valid_terminal_probe(evidence: Any, now: datetime) -> bool:
    if not isinstance(evidence, dict):
        return False
    probe = evidence.get("probe")
    if not isinstance(probe, dict):
        return False
    try:
        first = datetime.fromisoformat(str(probe["first_observed_at"]))
        last = datetime.fromisoformat(str(probe["observed_at"]))
        first_slot, last_slot = int(probe["first_slot"]), int(probe["slot"])
        return bool(
            evidence.get("policy") == TERMINAL_PROBE_POLICY
            and evidence.get("global_market_healthy") is True
            and probe.get("verified") is True
            and probe.get("outcome") == "unavailable"
            and int(probe["consecutive"]) >= 2
            and 0 < first_slot < last_slot
            and (last - first).total_seconds() > 0
            and (now - last).total_seconds() >= 0
            and (now - first).total_seconds() <= TERMINAL_PROBE_MAX_AGE_SECONDS
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        return False
