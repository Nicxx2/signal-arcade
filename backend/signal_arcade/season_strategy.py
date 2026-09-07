"""Small, descriptive season records; never inputs to trading or qualification."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any, Literal, Self

from pydantic import AwareDatetime, BaseModel, Field, StrictBool, model_validator

from .models import ChallengerSkill, Decision

MAX_PARTICIPANTS = 128
SKILLS = ("entry", "manipulation", "sizing", "exit")


class StrategyParticipant(BaseModel):
    kind: Literal["champion", "learner", "ai_critic"]
    skill: Literal["entry", "manipulation", "sizing", "exit", ""]
    version: str = Field(min_length=1, max_length=512)
    first_used_at: AwareDatetime

    @model_validator(mode="after")
    def consistent_identity(self) -> Self:
        if (self.kind == "ai_critic") != (self.skill == "") or not self.version.strip():
            raise ValueError("Participant family, skill and version must identify actual use")
        return self


class SeasonStrategyRecord(BaseModel):
    schema_version: Literal[1]
    tracking_started_at: AwareDatetime
    complete_from_start: StrictBool
    baseline_observed: StrictBool
    first_baseline_at: AwareDatetime | None
    skills_observed: list[ChallengerSkill] = Field(max_length=4)
    ai_observed: StrictBool
    champion_observed: StrictBool
    unattributed_use: StrictBool = False
    participants: list[StrategyParticipant] = Field(max_length=MAX_PARTICIPANTS)
    details_limited: StrictBool

    @model_validator(mode="after")
    def consistent_history(self) -> Self:
        identities = {(p.kind, p.skill, p.version) for p in self.participants}
        skills = {p.skill for p in self.participants if p.skill}
        recorded_skills = {skill.value for skill in self.skills_observed}
        ai = any(p.kind == "ai_critic" for p in self.participants)
        champion = any(p.kind == "champion" for p in self.participants)
        if (
            len(identities) != len(self.participants)
            or len(recorded_skills) != len(self.skills_observed)
            or self.baseline_observed != (self.first_baseline_at is not None)
            or any(p.first_used_at < self.tracking_started_at for p in self.participants)
            or (
                self.first_baseline_at is not None
                and self.first_baseline_at < self.tracking_started_at
            )
        ):
            raise ValueError("Recorded use has inconsistent identities or timestamps")
        if self.details_limited:
            if (
                len(self.participants) != MAX_PARTICIPANTS
                or not skills.issubset(recorded_skills)
                or (ai and not self.ai_observed)
                or (champion and not self.champion_observed)
            ):
                raise ValueError("Bounded history must preserve all retained participation facts")
        elif (
            skills != recorded_skills
            or ai != self.ai_observed
            or champion != self.champion_observed
        ):
            raise ValueError("Summary must match the recorded participants")
        return self


def new_strategy_record(started_at: str, *, complete: bool) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "tracking_started_at": started_at,
        "complete_from_start": complete,
        "baseline_observed": False,
        "first_baseline_at": None,
        "skills_observed": [],
        "ai_observed": False,
        "champion_observed": False,
        "unattributed_use": False,
        "participants": [],
        "details_limited": False,
    }


def read_strategy_record(raw: str | None) -> dict[str, Any] | None:
    if raw is None:
        return None
    try:
        return SeasonStrategyRecord.model_validate_json(raw).model_dump(mode="json")
    except (ValueError, TypeError):
        return None


def decision_participants(decision: Decision) -> list[dict[str, str]]:
    participants = []
    for skill in SKILLS:
        receipt = decision.challenger_assessments.get(skill)
        if not isinstance(receipt, dict):
            continue
        parameters = receipt.get("parameters")
        version = receipt.get("artifact_version")
        if isinstance(parameters, dict) and parameters.get("applied") is True:
            participants.append(
                {
                    "kind": "champion",
                    "skill": skill,
                    "version": version
                    if isinstance(version, str) and receipt.get("skill") == skill
                    else "",
                }
            )
    legacy = decision.learning_assessment
    if (
        legacy is not None
        and legacy.applied
        and not any(item["skill"] == "entry" for item in participants)
    ):
        participants.append({"kind": "learner", "skill": "entry", "version": legacy.model_version})
    # The critic adds its prompt policy to the final decision only for an applied valid veto.
    # Shadow reviews and an enabled-but-unused critic do not change the decision's provenance.
    for version in decision.model_version.split("+"):
        if version.startswith("ai-critic-") and len(version) <= 128:
            participants.append({"kind": "ai_critic", "skill": "", "version": version})
    return participants


def record_strategy_use(
    original: dict[str, Any], participants: list[dict[str, str]], at: str
) -> dict[str, Any]:
    """Copy only on a new participation fact; repeated market ticks require no writes."""
    try:
        if datetime.fromisoformat(at) < datetime.fromisoformat(original["tracking_started_at"]):
            return original
    except (ValueError, TypeError):
        return original
    valid = []
    unattributed = original.get("unattributed_use", False)
    baseline_use = not participants
    for participant in participants:
        try:
            parsed = StrategyParticipant.model_validate({**participant, "first_used_at": at})
            valid.append({"kind": parsed.kind, "skill": parsed.skill, "version": parsed.version})
        except (ValueError, TypeError):
            unattributed = True
    participants = valid
    known = {(p["kind"], p["skill"], p["version"]) for p in original["participants"]}
    unique = {(p["kind"], p["skill"], p["version"]): p for p in participants}
    additions = [p for key, p in unique.items() if key not in known]
    skills = sorted(
        set(original["skills_observed"]) | {p["skill"] for p in participants if p["skill"]}
    )
    ai = original["ai_observed"] or any(p["kind"] == "ai_critic" for p in participants)
    champion = original["champion_observed"] or any(p["kind"] == "champion" for p in participants)
    baseline = original["baseline_observed"] or baseline_use
    limited = original["details_limited"] or len(known) + len(additions) > MAX_PARTICIPANTS
    remaining = max(0, MAX_PARTICIPANTS - len(known))
    if (
        not additions[:remaining]
        and skills == original["skills_observed"]
        and ai == original["ai_observed"]
        and champion == original["champion_observed"]
        and baseline == original["baseline_observed"]
        and limited == original["details_limited"]
        and unattributed == original.get("unattributed_use", False)
    ):
        return original
    return {
        **original,
        "baseline_observed": baseline,
        "first_baseline_at": original["first_baseline_at"] or (at if baseline_use else None),
        "skills_observed": skills,
        "ai_observed": ai,
        "champion_observed": champion,
        "details_limited": limited,
        "unattributed_use": unattributed,
        "participants": [
            *original["participants"],
            *[{**p, "first_used_at": at} for p in additions[:remaining]],
        ],
    }


def strategy_view(raw: str | None) -> dict[str, Any]:
    record = read_strategy_record(raw)
    if record is None:
        return {"status": "unknown", "complete_from_start": False, "participants": []}
    assisted = bool(record["skills_observed"] or record["ai_observed"])
    status = (
        "mixed"
        if assisted and record["baseline_observed"]
        else "assisted"
        if assisted
        else "unknown"
        if not record["complete_from_start"] or record["unattributed_use"]
        else "baseline"
        if record["baseline_observed"]
        else "no_decisions"
    )
    return {
        **record,
        "status": status,
        "participants": [
            {
                **p,
                "name": champion_codename(p["version"], ChallengerSkill(p["skill"]))
                if p["kind"] == "champion" and p["skill"] in SKILLS
                else "Local AI critic"
                if p["kind"] == "ai_critic"
                else f"{p['skill'].capitalize()} learner",
            }
            for p in record["participants"]
        ],
    }


def incomplete_record() -> dict[str, Any]:
    return new_strategy_record(datetime.now(UTC).isoformat(), complete=False)


def champion_codename(version: str, skill: ChallengerSkill) -> str:
    """Frozen identity recipe shared by the Arena and the season usage record."""
    adjectives = ("Bright", "Calm", "Clear", "Keen", "Lucid", "Quiet", "Steady", "Violet")
    nouns = {
        ChallengerSkill.ENTRY: ("Beacon", "Pathfinder", "Scout", "Wayfinder"),
        ChallengerSkill.MANIPULATION: ("Sentinel", "Shield", "Watchtower", "Warden"),
        ChallengerSkill.SIZING: ("Allocator", "Balancer", "Steward", "Surveyor"),
        ChallengerSkill.EXIT: ("Harbormaster", "Navigator", "Timekeeper", "Trailkeeper"),
    }[skill]
    digest = hashlib.sha256(f"{skill.value}:{version}".encode()).digest()
    return f"{adjectives[digest[0] % len(adjectives)]} {nouns[digest[1] % len(nouns)]}"
