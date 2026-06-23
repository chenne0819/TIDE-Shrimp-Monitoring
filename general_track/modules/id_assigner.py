# modules/id_assigner.py

from __future__ import annotations

import math


class FixedIDAssigner:
    """Assign detections to stable shrimp IDs without custom ID backtracking."""

    def __init__(self, total_ids: int, match_distance: float) -> None:
        self.fixed_total = total_ids is not None and int(total_ids) > 0
        self.total_ids = max(1, int(total_ids)) if self.fixed_total else 0
        self.match_distance = match_distance
        self._next_id = 1
        self._tracks: dict[int, tuple[float, float]] = {}
        self._tracker_to_fixed: dict[int, int] = {}

    def assign(self, detections: list[dict], prefer_track: bool = False, current_frame_idx: int = 0) -> list[dict]:
        if not detections:
            return detections

        for det in detections:
            det["include_in_stats"] = True

        if prefer_track:
            return self._assign_with_tracker_ids(detections)

        return self._assign_by_distance(detections)

    def _assign_with_tracker_ids(self, detections: list[dict]) -> list[dict]:
        used_ids: set[int] = set()

        for det in detections:
            track_id = det.get("track_id")
            if track_id is None or track_id == "":
                fixed_id = self._next_available_id(used_ids)
                if fixed_id is None:
                    self._tag(det, "", "overflow", 0.0, include=False)
                    continue
                self._tag(det, fixed_id, "track_created", 0.0)
                used_ids.add(fixed_id)
                continue

            track_id = int(track_id)
            fixed_id = self._tracker_to_fixed.get(track_id)
            if fixed_id is None or fixed_id in used_ids:
                fixed_id = self._next_available_id(used_ids)
                if fixed_id is None:
                    self._tag(det, "", "overflow", 0.0, include=False)
                    continue
                self._tracker_to_fixed[track_id] = fixed_id
                status = "track_created"
                distance = 0.0
            else:
                status = "tracked"
                distance = self._distance_to_id(det, fixed_id)

            self._tag(det, fixed_id, status, distance)
            used_ids.add(fixed_id)

        self._update_tracks(detections)
        return detections

    def _assign_by_distance(self, detections: list[dict]) -> list[dict]:
        used_dets: set[int] = set()
        used_ids: set[int] = set()
        pairs = []
        for det_idx, det in enumerate(detections):
            for shrimp_id, (cx, cy) in self._tracks.items():
                if shrimp_id in used_ids:
                    continue
                dist = math.hypot(det["cx"] - cx, det["cy"] - cy)
                if dist <= self.match_distance:
                    pairs.append((dist, det_idx, shrimp_id))

        for dist, det_idx, shrimp_id in sorted(pairs):
            if det_idx in used_dets or shrimp_id in used_ids:
                continue
            self._tag(detections[det_idx], shrimp_id, "matched", dist)
            used_dets.add(det_idx)
            used_ids.add(shrimp_id)

        for det_idx, det in enumerate(detections):
            if det_idx in used_dets:
                continue
            fixed_id = self._next_available_id(used_ids)
            if fixed_id is None:
                fixed_id = self._nearest_unused_id(det, used_ids)
                status = "forced" if fixed_id is not None else "overflow"
                include = fixed_id is not None
            else:
                status = "created"
                include = True

            if fixed_id is None:
                self._tag(det, "", "overflow", 0.0, include=False)
                continue

            self._tag(det, fixed_id, status, self._distance_to_id(det, fixed_id), include=include)
            used_ids.add(fixed_id)

        self._update_tracks(detections)
        return detections

    def _update_tracks(self, detections: list[dict]) -> None:
        for det in detections:
            if det.get("include_in_stats", True) and det.get("shrimp_id") != "":
                self._tracks[int(det["shrimp_id"])] = (det["cx"], det["cy"])

    def _next_available_id(self, used_ids: set[int]) -> int | None:
        if not self.fixed_total:
            while self._next_id in used_ids:
                self._next_id += 1
            shrimp_id = self._next_id
            self._next_id += 1
            return shrimp_id

        while self._next_id <= self.total_ids:
            shrimp_id = self._next_id
            self._next_id += 1
            if shrimp_id not in used_ids:
                return shrimp_id

        candidates = [sid for sid in range(1, self.total_ids + 1) if sid not in used_ids and sid not in self._tracks]
        return min(candidates) if candidates else None

    def _nearest_unused_id(self, det: dict, used_ids: set[int]) -> int | None:
        candidates = [sid for sid in self._tracks if sid not in used_ids]
        if not candidates:
            return None
        return min(candidates, key=lambda sid: self._distance_to_id(det, sid))

    def _distance_to_id(self, det: dict, shrimp_id: int) -> float:
        if shrimp_id not in self._tracks:
            return 0.0
        cx, cy = self._tracks[shrimp_id]
        return math.hypot(det["cx"] - cx, det["cy"] - cy)

    @staticmethod
    def _tag(det: dict, shrimp_id, status: str, distance: float, include: bool = True) -> None:
        det["shrimp_id"] = shrimp_id
        det["id_status"] = status
        det["id_distance"] = round(float(distance), 2)
        det["include_in_stats"] = include
