from __future__ import annotations

import csv
import pickle
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import torch
from torchvision import models
from tqdm import tqdm
from ultralytics import YOLO

from .config import (
    IMGSZ_OBB,
    MODEL_HEAD_TAIL_OBB_PATH,
    MODEL_SEX_CLASSIFIER_PATH,
)
from .obb_track import extract_obb_track_id


REQUIRED_OBB_CLASSES = {"shrimp", "shrimp_head", "shrimp_tail"}
REQUIRED_SEX_CLASSES = {"female", "male"}


class ShrimpSexClassifier:
    """Load the female/male ResNet18 checkpoint used by the training pipeline."""

    def __init__(self, model_path: str, device: str | None = None) -> None:
        self.path = Path(model_path)
        if not self.path.exists():
            raise FileNotFoundError(f"Sex classifier not found: {self.path}")
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        checkpoint = torch.load(self.path, map_location=self.device)
        self.class_to_idx = checkpoint["class_to_idx"]
        if set(self.class_to_idx) != REQUIRED_SEX_CLASSES:
            raise ValueError(f"Expected CNN classes {sorted(REQUIRED_SEX_CLASSES)}, got {self.class_to_idx}")
        self.architecture = str(checkpoint.get("architecture", checkpoint.get("model", "resnet18"))).lower()

        self.image_size = int(checkpoint.get("image_size", 128))
        self.grayscale = bool(checkpoint.get("grayscale", False))
        if self.architecture == "resnet18":
            model = models.resnet18(weights=None)
        elif self.architecture == "resnet34":
            model = models.resnet34(weights=None)
        elif self.architecture == "resnet50":
            model = models.resnet50(weights=None)
        else:
            raise ValueError(f"Unsupported classifier architecture: {self.architecture}")
        state_dict = checkpoint["model_state"]
        if "fc.1.weight" in state_dict:
            model.fc = torch.nn.Sequential(
                torch.nn.Dropout(float(checkpoint.get("dropout", 0.5))),
                torch.nn.Linear(model.fc.in_features, len(self.class_to_idx)),
            )
        elif "fc.weight" in state_dict:
            model.fc = torch.nn.Linear(model.fc.in_features, len(self.class_to_idx))
        else:
            raise ValueError("Unsupported classifier head format: expected fc.weight or fc.1.weight")
        model.load_state_dict(state_dict)
        self.model = model.to(self.device).eval()
        self.labels = {index: name for name, index in self.class_to_idx.items()}
        self.mean = torch.tensor([0.485, 0.456, 0.406], device=self.device).view(1, 3, 1, 1)
        self.std = torch.tensor([0.229, 0.224, 0.225], device=self.device).view(1, 3, 1, 1)

    def predict(self, crop_bgr: np.ndarray) -> tuple[str, float, float]:
        if crop_bgr is None or crop_bgr.size == 0:
            raise ValueError("Cannot classify an empty crop")
        image = cv2.resize(crop_bgr, (self.image_size, self.image_size), interpolation=cv2.INTER_AREA)
        if self.grayscale:
            image = cv2.cvtColor(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        tensor = torch.from_numpy(rgb).permute(2, 0, 1).unsqueeze(0).to(self.device)
        tensor = (tensor - self.mean) / self.std
        with torch.no_grad():
            probabilities = torch.softmax(self.model(tensor), dim=1)[0]
        index = int(torch.argmax(probabilities).item())
        return self.labels[index], float(probabilities[index]), float(probabilities[self.class_to_idx["male"]])


class YoloShrimpSexClassifier:
    """Female/male classifier backed by an Ultralytics YOLO classification model."""

    def __init__(self, model_path: str) -> None:
        self.path = Path(model_path)
        if not self.path.exists():
            raise FileNotFoundError(f"YOLO sex classifier not found: {self.path}")
        self.model = YOLO(str(self.path))
        if self.model.task != "classify":
            raise ValueError(f"Expected a YOLO classification model, got task: {self.model.task}")
        self.class_to_idx = {name: int(index) for index, name in self.model.names.items()}
        if set(self.class_to_idx) != REQUIRED_SEX_CLASSES:
            raise ValueError(f"Expected YOLO classes {sorted(REQUIRED_SEX_CLASSES)}, got {self.class_to_idx}")
        self.architecture = "yolo-classify"
        model_args = getattr(self.model.model, "args", {}) or {}
        self.image_size = int(model_args.get("imgsz", 224))

    def predict(self, crop_bgr: np.ndarray) -> tuple[str, float, float]:
        if crop_bgr is None or crop_bgr.size == 0:
            raise ValueError("Cannot classify an empty crop")
        result = self.model.predict(crop_bgr, imgsz=self.image_size, verbose=False)[0]
        if result.probs is None:
            raise ValueError("YOLO classification model returned no probabilities")
        probabilities = result.probs.data.detach().cpu().numpy()
        index = int(np.argmax(probabilities))
        label = self.model.names[index]
        return label, float(probabilities[index]), float(probabilities[self.class_to_idx["male"]])


def load_sex_classifier(model_path: str):
    """Load a custom ResNet checkpoint or fall back to Ultralytics classification."""
    try:
        return ShrimpSexClassifier(model_path)
    except (KeyError, TypeError, RuntimeError, ValueError, pickle.UnpicklingError) as resnet_error:
        try:
            return YoloShrimpSexClassifier(model_path)
        except Exception:
            raise resnet_error


def _order_points(points: np.ndarray) -> np.ndarray:
    """Return minAreaRect vertices in top-left, top-right, bottom-right, bottom-left order."""
    points = np.asarray(points, dtype=np.float32).reshape(4, 2)
    ordered = np.zeros((4, 2), dtype=np.float32)
    sums = points.sum(axis=1)
    differences = np.diff(points, axis=1).reshape(-1)
    ordered[0] = points[np.argmin(sums)]
    ordered[2] = points[np.argmax(sums)]
    ordered[1] = points[np.argmin(differences)]
    ordered[3] = points[np.argmax(differences)]
    return ordered


def rectify_shrimp(frame: np.ndarray, shrimp_polygon: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Rectify a shrimp OBB using minAreaRect, getPerspectiveTransform and warpPerspective."""
    polygon = np.asarray(shrimp_polygon, dtype=np.float32).reshape(-1, 2)
    rect = cv2.minAreaRect(polygon)
    source = _order_points(cv2.boxPoints(rect))
    width = max(1, int(round(max(np.linalg.norm(source[1] - source[0]), np.linalg.norm(source[2] - source[3])))))
    height = max(1, int(round(max(np.linalg.norm(source[3] - source[0]), np.linalg.norm(source[2] - source[1])))))
    destination = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype=np.float32)
    matrix = cv2.getPerspectiveTransform(source, destination)
    crop = cv2.warpPerspective(frame, matrix, (width, height))
    if crop.shape[0] > crop.shape[1]:
        old_height = crop.shape[0]
        crop = cv2.rotate(crop, cv2.ROTATE_90_CLOCKWISE)
        rotate_matrix = np.array([[0, -1, old_height - 1], [1, 0, 0], [0, 0, 1]], dtype=np.float32)
        matrix = rotate_matrix @ matrix
    return crop, matrix


def _point_in_polygon(center: tuple[float, float], polygon: np.ndarray) -> bool:
    contour = np.asarray(polygon, dtype=np.float32).reshape(-1, 1, 2)
    return cv2.pointPolygonTest(contour, (float(center[0]), float(center[1])), False) >= 0


def _transform_x(center: tuple[float, float], matrix: np.ndarray) -> float:
    point = np.array([[[center[0], center[1]]]], dtype=np.float32)
    return float(cv2.perspectiveTransform(point, matrix)[0, 0, 0])


def orient_head_left(
    crop: np.ndarray,
    matrix: np.ndarray,
    head_centers: list[tuple[float, float]],
    tail_centers: list[tuple[float, float]],
) -> tuple[np.ndarray | None, str]:
    """Prefer one head; fall back to one tail. Reject only when neither side is unique."""
    if len(head_centers) == 1:
        flip = _transform_x(head_centers[0], matrix) > crop.shape[1] / 2
        source = "head"
    elif len(tail_centers) == 1:
        flip = _transform_x(tail_centers[0], matrix) < crop.shape[1] / 2
        source = "tail"
    else:
        return None, "ambiguous_head_and_tail"
    return (cv2.flip(crop, 1) if flip else crop), source


def crop_classifier_region(horizontal_crop: np.ndarray) -> np.ndarray:
    """Crop the abdomen region sent to the female/male classifier."""
    horizontal_height, total_length = horizontal_crop.shape[:2]
    left = total_length // 4
    right = total_length - total_length // 2
    top = horizontal_height // 5
    bottom = horizontal_height - horizontal_height // 5
    if right <= left:
        raise ValueError(f"Shrimp crop is too short: {total_length}px")
    if bottom <= top:
        raise ValueError(f"Shrimp crop is too low: {horizontal_height}px")
    return horizontal_crop[top:bottom, left:right].copy()


def _obb_rows(result) -> list[dict]:
    rows = []
    if result.obb is None:
        return rows
    for obb in result.obb:
        class_index = int(obb.cls.cpu().numpy()[0])
        polygon = obb.xyxyxyxy.cpu().numpy()[0].astype(np.float32)
        rows.append(
            {
                "class_name": result.names[class_index],
                "polygon": polygon,
                "center": tuple(np.mean(polygon, axis=0).tolist()),
                "confidence": float(obb.conf.cpu().numpy()[0]),
                "track_id": extract_obb_track_id(obb),
            }
        )
    return rows


class HeadTailShrimpAnalyzer:
    def __init__(
        self,
        obb_model_path: str = MODEL_HEAD_TAIL_OBB_PATH,
        cnn_model_path: str = MODEL_SEX_CLASSIFIER_PATH,
    ) -> None:
        self.obb_model_path = obb_model_path
        self.cnn_model_path = cnn_model_path
        self.obb_model = YOLO(obb_model_path)
        names = set(self.obb_model.names.values())
        missing = REQUIRED_OBB_CLASSES - names
        if missing:
            raise ValueError(f"OBB model is missing classes: {sorted(missing)}; got {sorted(names)}")
        self.classifier = load_sex_classifier(cnn_model_path)
        self._shrimp_display_ids: dict[int, int] = {}
        self._next_display_id = 1

    def _display_track_id(self, raw_track_id: int | None) -> int | None:
        """Map shared multi-class ByteTrack IDs to shrimp-only sequential IDs."""
        if raw_track_id is None:
            return None
        raw_track_id = int(raw_track_id)
        if raw_track_id not in self._shrimp_display_ids:
            self._shrimp_display_ids[raw_track_id] = self._next_display_id
            self._next_display_id += 1
        return self._shrimp_display_ids[raw_track_id]

    def _detect(self, frame: np.ndarray, tracker: str | None, conf: float, iou: float):
        kwargs = {"conf": conf, "iou": iou, "imgsz": IMGSZ_OBB, "verbose": False, "persist": True}
        kwargs["tracker"] = tracker or "bytetrack.yaml"
        return self.obb_model.track(frame, **kwargs)[0]

    def _process_frame(
        self, frame: np.ndarray, result, frame_index: int, fps: float
    ) -> tuple[list[dict], np.ndarray, list[dict]]:
        rows = _obb_rows(result)
        shrimps = [row for row in rows if row["class_name"] == "shrimp"]
        heads = [row for row in rows if row["class_name"] == "shrimp_head"]
        tails = [row for row in rows if row["class_name"] == "shrimp_tail"]
        annotated = frame.copy()
        records = []
        debug_items = []

        for shrimp in shrimps:
            polygon = shrimp["polygon"]
            inside_heads = [item["center"] for item in heads if _point_in_polygon(item["center"], polygon)]
            inside_tails = [item["center"] for item in tails if _point_in_polygon(item["center"], polygon)]
            crop, matrix = rectify_shrimp(frame, polygon)
            oriented, orientation_source = orient_head_left(crop, matrix, inside_heads, inside_tails)
            if oriented is None:
                continue
            classifier_crop = crop_classifier_region(oriented)
            label, confidence, male_probability = self.classifier.predict(classifier_crop)
            raw_track_id = shrimp["track_id"]
            track_id = self._display_track_id(raw_track_id)
            debug_items.append(
                {
                    "crop": oriented,
                    "track_id": track_id,
                    "label": label,
                    "confidence": confidence,
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
                    "classifier_crop": classifier_crop,
                }
            )
            color = (255, 120, 40) if label == "male" else (0, 200, 0)
            cv2.polylines(annotated, [polygon.astype(np.int32)], True, color, 2)
            anchor = tuple(polygon[np.argmin(polygon[:, 1])].astype(int))
            identity = f"ID {track_id}" if track_id is not None else "ID ?"
            cv2.putText(
                annotated,
                f"{identity} {label} {confidence:.2f}",
                anchor,
                cv2.FONT_HERSHEY_SIMPLEX,
                0.75,
                color,
                2,
                cv2.LINE_AA,
            )
        return records, annotated, debug_items

    @staticmethod
    def _make_debug_view(items: list[dict], frame_index: int) -> np.ndarray:
        """Build a tiled view with the exact ResNet18 abdomen interval highlighted."""
        tile_width, tile_height = 480, 180
        tiles = []
        for item in items:
            crop = item["crop"]
            height, total_length = crop.shape[:2]
            left = total_length // 4
            right = total_length - total_length // 2
            top = height // 5
            bottom = height - height // 5
            marked = crop.copy()
            overlay = marked.copy()
            cv2.rectangle(overlay, (left, top), (max(left, right - 1), max(top, bottom - 1)), (0, 255, 255), -1)
            marked = cv2.addWeighted(overlay, 0.28, marked, 0.72, 0)
            cv2.rectangle(marked, (left, top), (max(left, right - 1), max(top, bottom - 1)), (0, 255, 255), 2)

            scale = min(tile_width / max(1, total_length), (tile_height - 42) / max(1, height))
            resized = cv2.resize(
                marked,
                (max(1, int(round(total_length * scale))), max(1, int(round(height * scale)))),
                interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR,
            )
            tile = np.full((tile_height, tile_width, 3), 28, dtype=np.uint8)
            y = 38 + max(0, (tile_height - 38 - resized.shape[0]) // 2)
            x = max(0, (tile_width - resized.shape[1]) // 2)
            tile[y : y + resized.shape[0], x : x + resized.shape[1]] = resized
            identity = item["track_id"] if item["track_id"] is not None else "?"
            text = f"ID {identity} | {item['label']} {item['confidence']:.2f}"
            cv2.putText(tile, text, (8, 27), cv2.FONT_HERSHEY_SIMPLEX, 0.78, (235, 235, 235), 2, cv2.LINE_AA)
            tiles.append(tile)

        if not tiles:
            empty = np.full((tile_height, tile_width, 3), 28, dtype=np.uint8)
            cv2.putText(
                empty,
                f"Frame {frame_index}: no valid shrimp crops",
                (20, tile_height // 2),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (220, 220, 220),
                1,
                cv2.LINE_AA,
            )
            return empty

        return cv2.vconcat(tiles)

    @staticmethod
    def _combine_preview(main_view: np.ndarray, debug_view: np.ndarray) -> np.ndarray:
        """Attach a large, vertically stacked debug panel to the main preview."""
        main_height, main_width = main_view.shape[:2]
        panel_width = min(480, max(360, main_width // 3))
        scale = panel_width / max(1, debug_view.shape[1])
        resized_width = panel_width
        resized_height = max(1, int(round(debug_view.shape[0] * scale)))
        interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
        resized_debug = cv2.resize(debug_view, (resized_width, resized_height), interpolation=interpolation)
        canvas_height = max(main_height, resized_height)
        main_panel = np.full((canvas_height, main_width, 3), 28, dtype=np.uint8)
        debug_panel = np.full((canvas_height, panel_width, 3), 28, dtype=np.uint8)
        main_y = (canvas_height - main_height) // 2
        main_panel[main_y : main_y + main_height] = main_view
        debug_panel[:resized_height] = resized_debug
        separator = np.full((canvas_height, 4, 3), 90, dtype=np.uint8)
        return cv2.hconcat([main_panel, separator, debug_panel])

    @staticmethod
    def _screen_work_area() -> tuple[int, int] | None:
        """Return the Windows desktop work area, excluding the taskbar when available."""
        try:
            import ctypes

            class Rect(ctypes.Structure):
                _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

            rect = Rect()
            if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
                return int(rect.right - rect.left), int(rect.bottom - rect.top)
            return int(ctypes.windll.user32.GetSystemMetrics(0)), int(ctypes.windll.user32.GetSystemMetrics(1))
        except (AttributeError, OSError, ValueError):
            return None

    @classmethod
    def _fit_preview_to_screen(cls, image: np.ndarray) -> np.ndarray:
        """Resize the complete preview proportionally to fit the current desktop."""
        screen = cls._screen_work_area()
        if screen is None:
            return image
        screen_width, screen_height = screen
        height, width = image.shape[:2]
        target_width = max(1, int(screen_width * 0.90))
        target_height = max(1, int(screen_height * 0.85))
        scale = min(target_width / max(1, width), target_height / max(1, height))
        resized_width = max(1, int(round(width * scale)))
        resized_height = max(1, int(round(height * scale)))
        if (resized_width, resized_height) == (width, height):
            return image
        interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
        return cv2.resize(image, (resized_width, resized_height), interpolation=interpolation)

    @classmethod
    def _debug_video_size(cls, fallback_image: np.ndarray) -> tuple[int, int]:
        """Return one fixed, codec-safe canvas size for debug video frames."""
        screen = cls._screen_work_area()
        if screen is None:
            width, height = fallback_image.shape[1], fallback_image.shape[0]
        else:
            width, height = int(screen[0] * 0.90), int(screen[1] * 0.85)
        return max(2, width - width % 2), max(2, height - height % 2)

    @staticmethod
    def _letterbox(image: np.ndarray, size: tuple[int, int]) -> np.ndarray:
        """Fit an image into a fixed canvas without changing its aspect ratio."""
        target_width, target_height = size
        height, width = image.shape[:2]
        scale = min(target_width / max(1, width), target_height / max(1, height))
        resized_width = max(1, int(round(width * scale)))
        resized_height = max(1, int(round(height * scale)))
        interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
        resized = cv2.resize(image, (resized_width, resized_height), interpolation=interpolation)
        canvas = np.full((target_height, target_width, 3), 28, dtype=np.uint8)
        x = (target_width - resized_width) // 2
        y = (target_height - resized_height) // 2
        canvas[y : y + resized_height, x : x + resized_width] = resized
        return canvas

    @staticmethod
    def _show_preview_or_raise(window_name: str, image: np.ndarray) -> int:
        """Show a preview frame, raising a clear error when OpenCV has no GUI backend."""
        try:
            cv2.imshow(window_name, image)
            return cv2.waitKey(1) & 0xFF
        except cv2.error as error:
            message = str(error)
            if "The function is not implemented" in message or "cvShowImage" in message:
                raise RuntimeError(
                    "OpenCV GUI backend is not available, so --preview/--preview-only cannot open a window. "
                    "Install a GUI-enabled OpenCV build, for example: "
                    "python -m pip uninstall opencv-python-headless opencv-python -y ; "
                    "python -m pip install opencv-python"
                ) from error
            raise

    def run(
        self,
        video: str,
        output_root: str = "general_track/exports/head_tail",
        tracker: str | None = "bytetrack.yaml",
        conf: float = 0.6,
        iou: float = 0.3,
        max_frames: int | None = None,
        preview: bool = False,
        preview_only: bool = False,
        debug: bool = False,
        save_crops: bool = False,
    ) -> dict:
        source = int(video) if str(video).strip().isdigit() else video
        capture = cv2.VideoCapture(source)
        if not capture.isOpened():
            raise FileNotFoundError(f"Cannot open video or camera: {video}")
        fps = float(capture.get(cv2.CAP_PROP_FPS)) or 30.0
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        source_name = f"camera_{video}" if isinstance(source, int) else Path(video).stem
        preview = preview or preview_only
        debug_enabled = bool(debug)
        self._shrimp_display_ids = {}
        self._next_display_id = 1
        run_dir = Path(output_root) / source_name / datetime.now().strftime("%Y%m%d_%H%M%S")
        if not preview_only:
            run_dir.mkdir(parents=True, exist_ok=True)
        crop_dir = run_dir / "classifier_crops"
        if save_crops and not preview_only:
            crop_dir.mkdir(exist_ok=True)
        video_path = run_dir / "result.mp4"
        csv_path = run_dir / "detections.csv"
        summary_path = run_dir / "per_shrimp.csv"
        writer = None
        debug_video_size = None
        all_records = []
        frame_index = 0
        progress_total = min(frame_count, max_frames) if max_frames and frame_count > 0 else (frame_count or None)

        with tqdm(total=progress_total, desc="Head/tail tracking", unit="frame", ncols=85) as progress:
            while max_frames is None or frame_index < max_frames:
                ok, frame = capture.read()
                if not ok:
                    break
                result = self._detect(frame, tracker, conf, iou)
                records, annotated, debug_items = self._process_frame(frame, result, frame_index, fps)
                for crop_index, record in enumerate(records):
                    crop = record.pop("classifier_crop")
                    if save_crops and not preview_only:
                        cv2.imwrite(str(crop_dir / f"frame_{frame_index:06d}_{crop_index:02d}_{record['label']}.jpg"), crop)
                all_records.extend(records)
                export_frame = annotated
                if debug:
                    export_debug_view = self._make_debug_view(debug_items, frame_index)
                    export_frame = self._combine_preview(annotated, export_debug_view)
                    if debug_video_size is None:
                        debug_video_size = self._debug_video_size(export_frame)
                    export_frame = self._letterbox(export_frame, debug_video_size)
                if writer is None and not preview_only:
                    height, width = export_frame.shape[:2]
                    writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
                if writer is not None:
                    writer.write(export_frame)
                if preview:
                    preview_image = annotated
                    if debug_enabled:
                        debug_view = self._make_debug_view(debug_items, frame_index)
                        preview_image = self._combine_preview(annotated, debug_view)
                    preview_image = self._fit_preview_to_screen(preview_image)
                    key = self._show_preview_or_raise("Head-tail shrimp tracking | D: debug | Q/Esc: quit", preview_image)
                    if key in {ord("d"), ord("D")}:
                        debug_enabled = not debug_enabled
                    elif key in {ord("q"), 27}:
                        break
                frame_index += 1
                progress.update(1)

        capture.release()
        if writer is not None:
            writer.release()
        if preview:
            cv2.destroyAllWindows()
        summaries = self._summarize(all_records)
        if preview_only:
            return {"output_dir": "", "video": "", "detections": "", "per_shrimp": ""}
        self._write_csv(csv_path, all_records)
        self._write_csv(summary_path, summaries)
        return {"output_dir": str(run_dir), "video": str(video_path), "detections": str(csv_path), "per_shrimp": str(summary_path)}

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
                }
            )
        return summaries

    @staticmethod
    def _write_csv(path: Path, rows: list[dict]) -> None:
        fieldnames = list(rows[0]) if rows else []
        with path.open("w", newline="", encoding="utf-8-sig") as file:
            if fieldnames:
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
