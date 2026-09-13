"""Deterministic acquisition-capacity experiment, not a live coverage forecast."""

from collections import Counter
from datetime import timedelta
from types import SimpleNamespace as NS

from signal_arcade.intelligence.learning import LEARNING_HORIZONS_SECONDS, LearningEngine
from signal_arcade.models import (
    LearningEvidenceLane,
    LearningEvidenceStatus,
    LearningObservationStatus,
)
from test_v1104_refresh import scheduler_fixture


def collection_workload(batch_size, *, pressure=False):
    learner, states, start = scheduler_fixture()
    prototype = states["discovery-0"]
    learner.observations.clear()
    learner.evidence_episodes.clear()
    states.clear()
    requests = 0
    selected_counts = Counter()
    closed = Counter()
    # Equal fixed arrivals for every alternative: one Discovery each 7s for 30m;
    # every fourth mint also has a Policy episode with its own 13s-later clock.
    for second in range(0, 3101):
        now = start + timedelta(seconds=second)
        if second < 1800 and second % 7 == 0:
            index = second // 7
            mint = f"mint-{index}"
            state = type(prototype)(
                mint=mint,
                last_reserve_at=start - timedelta(minutes=5),
                virtual_token_reserves=10**15,
                virtual_quote_reserves=10**10,
            )
            states[mint] = state
            learner.observations[mint] = NS(
                mint=mint, created_at=now, status=LearningObservationStatus.PENDING, checkpoints={}
            )
            if index % 4 == 0:
                learner.evidence_episodes[mint] = NS(
                    mint=mint,
                    entry_at=now + timedelta(seconds=13),
                    lane=LearningEvidenceLane.POLICY,
                    status=LearningEvidenceStatus.PENDING,
                    checkpoints={},
                )
        # 10s interval plus a declared 1s request cost. Occasional 33s pressure windows.
        if second % 11 == 0 and not (pressure and second % 300 < 33):
            selected = LearningEngine.due_checkpoint_mints(
                learner, states, now, limit=batch_size, fresh=False
            )
            assert len(selected) <= batch_size
            if selected:
                requests += 1
            selected_counts.update(selected)
            # Every fifth route is independently unavailable. Larger batches must not
            # turn those failures into useful evidence or remove their denominator.
            for mint in selected:
                available = int(mint.split("-")[1]) % 5 != 0
                for item, entered in (
                    (learner.observations[mint], learner.observations[mint].created_at),
                    (
                        learner.evidence_episodes.get(mint),
                        learner.evidence_episodes[mint].entry_at
                        if mint in learner.evidence_episodes
                        else now,
                    ),
                ):
                    if item is None:
                        continue
                    for horizon in LEARNING_HORIZONS_SECONDS:
                        age = (now - entered).total_seconds()
                        if horizon <= age <= horizon + 90 and str(horizon) not in item.checkpoints:
                            item.checkpoints[str(horizon)] = (
                                "usable" if available else "unavailable"
                            )
        for lane, items in (
            ("discovery", learner.observations),
            ("policy", learner.evidence_episodes),
        ):
            for item in items.values():
                entered = item.created_at if lane == "discovery" else item.entry_at
                for horizon in LEARNING_HORIZONS_SECONDS:
                    if (now - entered).total_seconds() > horizon + 90:
                        item.checkpoints.setdefault(str(horizon), "expired")
                if len(item.checkpoints) == 5:
                    item.status = (
                        LearningObservationStatus.COMPLETE
                        if lane == "discovery"
                        else LearningEvidenceStatus.COMPLETE
                    )
    for lane, items in (("discovery", learner.observations), ("policy", learner.evidence_episodes)):
        for item in items.values():
            assert len(item.checkpoints) == 5, "Only complete, equivalent cohorts are compared"
            for horizon, outcome in item.checkpoints.items():
                closed[(lane, int(horizon), outcome)] += 1
    return closed, requests


def test_existing_bounded_batch_options_reduce_acquisition_losses_without_moving_clocks():
    for pressure in (False, True):
        results = {size: collection_workload(size, pressure=pressure) for size in (5, 10, 20)}
        for size, (counts, requests) in results.items():
            print(
                {
                    "batch": size,
                    "pressure": pressure,
                    "requests": requests,
                    "primary_discovery": {
                        outcome: counts[("discovery", 300, outcome)]
                        for outcome in ("usable", "unavailable", "expired")
                    },
                }
            )
        for lane in ("discovery", "policy"):
            for horizon in LEARNING_HORIZONS_SECONDS:
                for smaller, larger in ((5, 10), (10, 20)):
                    small, large = results[smaller][0], results[larger][0]
                    assert large[(lane, horizon, "usable")] >= small[(lane, horizon, "usable")]
                    assert large[(lane, horizon, "expired")] <= small[(lane, horizon, "expired")]
                    assert sum(
                        large[(lane, horizon, x)] for x in ("usable", "unavailable", "expired")
                    ) == sum(
                        small[(lane, horizon, x)] for x in ("usable", "unavailable", "expired")
                    )
        assert (
            results[10][0][("discovery", 300, "usable")]
            > results[5][0][("discovery", 300, "usable")]
        )
