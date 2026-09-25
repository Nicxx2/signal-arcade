"""Passive, bounded actual-entry reporting. Never training or qualification evidence."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from pydantic import ValidationError

from ..models import ChallengerEvaluationReceipt, Decision, FillReceipt


def build_execution_activity(
    rows: Sequence[tuple[FillReceipt, FillReceipt | None, Decision | None]],
    *,
    versions: dict[str, str],
    since: datetime | None,
    season_id: str | None,
    profile: str | None,
    configuration: str | None,
    now: datetime,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "state": "available",
        "sample_limit": 30,
        "scope": "recent_fill_sample",
        "unlinked_entries": 0,
        "skills": [],
    }
    if since is None or not season_id or not profile or not configuration:
        report["state"] = "unavailable"
        return report
    selected = []
    seen: set[str] = set()
    for entry, close, decision in rows[:30]:
        if entry.fill_id in seen or not since < entry.filled_at <= now:
            continue
        seen.add(entry.fill_id)
        if decision is None:
            report["unlinked_entries"] += 1
            continue
        if (
            decision.mint != entry.mint
            or decision.action != "enter"
            or decision.season_id != season_id
            or decision.season_profile_fingerprint != profile
            or decision.configuration_fingerprint != configuration
            or not since < decision.created_at <= entry.filled_at
        ):
            continue
        selected.append((entry, close, decision))
    for skill in ("entry", "manipulation"):
        version = versions.get(skill)
        if version is None:
            continue
        counts = dict.fromkeys(("supported_entry", "fallback", "unknown", "later_fallback"), 0)
        outcomes: dict[tuple[str, str, int], dict[str, Any]] = {}
        for entry, close, decision in selected:
            category = "unknown"
            try:
                receipt = ChallengerEvaluationReceipt.model_validate(
                    decision.challenger_assessments.get(skill)
                )
            except (ValidationError, TypeError, ValueError):
                receipt = None
            if (
                receipt is not None
                and receipt.skill == skill
                and receipt.artifact_version == version
                and receipt.evaluated_at == decision.created_at
                and receipt.baseline_actionable
            ):
                applied = receipt.parameters.get("applied")
                if (
                    receipt.in_distribution
                    and applied is True
                    and receipt.proposed_action == "support"
                ):
                    category = "supported_entry"
                elif not receipt.in_distribution and applied is False:
                    category = "fallback"
                    p = receipt.parameters
                    try:
                        origin = datetime.fromisoformat(str(p.get("policy_origin_at", "")))
                        if (
                            p.get("policy_origin_status") == "recorded"
                            and p.get("policy_origin_relation") == "later_attempt"
                            and origin.utcoffset() is not None
                            and origin < decision.created_at
                        ):
                            counts["later_fallback"] += 1
                    except (TypeError, ValueError):
                        pass
            counts[category] += 1
            if category == "unknown":
                continue
            key = (category, entry.account_currency.value, entry.account_decimals)
            group = outcomes.setdefault(
                key,
                {
                    "category": category,
                    "currency": key[1],
                    "decimals": key[2],
                    "closed_count": 0,
                    "unresolved_count": 0,
                    "net_minor": 0,
                    "winning_count": 0,
                },
            )
            if (
                close is None
                or close.side != "sell"
                or close.mint != entry.mint
                or close.position_opened_at != entry.filled_at
                or not entry.filled_at <= close.filled_at <= now
                or close.token_units != entry.token_units
                or close.account_currency != entry.account_currency
                or close.account_decimals != entry.account_decimals
            ):
                group["unresolved_count"] += 1
                continue
            net = close.account_net_minor - entry.account_net_minor
            group["closed_count"] += 1
            group["net_minor"] += net
            group["winning_count"] += int(net > 0)
        report["skills"].append(
            {
                "skill": skill,
                "observed_count": len(selected),
                **counts,
                "outcomes": list(outcomes.values()),
            }
        )
    return report
