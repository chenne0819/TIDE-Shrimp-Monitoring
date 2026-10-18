"""Time-aware display smoothing for preview and video; raw predictions stay intact."""
from dataclasses import dataclass
import math


@dataclass
class _TrackState:
    last_seen: float
    label: str
    probability: float
    candidate: str | None = None
    candidate_since: float | None = None


class PreviewSmoothing:
    TIME_CONSTANT_SECONDS = 1.0
    CONFIRM_SECONDS = 1.0
    RETENTION_SECONDS = 3.0
    MAX_OBSERVATION_GAP_SECONDS = 1.0

    def __init__(self, threshold=None):
        self.threshold = 0.5 if threshold is None else threshold
        self._tracks = {}

    def update(self, items, now):
        self._tracks = {key: state for key, state in self._tracks.items()
                        if now - state.last_seen <= self.RETENTION_SECONDS}
        visible = {item["track_id"] for item in items}
        for track_id, state in self._tracks.items():
            if track_id not in visible:
                state.candidate = state.candidate_since = None
        result = []
        for item in items:
            displayed = dict(item)
            displayed["raw_label"] = item["label"]
            track_id = item["track_id"]
            if track_id is None:
                displayed.update(label="pending", preview_male_probability=None)
                result.append(displayed)
                continue
            probability = float(item["male_probability"])
            if not math.isfinite(probability) or not 0 <= probability <= 1:
                raise ValueError("Preview male probability must be finite and between 0 and 1")
            state = self._tracks.get(track_id)
            if state is None:
                label = "male" if probability >= self.threshold else "female"
                state = _TrackState(now, label, probability)
                self._tracks[track_id] = state
            else:
                elapsed = now - state.last_seen
                if elapsed > self.MAX_OBSERVATION_GAP_SECONDS:
                    # Missing time is not additional evidence for the current frame.
                    state.candidate = state.candidate_since = None
                else:
                    alpha = -math.expm1(-max(0.0, elapsed) / self.TIME_CONSTANT_SECONDS)
                    state.probability += alpha * (probability - state.probability)
                    candidate = "male" if state.probability >= self.threshold else "female"
                    if candidate == state.label:
                        state.candidate = state.candidate_since = None
                    elif state.candidate != candidate:
                        state.candidate, state.candidate_since = candidate, now
                    elif now - state.candidate_since >= self.CONFIRM_SECONDS - 1e-9:
                        state.label = candidate
                        state.candidate = state.candidate_since = None
            state.last_seen = now
            displayed.update(label=state.label, preview_male_probability=state.probability)
            result.append(displayed)
        return result
