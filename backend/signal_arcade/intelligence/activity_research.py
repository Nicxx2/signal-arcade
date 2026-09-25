"""Bounded offline screening. No service, database writes or promotion authority.

Read a bounded SQLite period or an exported private dataset: python -m
signal_arcade.intelligence.activity_research SOURCE.sqlite SPEC.json --export PRIVATE.json
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
    MAX_ROWS,
    READ_SECONDS,
    StudyDataset,
    extract_study,
    load_dataset,
    validate_dataset,
    write_dataset,
)
from .activity_evidence import ActivityEvidence, read_activity
from .features import NATIVE_SOL_MINT, WRAPPED_SOL_MINT
from .learning import (
    CHECKPOINT_GRACE_SECONDS,
    MODEL_WINDOW_OBSERVATIONS,
    PRIMARY_HORIZON_SECONDS,
    LearningEngine,
    _policy_identity_key,
)

MAX_STUDY_PARENT_BYTES = 64 * 1024 * 1024


class ActivityStudy(BaseModel):
    """One deliberately fixed exploratory formula, not a search over winning thresholds."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    recipe: Literal["count-value-participation-screen-v1"] = "count-value-participation-screen-v1"
    frozen_at: datetime
    start: datetime
    end: datetime
    outcome_cutoff: datetime
    risk_mode: RiskMode
    configuration_fingerprint: str | None
    baseline_version: str
    season_profile_fingerprint: str | None
    fee_bps: int = Field(ge=0, le=10000)
    network_fee_lamports: int = Field(ge=0)
    venue: str
    quote_mint: str
    selected_coverage_percent: Literal[55, 60, 65, 70]
    # Research minima, not replacements for native proof or independent reference review.
    minimum_opportunities: int = Field(default=200, ge=200)
    minimum_changed: int = Field(default=30, ge=30)

    @model_validator(mode="after")
    def chronological(self) -> Self:
        clocks = (self.frozen_at, self.start, self.end, self.outcome_cutoff)
        if any(t.utcoffset() is None for t in clocks) or not (
            self.frozen_at < self.start < self.end < self.outcome_cutoff
        ):
            raise ValueError("freeze the specification before its observation period")
        if (self.outcome_cutoff - self.end).total_seconds() < 900:
            raise ValueError("allow the final primary checkpoints to mature")
        if self.quote_mint not in {NATIVE_SOL_MINT, WRAPPED_SOL_MINT}:
            raise ValueError("this recipe's amount cutoff is denominated in SOL")
        return self


def proposed_veto(record: ActivityEvidence) -> bool | None:
    """Weak demand hypothesis; never a manipulation label. None means Baseline fallback.

    Count buy share >=70%, value share <=45%, <=3 meaningful trades/minute and <=2
    net-buying wallets in five minutes. Correlated flow fields are not extra confirmations.
    These prespecified research thresholds are not asserted to be optimal or safe to deploy.
    """
    return _screen_activity(record)[0]


def _screen_activity(record: ActivityEvidence) -> tuple[bool | None, str | None]:
    """One first failing input reason per opportunity; the hypothesis is unchanged."""
    required = (
        "buy_ratio_5m",
        "buy_quote_volume_ratio_5m",
        "meaningful_trade_count_1m",
        "net_buy_wallet_count_5m",
        "trade_amount_coverage_5m",
        "known_wallet_trade_coverage",
        "signed_trade_coverage",
        "trade_count_5m",
        "age_seconds",
        "integrity_window_complete",
        "trade_buffer_saturated",
    )
    if record.status == "unavailable":
        return None, "record_unavailable"
    if record.integrity is None:
        return None, "original_integrity_absent"
    values: dict[str, float | int | bool] = {}
    for name in required:
        value, quality, clock, reason = record.metrics[name]
        if value is None or quality != 1 or clock is None or reason is not None:
            return None, "missing_or_low_quality_metric"
        if not 0 <= (record.decision_at - record.clocks[clock]).total_seconds() <= 1:
            return None, "stale_or_future_metric"
        values[name] = value
    if values["integrity_window_complete"] is not True:
        return None, "incomplete_stream_window"
    if values["trade_buffer_saturated"] is not False:
        return None, "saturated_trade_buffer"
    if any(
        values[n] != 1
        for n in (
            "trade_amount_coverage_5m",
            "known_wallet_trade_coverage",
            "signed_trade_coverage",
        )
    ):
        return None, "incomplete_amount_wallet_or_signature_coverage"
    if values["trade_count_5m"] < 24 or values["age_seconds"] < 30:
        return None, "insufficient_observed_activity"
    return bool(
        values["buy_ratio_5m"] >= 0.70
        and values["buy_quote_volume_ratio_5m"] <= 0.45
        and values["meaningful_trade_count_1m"] <= 3
        and values["net_buy_wallet_count_5m"] <= 2
    ), None


def evaluate_activity(
    study: ActivityStudy,
    episodes: list[LearningEvidenceEpisode],
    identities: dict[str, tuple[str, str]],
    companions: dict[str, str],
    *,
    as_of: datetime,
) -> dict[str, Any]:
    if as_of.utcoffset() is None:
        raise ValueError("study read timestamp must be timezone-aware")
    # A data-only view reuses the exact production selector without constructing a learner,
    # opening a writer, fitting, publishing, loading Champions or running governance.
    view = cast(
        LearningEngine,
        SimpleNamespace(
            # Preserve pre-study identities, but never let later traffic displace the fixed
            # study period through the selector's rolling cap. Naive clocks are ineligible.
            evidence_episodes={
                row.episode_id: row
                for row in episodes
                if row.entry_at.utcoffset() is not None
                and row.entry_at < study.end
                and row.entry_at <= as_of
            },
            _policy_identities=identities,
        ),
    )
    independent = LearningEngine._select_policy_evidence(
        view,
        mode=study.risk_mode,
        configuration_fingerprint=study.configuration_fingerprint,
        baseline_version=study.baseline_version,
    )
    selection_at_limit = len(independent) >= MODEL_WINDOW_OBSERVATIONS
    # A full selection whose oldest row precedes the study only drops pre-study rows.
    # A boundary within the study (including tied instants) cannot certify its population.
    study_truncated = bool(selection_at_limit and independent[0].entry_at >= study.start)
    counts: Counter[str] = Counter()
    deltas: list[float] = []
    changed_deltas: list[float] = []
    avoided_losses = missed_winners = 0.0
    digest = hashlib.sha256(study.model_dump_json().encode())
    integrity_states: Counter[str] = Counter()
    recorded_statuses: Counter[str] = Counter()
    unknown_reasons: Counter[str] = Counter()
    recorded_companions = 0
    for parent in independent:
        if not study.start <= parent.entry_at < study.end:
            continue
        if (
            parent.season_profile_fingerprint != study.season_profile_fingerprint
            or parent.fee_bps != study.fee_bps
            or parent.checkpoint_network_fee_lamports != study.network_fee_lamports
            or parent.venue != study.venue
            or parent.quote_mint != study.quote_mint
        ):
            counts["context_excluded"] += 1
            continue
        counts["opportunities"] += 1
        payload = companions.get(parent.episode_id)
        digest.update(
            json.dumps(
                [
                    parent.model_dump(mode="json"),
                    payload,
                    identities.get(_policy_identity_key(parent)),
                ],
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        )
        veto = None
        unknown_reason = None
        try:
            if payload is not None:
                recorded_companions += 1
                evidence = read_activity(payload, parent)
                recorded_statuses[evidence.status] += 1
                veto, unknown_reason = _screen_activity(evidence)
                if evidence.integrity is not None:
                    integrity_states[evidence.integrity.state.value] += 1
            else:
                counts["companion_absent"] += 1
                unknown_reason = "companion_absent"
        except (ValueError, TypeError):
            counts["companion_invalid"] += 1
            unknown_reason = "companion_invalid"
        if unknown_reason is not None:
            unknown_reasons[unknown_reason] += 1
        counts["feature_unknown" if veto is None else "feature_known"] += 1
        counts["changed" if veto is True else "unchanged"] += 1
        checkpoint = parent.checkpoints.get("300")
        if checkpoint is None:
            counts["pending_or_no_checkpoint"] += 1
            continue
        if checkpoint.horizon_seconds != PRIMARY_HORIZON_SECONDS:
            counts["invalid_primary_checkpoint"] += 1
            continue
        if checkpoint.observed_at.utcoffset() is None or not (
            parent.entry_at <= checkpoint.observed_at <= min(as_of, study.outcome_cutoff)
        ):
            counts["outside_outcome_clock"] += 1
            continue
        outcome = checkpoint.net_return
        if outcome is None or not math.isfinite(outcome) or checkpoint.missing_reason is not None:
            counts[
                "quote_failure"
                if checkpoint.missing_reason == "executable_exit_quote_unavailable"
                else "other_missing_outcome"
            ] += 1
            continue
        age = (checkpoint.observed_at - parent.entry_at).total_seconds()
        if not PRIMARY_HORIZON_SECONDS <= age <= PRIMARY_HORIZON_SECONDS + CHECKPOINT_GRACE_SECONDS:
            counts["invalid_primary_checkpoint"] += 1
            continue
        counts["usable_outcomes"] += 1
        counts["positive_outcomes" if outcome > 0 else "nonpositive_outcomes"] += 1
        delta = -outcome if veto is True else 0.0
        deltas.append(delta)
        if veto is True:
            changed_deltas.append(delta)
            counts["changed_usable"] += 1
            if outcome > 0:
                counts["missed_winners"] += 1
                missed_winners += outcome
            elif outcome < 0:
                counts["avoided_losses"] += 1
                avoided_losses -= outcome
    n = counts["opportunities"]
    known = counts["usable_outcomes"]
    mean = statistics.mean(deltas) if deltas else None
    interval = None
    if len(deltas) >= 2:
        margin = 1.96 * statistics.stdev(deltas) / math.sqrt(len(deltas))
        interval = [cast(float, mean) - margin, cast(float, mean) + margin]
    winner_harm = (
        counts["missed_winners"] / counts["positive_outcomes"]
        if counts["positive_outcomes"]
        else None
    )
    sufficient = bool(
        as_of >= study.outcome_cutoff
        and not study_truncated
        and n >= study.minimum_opportunities
        and counts["changed_usable"] >= study.minimum_changed
        and counts["feature_known"] / max(1, n) >= 0.90
        and known / max(1, n) >= study.selected_coverage_percent / 100
    )
    blockers = [
        name
        for condition, name in (
            (as_of < study.outcome_cutoff, "outcome_period_not_mature"),
            (study_truncated, "native_selection_cap_may_truncate_study"),
            (n < study.minimum_opportunities, "insufficient_independent_opportunities"),
            (
                counts["changed_usable"] < study.minimum_changed,
                "insufficient_changed_usable_outcomes",
            ),
            (counts["feature_known"] / max(1, n) < 0.90, "insufficient_feature_availability"),
            (
                known / max(1, n) < study.selected_coverage_percent / 100,
                "insufficient_outcome_coverage",
            ),
        )
        if condition
    ]
    return {
        "recipe": study.recipe,
        "spec_sha256": hashlib.sha256(study.model_dump_json().encode()).hexdigest(),
        "dataset_sha256": digest.hexdigest(),
        "selection_at_limit": selection_at_limit,
        "study_selection_may_be_truncated": study_truncated,
        "retention_completeness": "not_certified",
        "as_of": as_of.isoformat(),
        "counts": dict(counts),
        "recorded_companions": recorded_companions,
        "valid_companion_statuses": dict(recorded_statuses),
        "feature_unknown_reasons": dict(unknown_reasons),
        "screen_blockers": blockers,
        "pattern_observed": counts["changed"] > 0,
        "feature_availability": counts["feature_known"] / n if n else None,
        "outcome_coverage": known / n if n else None,
        "changed_fraction": counts["changed"] / n if n else None,
        "paired_mean_300s_return_delta": mean,
        "paired_normal_approximation_95_interval": interval,
        "changed_subset_mean_delta": statistics.mean(changed_deltas) if changed_deltas else None,
        "avoided_loss_return_sum": avoided_losses,
        "missed_winner_return_sum": missed_winners,
        "winner_veto_fraction": winner_harm,
        "original_integrity_states": dict(integrity_states),
        "sufficient_for_economic_screen": sufficient,
        "economic_screen_positive": bool(
            sufficient
            and interval
            and interval[0] > 0
            and winner_harm is not None
            and winner_harm <= 0.35
        ),
        "activation_allowed": False,
        "limitations": [
            "Research only. No independent manipulation truth labels or detection accuracy.",
            "300-second fee-inclusive counterfactuals; no adaptive exits or portfolio drawdown.",
            "Unknown features keep Baseline action; missing outcomes stay in opportunity counts.",
            "Interval uses available outcomes only; missingness and market dependence can bias it.",
            "Policy selection is capped at 1,000; pruned history cannot be rebuilt.",
        ],
    }


def evaluate_dataset(data: StudyDataset, study: ActivityStudy) -> dict[str, Any]:
    rows, issues = validate_dataset(data, study)
    result = evaluate_activity(study, rows, data.identities, data.companions, as_of=data.as_of)
    result["dataset_completeness_issues"] = issues
    result["retention_completeness"] = (
        "possible_gap" if issues else "no_recorded_overlap_not_a_population_census"
    )
    if issues:
        result["sufficient_for_economic_screen"] = False
        result["economic_screen_positive"] = False
        result["screen_blockers"].extend(issues)
    result["read_limits"] = {
        "max_policy_rows": MAX_ROWS,
        "max_parent_bytes": MAX_STUDY_PARENT_BYTES,
        "cooperative_sql_seconds": READ_SECONDS,
        "rows_read": len(rows),
        "metadata_rows_read": data.metadata_rows_read,
        "parent_bytes": data.parent_bytes,
    }
    result["snapshot_scope"] = "declared_period_with_persistent_first_policy_identities"
    result["retention_watermark_recorded"] = data.pruned_through is not None
    result["limitations"].append(
        "Indexed scope assumes original ISO timestamps and original enrollment clocks. "
        "It cannot recover manual deletions, unrecorded pruning or corrupt out-of-range metadata."
    )
    return result


def read_study(path: Path, study: ActivityStudy) -> dict[str, Any]:
    data = extract_study(path, study, max_parent_bytes=MAX_STUDY_PARENT_BYTES)
    return evaluate_dataset(data, study)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("spec", type=Path)
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument(
        "--export", type=Path, help="new private dataset path; never overwritten"
    )
    operation.add_argument("--from-bundle", action="store_true", help="read an exported dataset")
    args = parser.parse_args()
    study = ActivityStudy.model_validate_json(args.spec.read_text(encoding="utf-8"))
    if args.from_bundle:
        data = load_dataset(args.source, study)
    else:
        data = extract_study(args.source, study)
        validate_dataset(data, study)
        if args.export is not None:
            write_dataset(args.export, data, source=args.source)
    print(json.dumps(evaluate_dataset(data, study), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
