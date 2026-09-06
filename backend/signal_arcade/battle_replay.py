"""Bounded recording of already-computed tournament evidence; never scores a policy."""

from __future__ import annotations

import copy
import math
from datetime import UTC, datetime
from typing import Any, TypeGuard

from .models import ChallengerSkillState

MAX_REPLAY_POINTS = 32
MAX_REPLAY_BYTES = 32_768
REPLAY_VERSION = "battle-checkpoints-v1"


def _finite_number(value: Any) -> TypeGuard[float]:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def start_replay(state: ChallengerSkillState, minimum: int, coverage: float) -> None:
    state._battle_replay = {
        "version": REPLAY_VERSION,
        "cohort_key": state.cohort_key,
        "skill": state.skill.value,
        "candidate_version": state.testing_version,
        "champion_version": state.champion_version,
        "minimum_samples": minimum,
        "minimum_coverage": coverage,
        "partial": False,
        "sampled": False,
        "points": [],
    }
    state._battle_replay_dirty = True


def record_replay(state: ChallengerSkillState, minimum: int, coverage: float) -> None:
    # Some independent arithmetic tests use a minimal state double. Recording is optional.
    if not isinstance(state, ChallengerSkillState):
        return
    stats = state.last_tournament
    if not state.testing_version or not state.champion_version:
        return
    if (
        stats.get("candidate_version") != state.testing_version
        or stats.get("champion_version") != state.champion_version
    ):
        return
    replay = state._battle_replay
    if (
        replay is None
        or replay.get("candidate_version") != state.testing_version
        or replay.get("champion_version") != state.champion_version
    ):
        start_replay(state, minimum, coverage)
        replay = state._battle_replay
        assert replay is not None
        replay["partial"] = True
    observed = stats.get("common_observed_count", 0)
    usable = stats.get("common_usable_count", 0)
    if type(observed) is not int or type(usable) is not int or not 0 <= usable <= observed:
        return
    point: dict[str, Any] = {
        "observed": observed,
        "usable": usable,
        "coverage": usable / observed if observed else 0.0,
        "mean": stats.get("mean_uplift"),
        "lower": stats.get("uplift_lower_bound"),
        "upper": stats.get("uplift_upper_bound"),
    }
    if any(
        value is not None and not _finite_number(value)
        for value in (point["mean"], point["lower"], point["upper"])
    ):
        return
    if (
        all(point[key] is not None for key in ("lower", "mean", "upper"))
        and not point["lower"] <= point["mean"] <= point["upper"]
    ):
        return
    points = replay["points"]
    if points and all(points[-1].get(key) == value for key, value in point.items()):
        return
    now = datetime.now(UTC)
    if points and now <= datetime.fromisoformat(points[-1]["at"]):
        replay["partial"] = True
        state._battle_replay_dirty = True
        return
    point.update(at=now.isoformat(), sequence=points[-1]["sequence"] + 1 if points else 0)
    points.append(point)
    if len(points) > MAX_REPLAY_POINTS:
        # Keep endpoints and favour retaining real turning points. Every retained value is exact.
        def importance(index: int) -> tuple[float, int]:
            values = [points[i]["mean"] for i in (index - 1, index, index + 1)]
            if any(value is None for value in values):
                return (math.inf if values[1] is None and values[0] is not None else 0.0, index)
            return abs(values[1] - (values[0] + values[2]) / 2), index

        del points[min(range(1, len(points) - 1), key=importance)]
        replay["sampled"] = True
    state._battle_replay_dirty = True


def freeze_replay(state: ChallengerSkillState, event_id: str) -> None:
    replay = state._battle_replay
    if replay and replay["points"]:
        state._pending_battle_replays[event_id] = copy.deepcopy(replay)


def valid_replay(value: Any) -> TypeGuard[dict[str, Any]]:
    if not isinstance(value, dict) or value.get("version") != REPLAY_VERSION:
        return False
    if any(
        not isinstance(value.get(key), str) or not 1 <= len(value[key]) <= 180
        for key in ("cohort_key", "candidate_version", "champion_version")
    ):
        return False
    if (
        value.get("skill") not in ("entry", "manipulation", "sizing", "exit")
        or value["candidate_version"] == value["champion_version"]
    ):
        return False
    if type(value.get("minimum_samples")) is not int or not 1 <= value["minimum_samples"] <= 10000:
        return False
    threshold = value.get("minimum_coverage")
    if not _finite_number(threshold) or not 0 < threshold <= 1:
        return False
    if any(type(value.get(key)) is not bool for key in ("partial", "sampled")):
        return False
    points = value.get("points")
    if not isinstance(points, list) or not 1 <= len(points) <= MAX_REPLAY_POINTS:
        return False
    previous_time, previous_sequence = datetime.min.replace(tzinfo=UTC), -1
    for point in points:
        if not isinstance(point, dict):
            return False
        at, sequence = point.get("at"), point.get("sequence")
        try:
            if not isinstance(at, str) or len(at) > 40:
                return False
            parsed = datetime.fromisoformat(at)
            if parsed.utcoffset() is None:
                return False
        except ValueError:
            return False
        if parsed <= previous_time or type(sequence) is not int or sequence <= previous_sequence:
            return False
        previous_time, previous_sequence = parsed, sequence
        usable, observed, coverage = (
            point.get("usable"),
            point.get("observed"),
            point.get("coverage"),
        )
        if type(usable) is not int or type(observed) is not int or not 0 <= usable <= observed:
            return False
        if (
            not _finite_number(coverage)
            or abs(coverage - (usable / observed if observed else 0)) > 1e-9
        ):
            return False
        mean, lower, upper = (point.get(key) for key in ("mean", "lower", "upper"))
        if any(v is not None and not _finite_number(v) for v in (mean, lower, upper)):
            return False
        if (
            mean is not None
            and lower is not None
            and upper is not None
            and not lower <= mean <= upper
        ):
            return False
    return True
