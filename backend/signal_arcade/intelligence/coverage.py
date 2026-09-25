"""Optional, generation-bound explanations of the unchanged fitted coverage fraction."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from ..models import LearningObservation

# Schema 1 describes the primary Discovery cohort only. Never infer recoverability from
# a missing reason, and never use these reporting counts to select rows or grant authority.
COVERAGE_BUCKETS = (
    "usable",
    "quote_liquidity",
    "quote_fees",
    "quote_other",
    "stale_route",
    "window_elapsed",
    "other_missing",
)
QUOTE_BUCKETS = {
    "sell output exceeds real quote reserves": "quote_liquidity",
    "fees exceed sell proceeds": "quote_fees",
}


def freeze_quote_failures(observations: Sequence[LearningObservation]) -> dict[str, str]:
    """Keep only bounded classifications; bulky route receipts stay out of the fit copy."""
    result = {}
    for item in observations:
        checkpoint = item.checkpoints.get("300")
        if (
            checkpoint is not None
            and checkpoint.net_return is None
            and (checkpoint.missing_reason == "executable_exit_quote_unavailable")
        ):
            reason = (checkpoint.route_snapshot or {}).get("quote_failure_reason")
            result[item.observation_id] = QUOTE_BUCKETS.get(
                reason if isinstance(reason, str) else "", "quote_other"
            )
    return result


def fitted_coverage_metrics(
    resolved: Sequence[LearningObservation],
    quote_failures: Mapping[str, str] | None = None,
) -> dict[str, int]:
    """Count the exact resolved population already selected by the fitting contract."""
    quotes = freeze_quote_failures(resolved) if quote_failures is None else quote_failures
    counts = dict.fromkeys(COVERAGE_BUCKETS, 0)
    for item in resolved:
        checkpoint = item.checkpoints.get("300")
        if checkpoint is not None and checkpoint.net_return is not None:
            bucket = "usable"  # Includes zero, losses and chronologically embargoed rows.
        elif checkpoint is None:
            bucket = "other_missing"
        elif checkpoint.missing_reason == "executable_exit_quote_unavailable":
            bucket = quotes.get(item.observation_id, "quote_other")
            if bucket not in QUOTE_BUCKETS.values():
                bucket = "quote_other"
        else:
            bucket = {
                "stale_cached_route": "stale_route",
                "checkpoint_window_elapsed": "window_elapsed",
            }.get(checkpoint.missing_reason or "", "other_missing")
        counts[bucket] += 1
    return {
        "coverage_schema": 1,
        "coverage_resolved": len(resolved),
        **{f"coverage_{key}": value for key, value in counts.items()},
    }


def coverage_breakdown(metrics: Mapping[str, Any], sample_count: int) -> dict[str, int] | None:
    """Unknown, partial or contradictory historical metadata must not look like evidence."""
    keys = ("schema", "resolved", *COVERAGE_BUCKETS)
    values: dict[str, int] = {}
    for key in keys:
        value = metrics.get(f"coverage_{key}")
        if not isinstance(value, int) or isinstance(value, bool) or value < 0 or value > 1000:
            return None
        values[key] = value
    if values["schema"] != 1 or not values["resolved"]:
        return None
    if sum(values[key] for key in COVERAGE_BUCKETS) != values["resolved"]:
        return None
    fraction = metrics.get("outcome_availability")
    if (
        values["usable"] != sample_count
        or not isinstance(fraction, int | float)
        or isinstance(fraction, bool)
        or not math.isfinite(fraction)
        or not math.isclose(values["usable"] / values["resolved"], fraction, abs_tol=1e-9)
    ):
        return None
    return values
