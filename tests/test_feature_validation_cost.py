"""Faster field traversal must retain every chronological proof selection decision."""

import math
import random

import pytest
from signal_arcade.intelligence.learning import FEATURE_NAMES, _features_complete


def reference(features):
    return all(name in features and math.isfinite(features[name]) for name in FEATURE_NAMES)


@pytest.mark.parametrize("position", range(len(FEATURE_NAMES)))
@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), -float("inf"), 0.0, -0.5])
def test_every_field_preserves_missing_finite_and_nonfinite_semantics(position, value):
    features = dict.fromkeys(FEATURE_NAMES, 0.2)
    if value is None:
        features.pop(FEATURE_NAMES[position])
    else:
        features[FEATURE_NAMES[position]] = value
    assert _features_complete(features) == reference(features)


def test_short_circuit_exception_order_and_fresh_revalidation():
    features = dict.fromkeys(FEATURE_NAMES, 0.3)
    assert _features_complete(features)
    features[FEATURE_NAMES[1]] = None
    features.pop(FEATURE_NAMES[0])
    assert not _features_complete(features) and not reference(features)
    features[FEATURE_NAMES[0]] = 0.1
    with pytest.raises(TypeError):
        reference(features)
    with pytest.raises(TypeError):
        _features_complete(features)
    features[FEATURE_NAMES[1]] = -1.0
    assert _features_complete(features)


def test_mixed_vectors_match_original_validation_without_mutation():
    rng = random.Random(240923)  # noqa: S311 -- deterministic fixture
    for _ in range(150):
        features = {
            name: rng.choice([-1.0, 0.0, 0.7, 1.0, float("inf")])
            for name in FEATURE_NAMES
            if rng.random() > 0.02
        }
        original = features.copy()
        assert _features_complete(features) == reference(features)
        assert features == original
