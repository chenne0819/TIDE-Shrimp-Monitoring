from __future__ import annotations

import cv2
import numpy as np

from .head_tail_common import classifier_region_bounds


def label_color(label):
    # OpenCV uses BGR: cyan-blue for male, green for female.
    return {"male": (230, 190, 35), "female": (70, 180, 60)}.get(label, (180, 180, 180))


def short_label(label):
    return {"male": "M", "female": "F"}.get(label, "?")


def draw_label(image, text, anchor):
    font_scale = 0.75
    (width, _), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 2)
    font_scale *= min(1.0, max(1, image.shape[1] - 8) / max(1, width))
    (width, height), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 2)
    x = max(4, min(int(anchor[0]), image.shape[1] - width - 4))
    y = max(height + 4, min(int(anchor[1]), image.shape[0] - baseline - 4))
    cv2.rectangle(image, (x - 4, y - height - 4),
                  (x + width + 3, y + baseline + 3), (32, 32, 32), -1)
    cv2.putText(image, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX,
                font_scale, (255, 255, 255), 2, cv2.LINE_AA)


def preview_score(item):
    probability = item["preview_male_probability"]
    return "Pm ?" if probability is None else f"Pm {probability:.3f}"


def render_frame(frame, records, items, monitoring):
    annotated = frame.copy()
    for record, item in zip(records, items):
        polygon = item["polygon"]
        label = item["label"]
        track_id = item["track_id"]
        color = label_color(label)
        cv2.polylines(annotated, [polygon.astype(np.int32)], True, color, 2)
        anchor = tuple(polygon[np.argmin(polygon[:, 1])].astype(int))
        text = f"{track_id} {short_label(label)}" if track_id is not None else "?"
        if item.get("preview_male_probability") is not None:
            text += f" | {preview_score(item)}"
        draw_label(annotated, text, anchor)
        monitoring.annotate_measurement(annotated, record, anchor)
    monitoring.annotate_water(annotated)
    return annotated


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


def make_debug_view(items: list[dict], frame_index: int) -> np.ndarray:
    """Build a tiled view with the classifier abdomen interval highlighted."""
    tile_width, tile_height = 480, 180
    tiles = []
    for item in items:
        crop = item["crop"]
        smoothed = "preview_male_probability" in item
        header_height = 64 if smoothed else 38
        height, total_length = crop.shape[:2]
        left, top, right, bottom = classifier_region_bounds(crop.shape)
        marked = crop.copy()
        overlay = marked.copy()
        cv2.rectangle(overlay, (left, top), (max(left, right - 1), max(top, bottom - 1)), (0, 255, 255), -1)
        marked = cv2.addWeighted(overlay, 0.28, marked, 0.72, 0)
        cv2.rectangle(marked, (left, top), (max(left, right - 1), max(top, bottom - 1)), (0, 255, 255), 2)

        scale = min(tile_width / max(1, total_length), (tile_height - header_height - 4) / max(1, height))
        resized = cv2.resize(
            marked,
            (max(1, int(round(total_length * scale))), max(1, int(round(height * scale)))),
            interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR,
        )
        tile = np.full((tile_height, tile_width, 3), 28, dtype=np.uint8)
        y = header_height + max(0, (tile_height - header_height - resized.shape[0]) // 2)
        x = max(0, (tile_width - resized.shape[1]) // 2)
        tile[y : y + resized.shape[0], x : x + resized.shape[1]] = resized
        identity = item["track_id"] if item["track_id"] is not None else "?"
        text = (f"{identity} {short_label(item['label'])} | {preview_score(item)}"
                if smoothed else f"{identity} {short_label(item['label'])} {item['confidence']:.2f}")
        cv2.putText(tile, text, (8, 27), cv2.FONT_HERSHEY_SIMPLEX,
                    0.70, (255, 255, 255), 2, cv2.LINE_AA)
        if smoothed:
            raw = f"CNN {short_label(item['raw_label'])} {item['confidence']:.2f}"
            cv2.putText(tile, raw, (8, 53), cv2.FONT_HERSHEY_SIMPLEX, 0.60,
                        (220, 220, 220), 1, cv2.LINE_AA)
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
