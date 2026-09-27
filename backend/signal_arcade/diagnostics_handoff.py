"""Fixed-size accounting for events inside bounded diagnostic messages."""

from __future__ import annotations

import json
from typing import Any

CATEGORIES = ("training", "proof", "storage", "other")


def event_counts(raw: bytes) -> dict[str, int]:
    counts = dict.fromkeys(CATEGORIES, 0)
    try:
        record = json.loads(raw)
        events = record.get("events", []) if isinstance(record, dict) else []
        if not isinstance(events, list):
            return counts
        for event in events[:8]:
            kind: Any = event.get("kind") if isinstance(event, dict) else None
            category = "training" if kind == "training_error" else kind
            if not isinstance(category, str) or category not in counts:
                category = "other"
            counts[category] += 1
    except (ValueError, TypeError, RecursionError):
        # An unreadable envelope gives no evidence of its event population.
        pass
    return counts


def protected(raw: bytes) -> bool:
    counts = event_counts(raw)
    return bool(counts["training"] or counts["proof"])


def add_counts(target: dict[str, int], counts: dict[str, int]) -> None:
    for category in CATEGORIES:
        target[category] = min(2**53 - 1, target[category] + counts[category])
