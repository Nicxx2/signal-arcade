"""Versioned coverage requirements, separate from market and training population identity."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..models import ChallengerSkillArtifact, LearningModel
from . import exit_context

PERCENTAGES = (70, 65, 60, 55)
POLICY_VERSION = "skill-coverage-v1"
SETTING_KEY = "skill_coverage_policy"
POLICY_KEYS = frozenset(
    {
        "coverage_policy_version",
        "coverage_minimum_percent",
        "coverage_revision",
        "coverage_effective_at",
    }
)


@dataclass(frozen=True)
class CoveragePolicy:
    percent: int = 70
    revision: int = 0
    effective_at: datetime | None = None

    @property
    def fraction(self) -> float:
        return self.percent / 100

    def record(self) -> dict[str, Any]:
        return {
            "coverage_policy_version": POLICY_VERSION,
            "coverage_minimum_percent": self.percent,
            "coverage_revision": self.revision,
            "coverage_effective_at": self.effective_at.isoformat() if self.effective_at else None,
        }

    def metadata(self) -> dict[str, Any]:
        # Preserve byte-for-byte legacy parameters until the user actually changes the policy.
        return self.record() if self.revision else {}

    def fresh(self, validation_start: datetime | None) -> bool:
        return self.effective_at is None or bool(
            validation_start is not None
            and validation_start.utcoffset() is not None
            and validation_start >= self.effective_at
        )


def read_policy(record: Mapping[str, Any]) -> CoveragePolicy:
    present = POLICY_KEYS.intersection(record)
    if not present:
        return CoveragePolicy()
    if present != POLICY_KEYS or record.get("coverage_policy_version") != POLICY_VERSION:
        raise ValueError("incomplete or unsupported coverage policy")
    percent, revision = record["coverage_minimum_percent"], record["coverage_revision"]
    if type(percent) is not int or percent not in PERCENTAGES:
        raise ValueError("coverage must be 70, 65, 60 or 55 percent")
    if type(revision) is not int or revision < 0:
        raise ValueError("invalid coverage policy revision")
    raw_at = record["coverage_effective_at"]
    if revision == 0:
        if percent != 70 or raw_at is not None:
            raise ValueError("invalid legacy coverage policy")
        return CoveragePolicy()
    if not isinstance(raw_at, str):
        raise ValueError("coverage policy time is missing")
    at = datetime.fromisoformat(raw_at)
    if at.utcoffset() is None:
        raise ValueError("coverage policy time must include its timezone")
    return CoveragePolicy(percent, revision, at)


def saved_minimum(record: Mapping[str, Any]) -> float:
    try:
        return read_policy(record).fraction
    except (ValueError, TypeError, OverflowError):
        return math.inf  # Unreadable proof never grants authority.


def is_coach(artifact: ChallengerSkillArtifact) -> bool:
    return artifact.schema_version == "challenger-skill-coach-v1"


def artifact_minimum(artifact: ChallengerSkillArtifact | LearningModel) -> float:
    if isinstance(artifact, ChallengerSkillArtifact) and is_coach(artifact):
        return 0.70
    return saved_minimum(artifact.hyperparameters)


def validation_current(artifact: ChallengerSkillArtifact | LearningModel) -> bool:
    """Legacy proof keeps its contract; versioned proof must carry its validation boundary."""
    if isinstance(artifact, ChallengerSkillArtifact) and is_coach(artifact):
        return True
    if not POLICY_KEYS.intersection(artifact.hyperparameters):
        return True
    try:
        policy = read_policy(artifact.hyperparameters)
    except (ValueError, TypeError, OverflowError):
        return False
    return artifact.hyperparameters.get("coverage_fresh_validation") is True and policy.fresh(
        artifact.training_cutoff_at
    )


def meets_current(artifact: ChallengerSkillArtifact | LearningModel, minimum: float) -> bool:
    """Historical qualification stays immutable; a stricter current policy is a separate gate."""
    saved = artifact_minimum(artifact)
    if not math.isfinite(saved):
        return False
    if minimum <= saved:
        return True
    values: list[float | int | None]
    if isinstance(artifact, LearningModel):
        values = [
            artifact.outcome_availability_fraction,
            artifact.policy_outcome_availability_fraction,
        ]
    else:
        names = {
            "entry": ("outcome_availability", "policy_outcome_availability"),
            "manipulation": ("outcome_availability", "policy_outcome_availability"),
            "sizing": ("outcome_availability",),
            "exit": ("validation_availability_fraction",),
        }[artifact.skill.value]
        if artifact.skill == "exit" and (
            exit_context.is_contextual(artifact)
            or "reference_availability_fraction" in artifact.metrics
        ):
            names += ("reference_availability_fraction",)
        values = [artifact.metrics.get(name) for name in names]
    return all(
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(value)
        and minimum <= value <= 1
        for value in values
    )
