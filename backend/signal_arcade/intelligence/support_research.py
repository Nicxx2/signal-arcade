"""Offline Manipulation selectivity research; never imported by the trading service.

python -m signal_arcade.intelligence.support_research SOURCE.sqlite SPEC.json
uses a bounded read-only snapshot. --export writes a new private replay bundle.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal, Self, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..models import LearningEvidenceEpisode, RiskMode
from .activity_dataset import (
    StudyDataset,
    extract_study,
    load_dataset,
    spec_digest,
    validate_dataset,
    write_dataset,
)
from .learning import MODEL_WINDOW_OBSERVATIONS, LearningEngine


class SupportStudy(BaseModel):
    """A fixed hypothesis. It cannot lower native proof or enable any trading rule."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    recipe: Literal["manipulation-sign-shadow-v1"] = "manipulation-sign-shadow-v1"
    frozen_at: datetime
    start: datetime
    end: datetime
    outcome_cutoff: datetime
    risk_mode: RiskMode
    configuration_fingerprint: str = Field(min_length=1)
    baseline_version: str = Field(min_length=1)
    season_id: str = Field(min_length=1)
    season_profile_fingerprint: str = Field(min_length=1)
    active_skill_versions: dict[str, str]
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    validation_rmse: float = Field(ge=0, le=10, allow_inf_nan=False)
    fee_bps: int = Field(ge=0, le=10000)
    network_fee_lamports: int = Field(ge=0)
    venue: str = Field(min_length=1)
    quote_mint: str = Field(min_length=1)
    selected_coverage_percent: Literal[55, 60, 65, 70]
    minimum_opportunities: int = Field(default=200, ge=200)
    minimum_changed: int = Field(default=60, ge=60)

    @model_validator(mode="after")
    def chronological(self) -> Self:
        clocks = (self.frozen_at, self.start, self.end, self.outcome_cutoff)
        if any(t.utcoffset() is None for t in clocks) or not (
            self.frozen_at < self.start < self.end < self.outcome_cutoff
        ):
            raise ValueError("freeze the specification before enrollment")
        if (self.outcome_cutoff - self.end).total_seconds() < 900:
            raise ValueError("allow the final checkpoints to mature")
        if (
            not self.active_skill_versions.get("manipulation")
            or not set(self.active_skill_versions) <= {"entry", "manipulation", "sizing", "exit"}
            or any(not v for v in self.active_skill_versions.values())
        ):
            raise ValueError("freeze the exact active Champion context")
        return self


def interval(values: list[float]) -> dict[str, Any]:
    """Three two-sided comparisons: conservative Bonferroni normal approximation."""
    mean = statistics.fmean(values) if values else None
    margin = 2.40 * statistics.stdev(values) / math.sqrt(len(values)) if len(values) >= 2 else None
    return {
        "n": len(values),
        "mean": mean,
        "lower": mean - margin if mean is not None and margin is not None else None,
        "upper": mean + margin if mean is not None and margin is not None else None,
    }


def _actions(row: LearningEvidenceEpisode, study: SupportStudy) -> tuple[bool, bool] | None:
    """Return incumbent/candidate take decisions from the original frozen receipt only."""
    version = study.active_skill_versions["manipulation"]
    receipt = row.challenger_evaluations.get(version)
    if (
        receipt is None
        or receipt.skill != "manipulation"
        or receipt.artifact_version != version
        or receipt.evaluated_at != row.entry_at
        or not receipt.baseline_actionable
        or receipt.prediction is None
        or not math.isfinite(receipt.prediction)
        or receipt.conservative_value is None
        or not math.isfinite(receipt.conservative_value)
        or not math.isclose(
            receipt.conservative_value,
            receipt.prediction - study.validation_rmse,
            rel_tol=1e-9,
            abs_tol=1e-9,
        )
    ):
        return None
    incumbent = not receipt.in_distribution or receipt.conservative_value > 0
    expected = "support" if receipt.in_distribution and receipt.conservative_value > 0 else "veto"
    if receipt.proposed_action != expected:
        return None
    # Unsupported inputs retain Baseline in both arms. No support boundary is relaxed.
    return incumbent, not receipt.in_distribution or receipt.prediction > 0


def evaluate_support(data: StudyDataset, study: SupportStudy) -> dict[str, Any]:
    rows, issues = validate_dataset(data, study)
    view = cast(
        LearningEngine,
        SimpleNamespace(
            evidence_episodes={r.episode_id: r for r in rows},
            _policy_identities=data.identities,
        ),
    )
    independent = LearningEngine._select_policy_evidence(
        view,
        mode=study.risk_mode,
        configuration_fingerprint=study.configuration_fingerprint,
        baseline_version=study.baseline_version,
    )
    if len(independent) >= MODEL_WINDOW_OBSERVATIONS:
        issues.append("native_selection_cap_may_truncate_study")
    counts: Counter[str] = Counter()
    differences: dict[str, list[float]] = {name: [] for name in ("incumbent", "baseline", "cash")}
    halves: list[list[float]] = [[], []]
    changed_halves = [0, 0]
    returns: dict[str, list[float]] = {name: [] for name in ("candidate", "incumbent", "baseline")}
    changed: list[float] = []
    digest = hashlib.sha256(study.model_dump_json().encode())
    midpoint = study.start + (study.end - study.start) / 2
    for row in independent:
        if (
            row.season_id != study.season_id
            or row.season_profile_fingerprint != study.season_profile_fingerprint
            or row.active_skill_versions != study.active_skill_versions
            or row.fee_bps != study.fee_bps
            or row.venue != study.venue
            or row.quote_mint != study.quote_mint
            or row.checkpoint_network_fee_lamports != study.network_fee_lamports
        ):
            counts["context_excluded"] += 1
            continue
        counts["opportunities"] += 1
        digest.update(row.model_dump_json().encode())
        action = _actions(row, study)
        counts["receipt_known" if action else "receipt_unknown"] += 1
        if action:
            counts["incumbent_entries" if action[0] else "incumbent_vetoes"] += 1
            counts["candidate_entries" if action[1] else "candidate_vetoes"] += 1
            counts["changed"] += int(action[0] != action[1])
        checkpoint = row.checkpoints.get("300")
        if (
            checkpoint is None
            or checkpoint.horizon_seconds != 300
            or checkpoint.observed_at.utcoffset() is None
            or not 300 <= (checkpoint.observed_at - row.entry_at).total_seconds() <= 390
            or checkpoint.observed_at > min(data.as_of, study.outcome_cutoff)
        ):
            counts["pending_or_invalid_checkpoint"] += 1
            continue
        if checkpoint.net_return is None or checkpoint.missing_reason is not None:
            counts[
                "quote_failure"
                if checkpoint.missing_reason == "executable_exit_quote_unavailable"
                else "missing_outcome"
            ] += 1
            continue
        value = checkpoint.net_return
        if not math.isfinite(value):
            counts["missing_outcome"] += 1
            continue
        counts["usable_outcomes"] += 1
        if action is None:
            continue
        incumbent = value if action[0] else 0.0
        candidate = value if action[1] else 0.0
        for name, reference in (("incumbent", incumbent), ("baseline", value), ("cash", 0.0)):
            differences[name].append(candidate - reference)
        for name, result in (
            ("incumbent", incumbent),
            ("baseline", value),
            ("candidate", candidate),
        ):
            returns[name].append(result)
        halves[int(row.entry_at >= midpoint)].append(candidate - incumbent)
        if action[0] != action[1]:
            changed.append(candidate - incumbent)
            changed_halves[int(row.entry_at >= midpoint)] += 1
        counts["winners"] += int(value > 0)
        counts["candidate_missed_winners"] += int(value > 0 and not action[1])
        counts["candidate_admitted_losses"] += int(value < 0 and action[1])
    n = counts["opportunities"]
    availability = counts["receipt_known"] / n if n else 0.0
    coverage = counts["usable_outcomes"] / n if n else 0.0
    paired_coverage = len(differences["incumbent"]) / n if n else 0.0
    winner_veto = (
        counts["candidate_missed_winners"] / counts["winners"] if counts["winners"] else None
    )
    blockers = list(issues)
    for condition, reason in (
        (data.as_of < study.outcome_cutoff, "outcome_period_not_mature"),
        (n < study.minimum_opportunities, "insufficient_opportunities"),
        (len(changed) < study.minimum_changed, "insufficient_changed_usable_outcomes"),
        (availability < 0.90, "insufficient_receipt_availability"),
        (coverage < study.selected_coverage_percent / 100, "insufficient_outcome_coverage"),
        (paired_coverage < study.selected_coverage_percent / 100, "insufficient_paired_coverage"),
        (min(changed_halves) < 30, "insufficient_temporal_support"),
    ):
        if condition:
            blockers.append(reason)
    comparisons = {name: interval(values) for name, values in differences.items()}
    positive = bool(
        not blockers
        and winner_veto is not None
        and winner_veto <= 0.35
        and all(c["lower"] is not None and c["lower"] > 0 for c in comparisons.values())
        and all(statistics.fmean(h) > 0 for h in halves)
    )
    return {
        "recipe": study.recipe,
        "spec_sha256": spec_digest(study),
        "selected_records_sha256": digest.hexdigest(),
        "as_of": data.as_of.isoformat(),
        "counts": dict(counts),
        "changed_usable": len(changed),
        "receipt_availability": availability,
        "outcome_coverage": coverage,
        "paired_coverage": paired_coverage,
        "changed_usable_by_half": changed_halves,
        "candidate_winner_veto_fraction": winner_veto,
        "candidate_minus_reference": comparisons,
        "mean_quoted_returns": {k: statistics.fmean(v) if v else None for k, v in returns.items()},
        "temporal_halves": [interval(h) for h in halves],
        "screen_blockers": blockers,
        "economic_screen_positive": positive,
        "activation_allowed": False,
        "limits": {
            "rows_read": len(rows),
            "parent_bytes": data.parent_bytes,
            "selection_cap": MODEL_WINDOW_OBSERVATIONS,
        },
        "limitations": [
            "Original Policy quotes only, not realized trades or a portfolio/drawdown simulation.",
            "Approximate intervals; dependence and missing outcomes can bias results.",
            "Frozen artifact bytes require separate digest verification against the specification.",
            "No fraud or wallet-ownership labels; positive suspicious outcomes stay positive.",
            "A positive screen does not authorize trading or replace chronological native proof.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("spec", type=Path)
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--export", type=Path)
    operation.add_argument("--from-bundle", action="store_true")
    args = parser.parse_args()
    with args.spec.open("rb") as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ValueError("study specification exceeds byte limit")
    study = SupportStudy.model_validate_json(raw)
    data = (
        load_dataset(args.source, study) if args.from_bundle else extract_study(args.source, study)
    )
    result = evaluate_support(data, study)
    if args.export is not None:
        write_dataset(args.export, data, source=args.source)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
