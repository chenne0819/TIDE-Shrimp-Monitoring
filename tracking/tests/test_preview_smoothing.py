import math

import pytest

from general_track.modules.preview_smoothing import PreviewSmoothing


def item(probability, track_id=1):
    return {"track_id": track_id, "male_probability": probability,
            "label": "male" if probability >= 0.5 else "female", "confidence": 0.8}


def test_uses_probabilities_and_preserves_source_items():
    smoothing = PreviewSmoothing()
    source = item(0.2)
    smoothing.update([source], 0)
    result = smoothing.update([item(0.8)], 0.5)[0]
    assert result["preview_male_probability"] == pytest.approx(0.2 + (1 - math.exp(-0.5)) * 0.6)
    assert result["label"] == "female"
    assert result["raw_label"] == "male"
    assert source == item(0.2)


def test_constant_input_smoothing_is_independent_of_fps():
    scores = []
    for fps in (2, 10, 30):
        smoothing = PreviewSmoothing()
        smoothing.update([item(0.1)], 0)
        for tick in range(1, fps + 1):
            result = smoothing.update([item(0.9)], tick / fps)[0]
        scores.append(result["preview_male_probability"])
    assert scores == pytest.approx([0.1 + (1 - math.exp(-1)) * 0.8] * 3)


def test_reverse_evidence_requires_one_second_after_smoothed_crossing():
    smoothing = PreviewSmoothing()
    smoothing.update([item(0.1)], 0)
    # The filtered probability crosses 0.5 at t=0.7.
    for tick in range(1, 17):
        assert smoothing.update([item(0.9)], tick / 10)[0]["label"] == "female"
    assert smoothing.update([item(0.9)], 1.7)[0]["label"] == "male"


def test_brief_reverse_spike_and_alternation_do_not_switch():
    smoothing = PreviewSmoothing()
    smoothing.update([item(0.1)], 0)
    assert smoothing.update([item(0.99)], 0.1)[0]["label"] == "female"
    for tick in range(2, 102):
        probability = 0.9 if tick % 2 else 0.1
        assert smoothing.update([item(probability)], tick / 10)[0]["label"] == "female"


def test_new_id_does_not_inherit_other_tracks_history():
    smoothing = PreviewSmoothing()
    smoothing.update([item(0.99, 1)], 0)
    result = smoothing.update([item(0.01, 2)], 0.1)[0]
    assert result["label"] == "female"
    assert result["preview_male_probability"] == 0.01
    assert smoothing.update([item(0.01, 1)], 0.2)[0]["label"] == "male"


def test_untracked_detection_is_pending_and_never_accumulates():
    smoothing = PreviewSmoothing()
    result = smoothing.update([item(0.99, None)], 0)[0]
    assert result["label"] == "pending"
    assert result["raw_label"] == "male"
    assert result["preview_male_probability"] is None
    assert not smoothing._tracks


def test_short_miss_interrupts_confirmation_and_long_miss_resets():
    smoothing = PreviewSmoothing()
    smoothing.update([item(0.1)], 0)
    for tick in range(1, 11):
        smoothing.update([item(0.9)], tick / 10)
    smoothing.update([], 1.1)
    for tick in range(12, 22):
        assert smoothing.update([item(0.9)], tick / 10)[0]["label"] == "female"
    assert smoothing.update([item(0.9)], 2.2)[0]["label"] == "male"
    assert smoothing.update([item(0.01)], 5.21)[0]["label"] == "female"


def test_gap_does_not_turn_one_frame_into_sustained_evidence():
    smoothing = PreviewSmoothing()
    smoothing.update([item(0.1)], 0)
    for tick in range(1, 11):
        smoothing.update([item(0.9)], tick / 10)
    previous = smoothing._tracks[1].probability
    result = smoothing.update([item(0.99)], 2.5)[0]
    assert result["label"] == "female"
    assert result["preview_male_probability"] == previous
    assert smoothing._tracks[1].candidate_since is None


def test_configured_threshold_is_used_without_replacing_it():
    smoothing = PreviewSmoothing(threshold=0.03)
    result = smoothing.update([item(0.04)], 0)[0]
    assert result["label"] == "male"
    assert result["raw_label"] == "female"


@pytest.mark.parametrize("probability", [float("nan"), float("inf"), -0.1, 1.1])
def test_invalid_probabilities_are_rejected(probability):
    with pytest.raises(ValueError, match="probability"):
        PreviewSmoothing().update([item(probability)], 0)


def test_new_session_has_no_classification_history():
    first = PreviewSmoothing()
    first.update([item(0.99)], 0)
    assert PreviewSmoothing().update([item(0.01)], 0.1)[0]["label"] == "female"
