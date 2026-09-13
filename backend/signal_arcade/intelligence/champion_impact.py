"""Bounded spectator comparisons. Never an input to trading or qualification."""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import datetime, timedelta
from statistics import fmean, stdev
from typing import Any

from ..models import ChallengerEvaluationReceipt, LearningEvidenceEpisode

SKILLS = ("entry", "manipulation", "sizing", "exit")
HORIZONS = (60, 300, 600, 900, 1200)
WINDOW = 60
MINIMUM_PAIRS = 30
MINIMUM_COVERAGE = 0.70


def _finite(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def _receipt(
    row: LearningEvidenceEpisode, skill: str, versions: dict[str, str]
) -> ChallengerEvaluationReceipt | None:
    version = versions.get(skill)
    receipt = row.challenger_evaluations.get(version or "")
    if (
        receipt is None
        or receipt.artifact_version != version
        or receipt.skill != skill
        or receipt.evaluated_at != row.created_at
        or not receipt.baseline_actionable
    ):
        return None
    return receipt


def _multiplier(receipt: ChallengerEvaluationReceipt | None) -> float | None:
    if receipt is None:
        return None
    if not receipt.in_distribution:
        return 1.0
    value = receipt.parameters.get("bounded_multiplier")
    if (
        receipt.parameters.get("bounds_policy") != "sizing-authority-v1"
        or not _finite(value)
        or value not in (0.5, 1.0, 1.5, 2.0)
    ):
        return None
    return float(value)


def _return(row: LearningEvidenceEpisode, horizon: int, now: datetime) -> float | None:
    point = row.checkpoints.get(str(horizon))
    if (
        point is None
        or point.horizon_seconds != horizon
        or not row.entry_at + timedelta(seconds=horizon) <= point.observed_at <= now
        or point.missing_reason is not None
        or not _finite(point.net_return)
    ):
        return None
    return point.net_return


def _size(
    row: LearningEvidenceEpisode, multiplier: float, horizon: int, now: datetime
) -> float | None:
    trial = row.size_trials.get(format(multiplier, "g"))
    baseline = row.size_trials.get("1")
    if (
        trial is None
        or baseline is None
        or not trial.eligible_at_entry
        or not baseline.eligible_at_entry
        or not trial.entry_cost_lamports
        or not baseline.entry_cost_lamports
        or trial.entry_cost_lamports <= 0
        or baseline.entry_cost_lamports <= 0
        or trial.multiplier != multiplier
        or baseline.multiplier != 1.0
        or trial.entry_missing_reason is not None
        or baseline.entry_missing_reason is not None
    ):
        return None
    point = trial.checkpoints.get(str(horizon))
    if (
        point is None
        or point.horizon_seconds != horizon
        or point.exit_value_lamports is None
        or point.missing_reason is not None
        or not row.entry_at + timedelta(seconds=horizon) <= point.observed_at <= now
    ):
        return None
    return (point.exit_value_lamports - trial.entry_cost_lamports) / baseline.entry_cost_lamports


def _values(
    row: LearningEvidenceEpisode,
    subject: str,
    versions: dict[str, str],
    normal_hold: int,
    now: datetime,
) -> tuple[float | None, float | None, set[int], bool]:
    """Return reference, supported, required horizons, and whether this role was reached."""
    horizon = normal_hold if subject in ("team", "exit") else 300
    required = {horizon}
    baseline = _return(row, horizon, now)
    for skill in ("entry", "manipulation"):
        if skill not in versions:
            continue
        receipt = _receipt(row, skill, versions)
        if receipt is None or receipt.proposed_action not in ("support", "veto"):
            return None, None, required, True
        veto = receipt.in_distribution and receipt.proposed_action == "veto"
        if subject == skill:
            return baseline, 0.0 if veto else baseline, required, True
        if veto:
            # A team veto counts once. Downstream skills did not get to change this case.
            return (
                (baseline, 0.0, required, True)
                if subject == "team"
                else (None, None, required, False)
            )
    multiplier = 1.0
    if "sizing" in versions:
        selected = _multiplier(_receipt(row, "sizing", versions))
        if selected is None:
            return None, None, required, True
        multiplier = selected
    if subject == "sizing":
        return _size(row, 1.0, 300, now), _size(row, multiplier, 300, now), required, True
    if subject in ("team", "exit") and "exit" in versions:
        receipt = _receipt(row, "exit", versions)
        if receipt is None:
            required.update(h for h in HORIZONS if h <= normal_hold)
            return None, None, required, True
        try:
            horizon = int(receipt.proposed_action) if receipt.in_distribution else normal_hold
        except (TypeError, ValueError):
            return None, None, required, True
        if horizon not in HORIZONS or horizon > normal_hold:
            return None, None, required, True
        required.add(horizon)
    if "sizing" in versions:
        reference_size = multiplier if subject == "exit" else 1.0
        return (
            _size(row, reference_size, normal_hold, now),
            _size(row, multiplier, horizon, now),
            required,
            True,
        )
    return baseline, _return(row, horizon, now), required, True


def _summary(
    rows: Sequence[LearningEvidenceEpisode],
    subject: str,
    versions: dict[str, str],
    normal_hold: int,
    now: datetime,
) -> dict[str, Any]:
    resolved: list[tuple[LearningEvidenceEpisode, float | None, float | None]] = []
    pending = not_reached = 0
    # Select by chronology before checking usability; missing pairs must not disappear.
    for row in reversed(rows):
        try:
            reference, supported, horizons, reached = _values(
                row, subject, versions, normal_hold, now
            )
        except (TypeError, ValueError, OverflowError):
            # Incomplete legacy receipts are unavailable pairs, never a broken dashboard.
            reference, supported, reached = None, None, True
            horizons = {h for h in HORIZONS if h <= normal_hold}
        if not reached:
            not_reached += 1
            continue
        if row.status == "pending" and not all(str(h) in row.checkpoints for h in horizons):
            pending += 1
            continue
        resolved.append((row, reference, supported))
        if len(resolved) == WINDOW:
            break
    pairs = [
        (a, b)
        for _, a, b in resolved
        if a is not None and b is not None and _finite(a) and _finite(b)
    ]
    deltas = [b - a for a, b in pairs]
    mean = fmean(deltas) if deltas else None
    margin = 1.96 * stdev(deltas) / math.sqrt(len(deltas)) if len(deltas) >= 2 else None
    lower = mean - margin if mean is not None and margin is not None else None
    upper = mean + margin if mean is not None and margin is not None else None
    coverage = len(pairs) / len(resolved) if resolved else 0.0
    enough = len(pairs) >= MINIMUM_PAIRS and coverage >= MINIMUM_COVERAGE
    state = (
        "collecting"
        if not enough
        else "positive"
        if lower is not None and lower > 0
        else "negative"
        if upper is not None and upper < 0
        else "uncertain"
    )
    return {
        "subject": subject,
        "state": state,
        "observed_count": len(resolved),
        "usable_count": len(pairs),
        "pending_count": pending,
        "not_reached_count": not_reached,
        "coverage": coverage,
        "mean_advantage": mean,
        "lower_bound": lower,
        "upper_bound": upper,
        "reference_mean": fmean(a for a, _ in pairs) if pairs else None,
        "supported_mean": fmean(b for _, b in pairs) if pairs else None,
        "from": resolved[-1][0].created_at.isoformat() if resolved else None,
        "to": resolved[0][0].created_at.isoformat() if resolved else None,
        "reference_horizon_seconds": normal_hold if subject in ("exit", "team") else 300,
    }


def build_impact(
    rows: Sequence[LearningEvidenceEpisode],
    *,
    versions: dict[str, str],
    since: datetime | None,
    season_id: str | None,
    profile: str | None,
    normal_hold: int,
    now: datetime,
) -> dict[str, Any]:
    """Input is the engine's existing independent Policy population, capped at 1,000 rows."""
    report: dict[str, Any] = {
        "schema_version": 1,
        "as_of": now.isoformat(),
        "season_id": season_id,
        "profile_fingerprint": profile,
        "versions": dict(versions),
        "since": since.isoformat() if since else None,
        "window_size": WINDOW,
        "minimum_pairs": MINIMUM_PAIRS,
        "minimum_coverage": MINIMUM_COVERAGE,
        "state": "unavailable",
        "comparisons": [],
    }
    if not versions or not set(versions).issubset(SKILLS):
        return report
    if not since or not season_id or not profile or normal_hold not in HORIZONS:
        return report
    selected = []
    for row in rows[-1000:]:
        if (
            row.lane != "policy"
            or not row.qualification_eligible
            or row.synthetic
            or row.source_mode != "solana_mainnet"
            or row.season_id != season_id
            or row.season_profile_fingerprint != profile
            or row.active_skill_versions != versions
            or row.baseline_action != "enter"
            or not row.baseline_actionable
            or row.created_at.utcoffset() is None
            or not since < row.created_at <= now
        ):
            continue
        selected.append(row)
    selected.sort(key=lambda row: (row.created_at, row.episode_id))
    independent: dict[str, LearningEvidenceEpisode] = {}
    for row in selected:
        independent.setdefault(row.mint, row)
    selected = list(independent.values())
    subjects = [s for s in SKILLS if s in versions]
    if len(subjects) > 1:
        subjects = ["team", *subjects]
    report["state"] = "available"
    report["comparisons"] = [_summary(selected, s, versions, normal_hold, now) for s in subjects]
    return report
