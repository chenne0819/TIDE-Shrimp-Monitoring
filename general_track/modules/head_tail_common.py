from __future__ import annotations

import csv
from pathlib import Path

import cv2
import numpy as np

from .obb_track import extract_obb_track_id


REQUIRED_HEAD_TAIL_OBB_CLASSES = {"shrimp", "shrimp_head", "shrimp_tail"}


def validate_head_tail_obb_model(model) -> None:
    names = set(model.names.values())
    missing = REQUIRED_HEAD_TAIL_OBB_CLASSES - names
    if missing:
        raise ValueError(f"OBB model is missing classes: {sorted(missing)}; got {sorted(names)}")


def obb_rows(result) -> list[dict]:
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


def split_head_tail_rows(rows: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    return (
        [row for row in rows if row["class_name"] == "shrimp"],
        [row for row in rows if row["class_name"] == "shrimp_head"],
        [row for row in rows if row["class_name"] == "shrimp_tail"],
    )


def point_in_polygon(center: tuple[float, float], polygon: np.ndarray) -> bool:
    contour = np.asarray(polygon, dtype=np.float32).reshape(-1, 1, 2)
    return cv2.pointPolygonTest(contour, (float(center[0]), float(center[1])), False) >= 0


def associated_centers(items: list[dict], polygon: np.ndarray) -> list[tuple[float, float]]:
    return [item["center"] for item in items if point_in_polygon(item["center"], polygon)]


def order_points(points: np.ndarray) -> np.ndarray:
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
    polygon = np.asarray(shrimp_polygon, dtype=np.float32).reshape(-1, 2)
    rect = cv2.minAreaRect(polygon)
    source = order_points(cv2.boxPoints(rect))
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


def transform_x(center: tuple[float, float], matrix: np.ndarray) -> float:
    point = np.array([[[center[0], center[1]]]], dtype=np.float32)
    return float(cv2.perspectiveTransform(point, matrix)[0, 0, 0])


def orient_head_left(
    crop: np.ndarray,
    matrix: np.ndarray,
    head_centers: list[tuple[float, float]],
    tail_centers: list[tuple[float, float]],
) -> tuple[np.ndarray | None, str]:
    if len(head_centers) == 1:
        flip = transform_x(head_centers[0], matrix) > crop.shape[1] / 2
        source = "head"
    elif len(tail_centers) == 1:
        flip = transform_x(tail_centers[0], matrix) < crop.shape[1] / 2
        source = "tail"
    else:
        return None, "ambiguous_head_and_tail"
    return (cv2.flip(crop, 1) if flip else crop), source


def crop_classifier_region(horizontal_crop: np.ndarray) -> np.ndarray:
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


def screen_work_area() -> tuple[int, int] | None:
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


def fit_preview_to_screen(image: np.ndarray) -> np.ndarray:
    screen = screen_work_area()
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


def debug_video_size(fallback_image: np.ndarray) -> tuple[int, int]:
    screen = screen_work_area()
    if screen is None:
        width, height = fallback_image.shape[1], fallback_image.shape[0]
    else:
        width, height = int(screen[0] * 0.90), int(screen[1] * 0.85)
    return max(2, width - width % 2), max(2, height - height % 2)


def letterbox(image: np.ndarray, size: tuple[int, int]) -> np.ndarray:
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


def show_preview_or_raise(window_name: str, image: np.ndarray) -> int:
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


def combine_preview(main_view: np.ndarray, debug_view: np.ndarray) -> np.ndarray:
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


def write_csv(path: Path, rows: list[dict]) -> None:
    fieldnames = list(rows[0]) if rows else []
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        if fieldnames:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
