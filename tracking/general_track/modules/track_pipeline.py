from __future__ import annotations

from collections import Counter, defaultdict, deque
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from tqdm import tqdm
from ultralytics import YOLO

from shrimp_monitoring import MonitoringSession, summarize_measurements

from .config import HBB_CONF, IMGSZ_HBB, IMGSZ_OBB, MODEL_HBB_PATH, MODEL_HEAD_TAIL_OBB_PATH
from .head_tail_common import (
    associated_centers,
    combine_preview,
    debug_video_size,
    fit_preview_to_screen,
    letterbox,
    obb_rows,
    rectify_shrimp,
    show_preview_or_raise,
    split_head_tail_rows,
    transform_x,
    validate_head_tail_obb_model,
    write_csv,
)


WINDOW_FRAMES = 300
FEMALE_MAX_RATE = 1.0 / 3.0
MALE_MIN_RATE = 2.0 / 3.0


class SlidingVoteState:
    def __init__(self, window_frames: int = WINDOW_FRAMES, grace_frames: int = 30) -> None:
        self.window_frames = int(window_frames)
        self.grace_frames = int(grace_frames)
        self.events: dict[int, deque[tuple[int, int]]] = defaultdict(deque)
        self.last_male_frame: dict[int, int] = {}

    def update(self, track_id: int, frame_index: int, male_detected: bool) -> tuple[str, float, int, int, bool, bool]:
        if male_detected:
            self.last_male_frame[track_id] = frame_index
            male_hit = True
        else:
            last = self.last_male_frame.get(track_id)
            male_hit = last is not None and frame_index - last <= self.grace_frames

        queue = self.events[track_id]
        queue.append((frame_index, int(male_hit)))
        min_frame = frame_index - self.window_frames + 1
        while queue and queue[0][0] < min_frame:
            queue.popleft()

        male_hits = int(sum(value for _, value in queue))
        window_ready = len(queue) >= self.window_frames
        denominator = self.window_frames if window_ready else max(len(queue), 1)
        male_rate = male_hits / denominator
        if male_rate >= MALE_MIN_RATE:
            label = "M"
        elif male_rate < FEMALE_MAX_RATE:
            label = "F"
        else:
            label = "obs"
        return label, male_rate, male_hits, denominator, male_hit, window_ready


class HbbVotingShrimpAnalyzer:
    def __init__(
        self,
        obb_model_path: str = MODEL_HEAD_TAIL_OBB_PATH,
        hbb_model_path: str = MODEL_HBB_PATH,
        window_frames: int = WINDOW_FRAMES,
        monitoring: MonitoringSession | None = None,
    ) -> None:
        self.obb_model_path = obb_model_path
        self.hbb_model_path = hbb_model_path
        self.window_frames = int(window_frames)
        self.monitoring = monitoring or MonitoringSession()
        self.obb_model = YOLO(obb_model_path)
        validate_head_tail_obb_model(self.obb_model)
        self.hbb_model = YOLO(hbb_model_path)
        self._display_ids: dict[int, int] = {}
        self._next_display_id = 1

    def _display_track_id(self, raw_track_id: int | None) -> int | None:
        if raw_track_id is None:
            return None
        raw_track_id = int(raw_track_id)
        if raw_track_id not in self._display_ids:
            self._display_ids[raw_track_id] = self._next_display_id
            self._next_display_id += 1
        return self._display_ids[raw_track_id]

    def _detect_obb(self, frame: np.ndarray, tracker: str | None, conf: float, iou: float):
        kwargs = {"conf": conf, "iou": iou, "imgsz": IMGSZ_OBB, "verbose": False, "persist": True}
        kwargs["tracker"] = tracker or "bytetrack.yaml"
        return self.obb_model.track(frame, **kwargs)[0]

    def _detect_male_line(self, crop: np.ndarray, conf: float) -> tuple[bool, float, list[tuple[int, int, int, int]]]:
        result = self.hbb_model.predict(crop, imgsz=IMGSZ_HBB, verbose=False)[0]
        boxes: list[tuple[int, int, int, int]] = []
        best_conf = 0.0
        if result.boxes is None:
            return False, best_conf, boxes
        for box in result.boxes:
            class_index = int(box.cls[0])
            name = result.names[class_index]
            score = float(box.conf[0])
            if name != "male_line" or score < conf:
                continue
            x1, y1, x2, y2 = [int(round(v)) for v in box.xyxy[0].cpu().numpy().tolist()]
            boxes.append((x1, y1, x2, y2))
            best_conf = max(best_conf, score)
        return bool(boxes), best_conf, boxes

    @staticmethod
    def _orient_head_left_with_flip(
        crop: np.ndarray,
        matrix: np.ndarray,
        head_centers: list[tuple[float, float]],
        tail_centers: list[tuple[float, float]],
    ) -> tuple[np.ndarray | None, str, bool]:
        if len(head_centers) == 1:
            flip = transform_x(head_centers[0], matrix) > crop.shape[1] / 2
            source = "head"
        elif len(tail_centers) == 1:
            flip = transform_x(tail_centers[0], matrix) < crop.shape[1] / 2
            source = "tail"
        else:
            return None, "ambiguous_head_and_tail", False
        return (cv2.flip(crop, 1) if flip else crop), source, flip

    @staticmethod
    def _male_boxes_to_frame_polygons(
        male_boxes: list[tuple[int, int, int, int]],
        oriented_shape: tuple[int, int, int],
        matrix: np.ndarray,
        flipped: bool,
    ) -> list[np.ndarray]:
        if not male_boxes:
            return []
        inverse_matrix = np.linalg.inv(matrix)
        width = oriented_shape[1]
        polygons = []
        for x1, y1, x2, y2 in male_boxes:
            corners = np.array(
                [[[x1, y1], [x2, y1], [x2, y2], [x1, y2]]],
                dtype=np.float32,
            )
            if flipped:
                corners[:, :, 0] = width - 1 - corners[:, :, 0]
            frame_corners = cv2.perspectiveTransform(corners, inverse_matrix)[0]
            polygons.append(frame_corners.astype(np.int32))
        return polygons

    def _process_frame(
        self,
        frame: np.ndarray,
        frame_index: int,
        fps: float,
        tracker: str | None,
        obb_conf: float,
        obb_iou: float,
        hbb_conf: float,
        vote_state: SlidingVoteState,
    ) -> tuple[list[dict], list[dict], np.ndarray, list[dict]]:
        result = self._detect_obb(frame, tracker, obb_conf, obb_iou)
        shrimps, heads, tails = split_head_tail_rows(obb_rows(result))
        annotated = frame.copy()
        records = []
        windows = []
        debug_items = []

        for shrimp in shrimps:
            polygon = shrimp["polygon"]
            crop, matrix = rectify_shrimp(frame, polygon)
            head_centers = associated_centers(heads, polygon)
            tail_centers = associated_centers(tails, polygon)
            oriented, direction_source, flipped = self._orient_head_left_with_flip(crop, matrix, head_centers, tail_centers)
            if oriented is None:
                continue

            raw_track_id = shrimp["track_id"]
            track_id = self._display_track_id(raw_track_id)
            if track_id is None:
                continue

            male_detected, male_conf, male_boxes = self._detect_male_line(oriented, hbb_conf)
            label, male_rate, male_hits, denominator, male_hit, window_ready = vote_state.update(track_id, frame_index, male_detected)
            label_for_display = label if window_ready else f"{label}*"
            record = {
                "frame": frame_index,
                "time_sec": round(frame_index / fps, 3),
                "track_id": track_id,
                "raw_tracker_id": "" if raw_track_id is None else raw_track_id,
                "label": label if window_ready else "",
                "display_label": label,
                "window_ready": int(window_ready),
                "male_line_detected": int(male_detected),
                "male_line_grace_hit": int(male_hit and not male_detected),
                "male_conf": round(male_conf, 6),
                "window_male_hits": male_hits,
                "window_length": denominator,
                "window_male_rate": round(male_rate, 6),
                "obb_confidence": round(shrimp["confidence"], 6),
                "head_count": len(head_centers),
                "tail_count": len(tail_centers),
                "direction_source": direction_source,
            }
            record.update(self.monitoring.measure(polygon, frame.shape))
            records.append(record)
            if window_ready:
                windows.append(
                    {
                        "track_id": track_id,
                        "window_start_frame": frame_index - self.window_frames + 1,
                        "window_end_frame": frame_index,
                        "window_length": denominator,
                        "male_hits": male_hits,
                        "male_rate": round(male_rate, 6),
                        "label": label,
                    }
                )
            debug_items.append({"crop": oriented, "track_id": track_id, "label": label_for_display, "male_rate": male_rate, "male_boxes": male_boxes})

            color = self._label_color(label)
            cv2.polylines(annotated, [polygon.astype(np.int32)], True, color, 2)
            for male_polygon in self._male_boxes_to_frame_polygons(male_boxes, oriented.shape, matrix, flipped):
                cv2.polylines(annotated, [male_polygon], True, (0, 255, 255), 2, cv2.LINE_AA)
            anchor = tuple(polygon[np.argmin(polygon[:, 1])].astype(int))
            cv2.putText(
                annotated,
                f"ID {track_id} {label_for_display} {male_rate * 100:.0f}%",
                anchor,
                cv2.FONT_HERSHEY_SIMPLEX,
                0.75,
                color,
                2,
                cv2.LINE_AA,
            )
            self.monitoring.annotate_measurement(annotated, record, anchor)
        self.monitoring.annotate_water(annotated)
        return records, windows, annotated, debug_items

    @staticmethod
    def _label_color(label: str) -> tuple[int, int, int]:
        if label == "M":
            return (255, 120, 40)
        if label == "obs":
            return (150, 150, 150)
        return (0, 200, 0)

    @classmethod
    def _make_debug_view(cls, items: list[dict], frame_index: int) -> np.ndarray:
        tile_width, tile_height = 480, 180
        tiles = []
        for item in items:
            marked = item["crop"].copy()
            for x1, y1, x2, y2 in item["male_boxes"]:
                cv2.rectangle(marked, (x1, y1), (x2, y2), (0, 255, 255), 2)
            height, width = marked.shape[:2]
            scale = min(tile_width / max(1, width), (tile_height - 42) / max(1, height))
            resized = cv2.resize(
                marked,
                (max(1, int(round(width * scale))), max(1, int(round(height * scale)))),
                interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR,
            )
            tile = np.full((tile_height, tile_width, 3), 28, dtype=np.uint8)
            y = 38 + max(0, (tile_height - 38 - resized.shape[0]) // 2)
            x = max(0, (tile_width - resized.shape[1]) // 2)
            tile[y : y + resized.shape[0], x : x + resized.shape[1]] = resized
            text = f"ID {item['track_id']} | {item['label']} {item['male_rate'] * 100:.0f}%"
            cv2.putText(tile, text, (8, 27), cv2.FONT_HERSHEY_SIMPLEX, 0.78, (235, 235, 235), 2, cv2.LINE_AA)
            tiles.append(tile)
        if not tiles:
            empty = np.full((tile_height, tile_width, 3), 28, dtype=np.uint8)
            cv2.putText(empty, f"Frame {frame_index}: no valid shrimp crops", (20, tile_height // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (220, 220, 220), 1, cv2.LINE_AA)
            return empty
        return cv2.vconcat(tiles)

    def run(
        self,
        video: str,
        output_root: str = "general_track/exports/run_track",
        tracker: str | None = "bytetrack.yaml",
        obb_conf: float = 0.5,
        obb_iou: float = 0.3,
        hbb_conf: float = HBB_CONF,
        max_frames: int | None = None,
        preview: bool = False,
        preview_only: bool = False,
        debug: bool = False,
        gt: str | None = None,
        number_of_shrimps: int | None = None,
    ) -> dict:
        self.monitoring.reset()
        source = int(video) if str(video).strip().isdigit() else video
        capture = cv2.VideoCapture(source)
        if not capture.isOpened():
            capture.release()
            raise FileNotFoundError(f"Cannot open video or camera: {video}")
        writer = None
        preview = preview or preview_only
        skipped_turbid = False
        try:
            fps = float(capture.get(cv2.CAP_PROP_FPS)) or 30.0
            frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
            source_name = f"camera_{video}" if isinstance(source, int) else Path(video).stem
            debug_enabled = bool(debug)
            self._display_ids = {}
            self._next_display_id = 1

            run_dir = Path(output_root) / source_name / datetime.now().strftime("%Y%m%d_%H%M%S")
            if not preview_only:
                run_dir.mkdir(parents=True, exist_ok=True)
            video_path = run_dir / "result.mp4"
            detections_path = run_dir / "detections.csv"
            windows_path = run_dir / "sliding_windows.csv"
            per_shrimp_path = run_dir / "per_shrimp.csv"
            video_info_path = run_dir / "video_info.csv"
            vote_summary_path = run_dir / "window_vote_summary.csv"

            vote_state = SlidingVoteState(self.window_frames, grace_frames=max(1, int(round(fps))))
            all_records: list[dict] = []
            all_windows: list[dict] = []
            fixed_video_size = None
            frame_index = 0
            processed_frames = 0
            progress_total = min(frame_count, max_frames) if max_frames and frame_count > 0 else (frame_count or None)

            with tqdm(total=progress_total, desc="OBB+HBB tracking", unit="frame", ncols=85) as progress:
                while max_frames is None or frame_index < max_frames:
                    ok, frame = capture.read()
                    if not ok:
                        break
                    if frame_index == 0 and not self.monitoring.check_frame(frame, frame_index, fps):
                        skipped_turbid = True
                        break
                    processed_frames += 1
                    records, windows, annotated, debug_items = self._process_frame(
                        frame, frame_index, fps, tracker, obb_conf, obb_iou, hbb_conf, vote_state
                    )
                    all_records.extend(records)
                    all_windows.extend(windows)

                    export_frame = annotated
                    if debug:
                        export_frame = combine_preview(annotated, self._make_debug_view(debug_items, frame_index))
                        if fixed_video_size is None:
                            fixed_video_size = debug_video_size(export_frame)
                        export_frame = letterbox(export_frame, fixed_video_size)
                    if writer is None and not preview_only:
                        height, width = export_frame.shape[:2]
                        writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
                        if not writer.isOpened():
                            raise RuntimeError(f"Unable to create result video: {video_path}")
                    if writer is not None:
                        writer.write(export_frame)

                    if preview:
                        preview_image = annotated
                        if debug_enabled:
                            preview_image = combine_preview(annotated, self._make_debug_view(debug_items, frame_index))
                        preview_image = fit_preview_to_screen(preview_image)
                        key = show_preview_or_raise("Shrimp run_track | D: debug | Q/Esc: quit", preview_image)
                        if key in {ord("d"), ord("D")}:
                            debug_enabled = not debug_enabled
                        elif key in {ord("q"), 27}:
                            break

                    frame_index += 1
                    progress.update(1)


            skip_status = {"status": "skipped_turbid", "monitoring_status": "skipped_turbid", "skipped": True} if skipped_turbid else {}
            if preview_only:
                return {"output_dir": "", "video": "", "detections": "", "sliding_windows": "", "per_shrimp": "", **skip_status}

            write_csv(detections_path, all_records)
            write_csv(windows_path, all_windows)
            per_shrimp = self._summarize(all_records, gt=gt)
            write_csv(per_shrimp_path, per_shrimp)
            video_info_rows = self._video_info_rows(source_name, gt, number_of_shrimps, frame_count, fps, self.window_frames)
            vote_summary_rows = self._window_vote_summary_rows(source_name, gt, all_windows)
            if skipped_turbid:
                video_info_rows[0]["Valid Windows"] = 0
                vote_summary_rows[0]["Final Prediction"] = ""
                vote_summary_rows[0]["Status"] = "skipped_turbid"
            write_csv(video_info_path, video_info_rows)
            write_csv(vote_summary_path, vote_summary_rows)
            return {
                "output_dir": str(run_dir),
                "video": str(video_path) if writer is not None else "",
                "detections": str(detections_path),
                "sliding_windows": str(windows_path),
                "per_shrimp": str(per_shrimp_path),
                "video_info": str(video_info_path),
                "window_vote_summary": str(vote_summary_path),
                **self.monitoring.export(run_dir),
                **skip_status,
            }
        finally:
            capture.release()
            if writer is not None:
                writer.release()
            if preview:
                cv2.destroyAllWindows()

    @staticmethod
    def _normalize_gt(gt: str | None) -> str:
        if gt is None:
            return ""
        value = str(gt).strip().lower()
        if value in {"m", "male"}:
            return "Male"
        if value in {"f", "female"}:
            return "Female"
        raise ValueError("gt must be Male or Female")

    @staticmethod
    def _final_from_counts(male: int, female: int, obs: int) -> str:
        values = {"Male": male, "Female": female, "Obs": obs}
        return max(values, key=lambda label: (values[label], label == "Male", label == "Female"))

    @classmethod
    def _video_info_rows(
        cls,
        video_name: str,
        gt: str | None,
        number_of_shrimps: int | None,
        total_frames: int,
        fps: float,
        window_frames: int,
    ) -> list[dict]:
        duration = total_frames / max(float(fps), 1e-9)
        return [
            {
                "Video": video_name,
                "Ground Truth": cls._normalize_gt(gt),
                "Number of Shrimps": "" if number_of_shrimps is None else int(number_of_shrimps),
                "Duration": round(duration, 3),
                "FPS": round(float(fps), 6),
                "Total Frames": int(total_frames),
                "Valid Windows": max(0, int(total_frames) - int(window_frames) + 1),
            }
        ]

    @classmethod
    def _window_vote_summary_rows(cls, video_name: str, gt: str | None, windows: list[dict]) -> list[dict]:
        labels = Counter(item["label"] for item in windows)
        male = labels["M"]
        female = labels["F"]
        obs = labels["obs"]
        return [
            {
                "Video": video_name,
                "Ground Truth": cls._normalize_gt(gt),
                "Total Windows": len(windows),
                "Male Windows": male,
                "Female Windows": female,
                "Observation Windows": obs,
                "Final Prediction": cls._final_from_counts(male, female, obs),
            }
        ]

    @classmethod
    def _summarize(cls, records: list[dict], gt: str | None = None) -> list[dict]:
        gt_label = cls._normalize_gt(gt)
        grouped = defaultdict(list)
        for record in records:
            grouped[int(record["track_id"])].append(record)
        rows = []
        for track_id, items in sorted(grouped.items()):
            ready_items = [item for item in items if item.get("window_ready") == 1]
            labels = Counter(item["label"] for item in ready_items)
            last = ready_items[-1] if ready_items else items[-1]
            row = {
                "track_id": track_id,
                "final_label": last["label"],
                "observations": len(items),
                "valid_windows": len(ready_items),
                "female_votes": labels["F"],
                "obs_votes": labels["obs"],
                "male_votes": labels["M"],
                "last_window_male_rate": last["window_male_rate"],
                "last_window_male_hits": last["window_male_hits"],
                "last_window_length": last["window_length"],
            }
            if gt_label:
                row["GT"] = gt_label
            row.update(summarize_measurements(items))
            rows.append(row)
        return rows
