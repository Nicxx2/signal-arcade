"""Private fit workspace and immutable outputs; workers cannot publish authority."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import TypeAdapter

from ..models import (
    ChallengerSkillArtifact,
    ChallengerSkillState,
    LearningEvidenceEpisode,
    LearningModel,
    LearningObservation,
    RiskMode,
)

if TYPE_CHECKING:
    from ..database import Database

TrainingInputs = tuple[
    list[LearningObservation],
    list[LearningEvidenceEpisode],
    list[LearningModel],
    list[ChallengerSkillArtifact],
    list[ChallengerSkillState],
]
TRAINING_INPUTS: TypeAdapter[TrainingInputs] = TypeAdapter(TrainingInputs)
TRAINING_COPY_CHUNK_ROWS = 32


def freeze_training_inputs(inputs: TrainingInputs) -> tuple[bytes, ...]:
    """Freeze the complete boundary in small serializer calls, retaining every input row."""
    observations, episodes, models, artifacts, states = inputs
    length = max(len(observations), len(episodes), len(models), len(artifacts), len(states))
    return tuple(
        TRAINING_INPUTS.dump_json(
            (
                observations[offset : offset + TRAINING_COPY_CHUNK_ROWS],
                episodes[offset : offset + TRAINING_COPY_CHUNK_ROWS],
                models[offset : offset + TRAINING_COPY_CHUNK_ROWS],
                artifacts[offset : offset + TRAINING_COPY_CHUNK_ROWS],
                states[offset : offset + TRAINING_COPY_CHUNK_ROWS],
            ),
            round_trip=True,
            # Account hashes and decoded reserve audits stay in the durable evidence journal.
            # Fitting consumes the recorded values, missing reasons and chronological times,
            # never these bulky nested proofs. Keep all Policy sizing economics and checkpoints.
            exclude={
                0: {
                    "__all__": {
                        "size_trials": True,
                        "challenger_evaluations": True,
                        "checkpoints": {"__all__": {"route_snapshot"}},
                    }
                },
                1: {
                    "__all__": {
                        "challenger_evaluations": True,
                        "checkpoints": {"__all__": {"route_snapshot"}},
                        "size_trials": {
                            "__all__": {
                                "checkpoints": {"__all__": {"route_snapshot"}},
                            }
                        },
                    }
                },
            },
        )
        for offset in range(0, length, TRAINING_COPY_CHUNK_ROWS)
    )


def thaw_training_inputs(frozen: tuple[bytes, ...] | bytes) -> TrainingInputs:
    """Reconstruct off the market boundary, yielding between bounded validation calls."""
    if isinstance(frozen, bytes):
        # Retained for direct callers comparing a complete reference cohort.
        return TRAINING_INPUTS.validate_json(frozen)
    result: TrainingInputs = ([], [], [], [], [])
    for payload in frozen:
        chunk = TRAINING_INPUTS.validate_json(payload)
        result[0].extend(chunk[0])
        result[1].extend(chunk[1])
        result[2].extend(chunk[2])
        result[3].extend(chunk[3])
        result[4].extend(chunk[4])
        # A native Pydantic call can hold Python's GIL for the whole payload. Merely putting
        # one large call in a thread does not let market/event-loop Python run during it.
        time.sleep(0)
    return result


@dataclass
class TrainingOutput:
    models: list[LearningModel] = field(default_factory=list)
    artifacts: list[tuple[ChallengerSkillArtifact, str, bytes | None]] = field(default_factory=list)


@dataclass
class TrainingJob:
    workspace: Any
    key: tuple[RiskMode, str | None]
    requested_at: datetime
    started_monotonic: float
    authority_context: tuple[Any, ...]
    runtime_context: tuple[Any, ...]
    frozen_inputs: tuple[bytes, ...] | bytes
    phase_seconds: dict[str, float] = field(default_factory=dict)


class TrainingReader:
    """Only artifact reads are permitted from a fitting thread."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def load_statistical_model_artifact(self, version: str) -> dict[str, str | bytes] | None:
        return self._database.load_statistical_model_artifact(version)
