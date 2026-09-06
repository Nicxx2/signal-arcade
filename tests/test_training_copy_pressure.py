from __future__ import annotations

import json
from dataclasses import replace

import pytest
from signal_arcade.intelligence.training_job import (
    TRAINING_COPY_CHUNK_ROWS,
    TRAINING_INPUTS,
    freeze_training_inputs,
    thaw_training_inputs,
)
from test_v1104_training_history import training_fixture

# This suite verifies private workspace isolation and resource bounds.
# ruff: noqa: SLF001


@pytest.mark.parametrize("count", [0, 1, 31, 32, 33, 97])
def test_training_copy_keeps_all_rows_in_order_across_chunk_boundaries(settings, count):
    learner, database, _ = training_fixture(settings)
    try:
        rows = list(learner.observations.values())[:count]
        frozen = freeze_training_inputs((rows, [], [], [], []))
        assert len(frozen) == (count + TRAINING_COPY_CHUNK_ROWS - 1) // TRAINING_COPY_CHUNK_ROWS
        assert all(len(json.loads(part)[0]) <= TRAINING_COPY_CHUNK_ROWS for part in frozen)
        restored = thaw_training_inputs(frozen)
        reference = TRAINING_INPUTS.validate_json(
            TRAINING_INPUTS.dump_json(
                (rows, [], [], [], []),
                round_trip=True,
                exclude={0: {"__all__": {"size_trials", "challenger_evaluations"}}},
            )
        )
        assert restored == reference
        assert [row.mint for row in restored[0]] == [row.mint for row in rows]
    finally:
        database.close()


def test_training_copy_retains_uneven_model_artifact_and_state_tails(settings, monkeypatch):
    learner, database, _ = training_fixture(settings)
    try:
        assert learner.run_next_training()
        inputs = (
            list(learner.observations.values()),
            list(learner.evidence_episodes.values()),
            learner.models * 33,
            list(learner.skill_artifacts.values()) * 17,
            list(learner.skill_states.values()) * 11,
        )
        frozen = freeze_training_inputs(inputs)
        yields = []
        monkeypatch.setattr("signal_arcade.intelligence.training_job.time.sleep", yields.append)
        restored = thaw_training_inputs(frozen)
        reference = TRAINING_INPUTS.validate_json(
            TRAINING_INPUTS.dump_json(
                inputs,
                round_trip=True,
                exclude={
                    0: {"__all__": {"size_trials", "challenger_evaluations"}},
                    1: {"__all__": {"challenger_evaluations"}},
                },
            )
        )
        assert restored == reference
        assert yields == [0] * len(frozen)
    finally:
        database.close()


def test_broken_later_training_chunk_cannot_publish_partial_evidence(settings):
    learner, database, _ = training_fixture(settings)
    try:
        job = learner.prepare_next_training()
        assert job is not None and isinstance(job.frozen_inputs, tuple)
        broken = replace(job, frozen_inputs=(*job.frozen_inputs[:-1], b"invalid"))
        with pytest.raises(ValueError) as failure:
            learner.fit_training_job(broken)
        with pytest.raises(ValueError):
            learner.finish_training_job(broken, error=failure.value)
        assert learner.has_pending_training()
        assert database.list_learning_models() == []
        assert database.list_challenger_artifacts() == []
        assert not broken.workspace._training_output.models
    finally:
        database.close()
