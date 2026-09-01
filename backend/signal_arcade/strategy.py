"""Versioned deterministic policy provenance shared across paper subsystems."""

from __future__ import annotations

LEGACY_BASELINE_VERSION = "baseline-v1.1"
PREVIOUS_BASELINE_VERSION = "baseline-v1.2"
RECENT_BASELINE_VERSION = "baseline-v1.3"
CORROBORATED_BASELINE_VERSION = "baseline-v1.4"
BASELINE_VERSION = "baseline-v1.5"
LEGACY_INTEGRITY_POLICY_VERSION = "integrity-observation-v1"
PREVIOUS_INTEGRITY_POLICY_VERSION = "integrity-gates-v1"
RECENT_INTEGRITY_POLICY_VERSION = "integrity-gates-v2"
INTEGRITY_POLICY_VERSION = "integrity-gates-v3"
LEGACY_SIZING_POLICY_VERSION = "fixed-size-v1"
SIZING_POLICY_VERSION = "quality-size-v1"

# Baseline v1.4+ treats a strong but isolated manipulation signal as unresolved rather than
# silently accepting a full-size entry.  The assessment still needs corroboration before it may
# call a market suspicious; this threshold only decides whether the deterministic trader should
# wait for that ambiguity to resolve.  Moderate uncertainty remains observable at a bounded size.
UNCERTAIN_INTEGRITY_HOLD_SCORE = 0.80
UNCERTAIN_INTEGRITY_SIZE_MULTIPLIER = 0.70

SUPPORTED_BASELINE_VERSIONS = frozenset(
    {
        LEGACY_BASELINE_VERSION,
        PREVIOUS_BASELINE_VERSION,
        RECENT_BASELINE_VERSION,
        CORROBORATED_BASELINE_VERSION,
        BASELINE_VERSION,
    }
)
LEARNABLE_BASELINE_VERSIONS = frozenset(
    {
        PREVIOUS_BASELINE_VERSION,
        RECENT_BASELINE_VERSION,
        CORROBORATED_BASELINE_VERSION,
        BASELINE_VERSION,
    }
)


def integrity_policy_for_baseline(baseline_version: str) -> str:
    """Return the frozen integrity policy paired with a supported Baseline generation."""

    if baseline_version == LEGACY_BASELINE_VERSION:
        return LEGACY_INTEGRITY_POLICY_VERSION
    if baseline_version == PREVIOUS_BASELINE_VERSION:
        return PREVIOUS_INTEGRITY_POLICY_VERSION
    if baseline_version in {RECENT_BASELINE_VERSION, CORROBORATED_BASELINE_VERSION}:
        return RECENT_INTEGRITY_POLICY_VERSION
    if baseline_version == BASELINE_VERSION:
        return INTEGRITY_POLICY_VERSION
    raise ValueError(f"unsupported baseline version: {baseline_version}")


def strategy_fingerprint_payload() -> dict[str, str]:
    """Return the exact current entry-policy versions used by a new season."""

    return {
        "baseline_version": BASELINE_VERSION,
        "integrity_policy_version": INTEGRITY_POLICY_VERSION,
        "sizing_policy_version": SIZING_POLICY_VERSION,
    }
