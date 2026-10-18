from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import time

import cv2
import numpy as np
from tqdm import tqdm

from shrimp_monitoring import MonitoringSession, summarize_measurements

from .head_tail_common import associated_centers, crop_classifier_region, orient_head_left, rectify_shrimp, split_head_tail_rows
from .obb_track import detect_obb_rows, reset_obb_tracking
from .output import RunOutput
from .preview_smoothing import PreviewSmoothing
from . import visualization


class HeadTailShrimpAnalyzer:
    def __init__(self, obb_model, classifier, monitoring=None, cnn_threshold=None, imgsz=640):
        if cnn_threshold is not None:
            cnn_threshold = float(cnn_threshold)
            if not np.isfinite(cnn_threshold) or not 0 <= cnn_threshold <= 1:
                raise ValueError("CNN threshold must be a finite value between 0 and 1.")
        self.cnn_threshold = cnn_threshold
        self.obb_model = obb_model
        self.classifier = classifier
        self.monitoring = monitoring if monitoring is not None else MonitoringSession()
        self.imgsz = imgsz
        self._shrimp_display_ids = {}
        self._next_display_id = 1

    def _display_track_id(self, raw_track_id):
        if raw_track_id is None:
            return None
        raw_track_id = int(raw_track_id)
        if raw_track_id not in self._shrimp_display_ids:
            self._shrimp_display_ids[raw_track_id] = self._next_display_id
            self._next_display_id += 1
        return self._shrimp_display_ids[raw_track_id]

    def _detect(self, frame, tracker, conf, iou):
        return detect_obb_rows(self.obb_model, frame, tracker, conf=conf, iou=iou, imgsz=self.imgsz)

    def _process_frame(
        self, frame: np.ndarray, rows, frame_index: int, fps: float
    ) -> tuple[list[dict], list[dict]]:
        shrimps, heads, tails = split_head_tail_rows(rows)
        records = []
        debug_items = []

        for shrimp in shrimps:
            polygon = shrimp["polygon"]
            inside_heads = associated_centers(heads, polygon)
            inside_tails = associated_centers(tails, polygon)
            crop, matrix = rectify_shrimp(frame, polygon)
            oriented, orientation_source = orient_head_left(crop, matrix, inside_heads, inside_tails)
            if oriented is None:
                continue
            classifier_crop = crop_classifier_region(oriented)
            label, confidence, male_probability = self.classifier.predict(classifier_crop)
            if self.cnn_threshold is not None:
                label = "male" if male_probability >= self.cnn_threshold else "female"
                confidence = male_probability if label == "male" else 1.0 - male_probability
            raw_track_id = shrimp["track_id"]
            track_id = self._display_track_id(raw_track_id)
            debug_items.append(
                {
                    "crop": oriented,
                    "polygon": polygon,
                    "classifier_crop": classifier_crop,
                    "track_id": track_id,
                    "label": label,
                    "confidence": confidence,
                    "male_probability": male_probability,
                    "orientation_source": orientation_source,
                }
            )
            records.append(
                {
                    "frame": frame_index,
                    "time_sec": round(frame_index / fps, 3),
                    "track_id": "" if track_id is None else track_id,
                    "raw_tracker_id": "" if raw_track_id is None else raw_track_id,
                    "label": label,
                    "confidence": round(confidence, 6),
                    "male_probability": round(male_probability, 6),
                    "obb_confidence": round(shrimp["confidence"], 6),
                    "head_count": len(inside_heads),
                    "tail_count": len(inside_tails),
                    "orientation_source": orientation_source,
                    **self.monitoring.measure(polygon, frame.shape),
                }
            )
            if self.cnn_threshold is not None:
                records[-1]["cnn_threshold"] = self.cnn_threshold
        return records, debug_items

    def run(self, video, output_root="general_track/exports/run_track", tracker="bytetrack.yaml",
            conf=0.6, iou=0.3, max_frames=None, preview=False, preview_only=False, debug=False, save_crops=False):
        self.monitoring.reset()
        reset_obb_tracking(self.obb_model)
        self._shrimp_display_ids = {}
        self._next_display_id = 1
        source = int(video) if str(video).strip().isdigit() else video
        capture = cv2.VideoCapture(source)
        if not capture.isOpened():
            capture.release()
            raise FileNotFoundError(f"Cannot open video or camera: {video}")
        output = None
        preview = preview or preview_only
        preview_smoothing = PreviewSmoothing(self.cnn_threshold)
        skipped_turbid = False
        try:
            fps = float(capture.get(cv2.CAP_PROP_FPS))
            if not np.isfinite(fps) or fps <= 0:
                fps = 30.0
            frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
            source_name = f"camera_{video}" if isinstance(source, int) else Path(video).stem
            if not preview_only:
                output = RunOutput(output_root, source_name, fps, save_crops)
            debug_enabled = bool(debug)
            debug_video_size = None
            all_records = []
            frame_index = 0
            progress_total = min(frame_count, max_frames) if max_frames and frame_count > 0 else (frame_count or None)
            with tqdm(total=progress_total, desc="Head/tail tracking", unit="frame", ncols=85) as progress:
                while max_frames is None or frame_index < max_frames:
                    ok, frame = capture.read()
                    if not ok:
                        break
                    if frame_index == 0 and not self.monitoring.check_frame(frame, frame_index, fps):
                        skipped_turbid = True
                        break
                    rows = self._detect(frame, tracker, conf, iou)
                    records, items = self._process_frame(frame, rows, frame_index, fps)
                    all_records.extend(records)
                    annotated = visualization.render_frame(frame, records, items, self.monitoring)
                    if output is not None:
                        export_frame = annotated
                        if debug:
                            export_frame = visualization.combine_preview(annotated, visualization.make_debug_view(items, frame_index))
                            if debug_video_size is None:
                                debug_video_size = visualization.debug_video_size(export_frame)
                            export_frame = visualization.letterbox(export_frame, debug_video_size)
                        output.write(export_frame, items, frame_index)
                    if preview:
                        preview_items = preview_smoothing.update(items, time.monotonic())
                        preview_image = visualization.render_frame(frame, records, preview_items, self.monitoring)
                        if debug_enabled:
                            preview_image = visualization.combine_preview(preview_image, visualization.make_debug_view(preview_items, frame_index))
                        preview_image = visualization.fit_preview_to_screen(preview_image)
                        key = visualization.show_preview_or_raise("Head-tail shrimp tracking | D: debug | Q/Esc: quit", preview_image)
                        if key in {ord("d"), ord("D")}:
                            debug_enabled = not debug_enabled
                        elif key in {ord("q"), 27}:
                            break
                    frame_index += 1
                    progress.update(1)
            skip_status = {"status": "skipped_turbid", "monitoring_status": "skipped_turbid", "skipped": True} if skipped_turbid else {}
            if output is None:
                return {"output_dir": "", "video": "", "detections": "", "per_shrimp": "", **skip_status}
            return {**output.finish(all_records, self._summarize(all_records), self.monitoring), **skip_status}
        finally:
            capture.release()
            if output is not None:
                output.close()
            if preview:
                cv2.destroyAllWindows()

    @staticmethod
    def _summarize(records: list[dict]) -> list[dict]:
        grouped = defaultdict(list)
        for record in records:
            if record["track_id"] != "":
                grouped[int(record["track_id"])].append(record)
        summaries = []
        for track_id, items in sorted(grouped.items()):
            votes = Counter(item["label"] for item in items)
            label = max(votes, key=lambda name: (votes[name], name == "male"))
            summaries.append(
                {
                    "track_id": track_id,
                    "final_label": label,
                    "observations": len(items),
                    "male_votes": votes["male"],
                    "female_votes": votes["female"],
                    "mean_male_probability": round(float(np.mean([item["male_probability"] for item in items])), 6),
                    **summarize_measurements(items),
                }
            )
        return summaries


def __getattr__(name):
    if name in {"ResNet50FPNClassifier", "ShrimpSexClassifier", "YoloShrimpSexClassifier", "load_sex_classifier"}:
        from . import sex_classifier
        return getattr(sex_classifier, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
