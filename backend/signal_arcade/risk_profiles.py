from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import RISK_LIMITS, RiskMode
from .strategy import (
    BASELINE_VERSION,
    INTEGRITY_POLICY_VERSION,
    LEGACY_BASELINE_VERSION,
    LEGACY_INTEGRITY_POLICY_VERSION,
    LEGACY_SIZING_POLICY_VERSION,
    SIZING_POLICY_VERSION,
)

SEASON_PROFILE_SCHEMA_VERSION = 1


class DrawdownPolicyKind(StrEnum):
    DEFAULT = "default"
    CUSTOM = "custom"
    DISABLED = "disabled"


class DrawdownPolicy(BaseModel):
    """Typed portfolio drawdown policy; disabled is never represented as a magic number."""

    model_config = ConfigDict(extra="forbid")

    kind: DrawdownPolicyKind = DrawdownPolicyKind.DEFAULT
    custom_threshold_bps: int | None = Field(default=None, ge=100, le=9_900)

    @model_validator(mode="after")
    def validate_kind(self) -> DrawdownPolicy:
        if self.kind == DrawdownPolicyKind.CUSTOM and self.custom_threshold_bps is None:
            raise ValueError("custom drawdown policy requires a threshold")
        if self.kind != DrawdownPolicyKind.CUSTOM and self.custom_threshold_bps is not None:
            raise ValueError("only a custom drawdown policy accepts a threshold")
        return self


class SeasonProfile(BaseModel):
    """Immutable, canonical policy provenance for one paper season."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = SEASON_PROFILE_SCHEMA_VERSION
    provenance: Literal["exact"] = "exact"
    risk_mode: RiskMode
    risk_policy_version: str = "risk-limits-v1"
    # Missing values identify exact profiles created before strategy provenance existed. They
    # deliberately remain on the frozen v1.1 path until a clean successor season starts.
    baseline_version: str = LEGACY_BASELINE_VERSION
    integrity_policy_version: str = LEGACY_INTEGRITY_POLICY_VERSION
    sizing_policy_version: str = LEGACY_SIZING_POLICY_VERSION
    risk_limits: dict[str, int | float | str]
    drawdown_policy: DrawdownPolicy
    effective_drawdown_bps: int | None = Field(default=None, ge=100, le=9_900)
    profile_fingerprint: str = Field(min_length=16, max_length=64)
    learning_fingerprint: str | None = Field(default=None, min_length=8, max_length=128)
    locked_at: datetime | None = None


def resolved_drawdown_bps(mode: RiskMode, policy: DrawdownPolicy) -> int | None:
    if policy.kind == DrawdownPolicyKind.DISABLED:
        return None
    if policy.kind == DrawdownPolicyKind.CUSTOM:
        assert policy.custom_threshold_bps is not None
        return policy.custom_threshold_bps
    return round(RISK_LIMITS[mode].max_drawdown_fraction * 10_000)


def canonical_drawdown_policy(mode: RiskMode, policy: DrawdownPolicy) -> DrawdownPolicy:
    """Collapse a custom value equal to the personality default into one canonical profile."""

    if policy.kind == DrawdownPolicyKind.CUSTOM and policy.custom_threshold_bps == round(
        RISK_LIMITS[mode].max_drawdown_fraction * 10_000
    ):
        return DrawdownPolicy()
    return policy


def build_season_profile(
    mode: RiskMode,
    *,
    drawdown_policy: DrawdownPolicy | None = None,
    learning_fingerprint: str | None = None,
    locked_at: datetime | None = None,
) -> SeasonProfile:
    policy = canonical_drawdown_policy(mode, drawdown_policy or DrawdownPolicy())
    limits = RISK_LIMITS[mode].model_dump(mode="json")
    effective_bps = resolved_drawdown_bps(mode, policy)
    fingerprint_payload: dict[str, Any] = {
        "schema_version": SEASON_PROFILE_SCHEMA_VERSION,
        "risk_policy_version": "risk-limits-v1",
        "baseline_version": BASELINE_VERSION,
        "integrity_policy_version": INTEGRITY_POLICY_VERSION,
        "sizing_policy_version": SIZING_POLICY_VERSION,
        "risk_mode": mode.value,
        "risk_limits": limits,
        "drawdown_policy": {
            "kind": policy.kind.value,
            "effective_drawdown_bps": effective_bps,
        },
    }
    encoded = json.dumps(
        fingerprint_payload,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    fingerprint = hashlib.sha256(encoded).hexdigest()
    return SeasonProfile(
        risk_mode=mode,
        baseline_version=BASELINE_VERSION,
        integrity_policy_version=INTEGRITY_POLICY_VERSION,
        sizing_policy_version=SIZING_POLICY_VERSION,
        risk_limits=limits,
        drawdown_policy=policy,
        effective_drawdown_bps=effective_bps,
        profile_fingerprint=fingerprint,
        learning_fingerprint=learning_fingerprint,
        locked_at=locked_at,
    )


def upgrade_season_profile_strategy(
    profile: dict[str, Any],
    *,
    locked_at: datetime | None = None,
) -> SeasonProfile:
    """Create the current strategy successor without mutating the stored source profile."""

    parsed = SeasonProfile.model_validate(profile)
    learning_fingerprint = (
        parsed.learning_fingerprint if parsed.baseline_version == BASELINE_VERSION else None
    )
    return build_season_profile(
        parsed.risk_mode,
        drawdown_policy=parsed.drawdown_policy,
        learning_fingerprint=learning_fingerprint,
        locked_at=locked_at,
    )


def season_profile_catalog() -> list[dict[str, Any]]:
    """Expose the backend's real limits so web clients never maintain a divergent copy."""

    return [
        build_season_profile(mode).model_dump(mode="json")
        for mode in (RiskMode.SAFE, RiskMode.BALANCED, RiskMode.AGGRESSIVE)
    ]
