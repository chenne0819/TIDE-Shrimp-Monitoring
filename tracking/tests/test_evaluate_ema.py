import pytest

from evaluate_ema import aggregate, evaluate_trace


def trace(probabilities, label="male", fps=10):
    frames = [{"frame": index, "wall_seconds": index / fps, "source_seconds": index / fps,
               "items": [{"track_id": 1, "label": "male" if probability >= 0.03 else "female",
                          "confidence": 0.9, "male_probability": probability}]}
              for index, probability in enumerate(probabilities)]
    metadata = {"video": "test.mp4", "truth": label, "fps": fps, "expected_shrimp": 5}
    return frames, metadata


def test_known_constant_labels_get_correct_rates():
    frames, metadata = trace([0.9] * 20)
    result = evaluate_trace(frames, metadata, 0.5)
    assert result["accuracy"] == 1
    assert result["observations"] == 20
    assert result["switches"] == 0
    assert result["unique_track_ids"] == 1
    assert result["tracked_observation_seconds"] == pytest.approx(2)
    assert result["valid_observations_per_expected_shrimp_frame"] == 0.2


def test_incorrect_constant_is_not_scored_as_stable_success():
    frames, metadata = trace([0.9] * 20, label="female")
    result = evaluate_trace(frames, metadata, 0.5)
    assert result["accuracy"] == 0
    assert result["switches"] == 0
    assert result["segments_never_correct"] == 1
    assert result["error_observation_seconds"] == pytest.approx(2)


def test_replay_counts_switch_and_recovery_delay():
    frames, metadata = trace([0.1] + [0.9] * 30)
    result = evaluate_trace(frames, metadata, 0.5)
    assert result["switches"] == 1
    assert result["mean_first_correct_source_seconds"] == pytest.approx(1.7)
    assert result["correct_observations"] == 14


def test_missing_frames_and_no_id_are_not_counted_as_correct():
    frames, metadata = trace([0.9, 0.9, 0.9])
    frames[1]["items"] = []
    frames[2]["items"][0]["track_id"] = None
    result = evaluate_trace(frames, metadata, 0.5)
    assert result["observations"] == 1
    assert result["empty_frames"] == 1
    assert result["untracked_classifications"] == 1
    assert result["valid_observations_per_expected_shrimp_frame"] == pytest.approx(1 / 15)


def test_threshold_results_do_not_mutate_cached_predictions():
    frames, metadata = trace([0.2] * 20)
    assert evaluate_trace(frames, metadata, 0.1)["accuracy"] == 1
    assert evaluate_trace(frames, metadata, 0.5)["accuracy"] == 0
    assert evaluate_trace(frames, metadata, 0.1)["accuracy"] == 1
    assert frames[0]["items"][0]["male_probability"] == 0.2


def test_new_ids_and_expired_states_are_separate_segments():
    frames, metadata = trace([0.9, 0.1, 0.1])
    frames[1]["items"][0]["track_id"] = 2
    frames[2]["wall_seconds"] = 4
    result = evaluate_trace(frames, metadata, 0.5)
    assert result["unique_track_ids"] == 2
    assert result["track_segments"] == 3
    assert result["switches"] == 0


def test_video_balancing_does_not_favor_long_video():
    male_frames, male_metadata = trace([0.9] * 100)
    female_frames, female_metadata = trace([0.9], label="female")
    result = aggregate([evaluate_trace(male_frames, male_metadata, 0.5),
                        evaluate_trace(female_frames, female_metadata, 0.5)])
    assert result["balanced_accuracy"] == 0.5
    assert result["macro_f1_video_balanced"] == pytest.approx(1 / 3)
