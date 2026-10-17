from __future__ import annotations

import cv2
import numpy as np


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


def classifier_region_bounds(shape):
    horizontal_height, total_length = shape[:2]
    left = total_length // 4
    right = total_length - total_length // 2
    top = horizontal_height // 5
    bottom = horizontal_height - horizontal_height // 5
    if right <= left:
        raise ValueError(f"Shrimp crop is too short: {total_length}px")
    if bottom <= top:
        raise ValueError(f"Shrimp crop is too low: {horizontal_height}px")
    return left, top, right, bottom


def crop_classifier_region(horizontal_crop: np.ndarray) -> np.ndarray:
    left, top, right, bottom = classifier_region_bounds(horizontal_crop.shape)
    return horizontal_crop[top:bottom, left:right].copy()
