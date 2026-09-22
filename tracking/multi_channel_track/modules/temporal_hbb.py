import cv2
import numpy as np

from .config import HBB_TEMPORAL_FRAMES, HBB_TEMPORAL_STEP_FRAMES, IMGSZ_HBB


class TemporalHBBPipeline:
    """Build 3-frame 9-channel HBB inputs and map results back to crop coordinates."""

    def __init__(self, step_frames: int = HBB_TEMPORAL_STEP_FRAMES) -> None:
        self.step_frames = max(1, int(step_frames))
        self.buffers: dict[object, list[tuple[int, np.ndarray]]] = {}

    def reset(self, step_frames: int = HBB_TEMPORAL_STEP_FRAMES) -> None:
        self.step_frames = max(1, int(step_frames))
        self.buffers = {}

    def build_inputs(self, metas: list[dict], current_frame_idx: int) -> list[np.ndarray]:
        inputs = []
        for det_index, meta in enumerate(metas):
            key = meta.get("track_id")
            if key is None:
                key = ("det", det_index)
            buffer = self.buffers.setdefault(key, [])
            buffer.append((int(current_frame_idx), meta["crop"].copy()))
            cutoff = int(current_frame_idx) - self.step_frames * (HBB_TEMPORAL_FRAMES - 1)
            while len(buffer) > 1 and buffer[0][0] < cutoff:
                del buffer[0]
            frames = self.select_frames(buffer, int(current_frame_idx), self.step_frames)
            inputs.append(self.stack_frames(frames))
        return inputs

    @staticmethod
    def select_frames(buffer: list[tuple[int, np.ndarray]], current_frame_idx: int, step_frames: int) -> list[np.ndarray]:
        if not buffer:
            raise ValueError("Temporal HBB buffer is empty.")
        frame_numbers = np.asarray([item[0] for item in buffer], dtype=np.int32)
        targets = [
            int(current_frame_idx) - int(step_frames) * (HBB_TEMPORAL_FRAMES - 1 - offset)
            for offset in range(HBB_TEMPORAL_FRAMES)
        ]
        frames = []
        for target in targets:
            idx = int(np.argmin(np.abs(frame_numbers - target)))
            frames.append(buffer[idx][1])
        return frames

    @staticmethod
    def letterbox_crop(crop: np.ndarray, size: int = IMGSZ_HBB) -> np.ndarray:
        height, width = crop.shape[:2]
        scale = min(size / max(width, 1), size / max(height, 1))
        resized_w = max(1, int(round(width * scale)))
        resized_h = max(1, int(round(height * scale)))
        resized = cv2.resize(crop, (resized_w, resized_h), interpolation=cv2.INTER_LINEAR)
        canvas = np.full((size, size, 3), 114, dtype=crop.dtype)
        left = (size - resized_w) // 2
        top = (size - resized_h) // 2
        canvas[top : top + resized_h, left : left + resized_w] = resized
        return canvas

    @classmethod
    def stack_frames(cls, crops: list[np.ndarray]) -> np.ndarray:
        bgr_frames = [cls.letterbox_crop(crop, IMGSZ_HBB) for crop in crops]
        rgb_frames = [cv2.cvtColor(frame, cv2.COLOR_BGR2RGB) for frame in bgr_frames]
        return np.concatenate(rgb_frames, axis=2)

    @staticmethod
    def unletterbox_box(box_xyxy: np.ndarray, crop_shape) -> list[float]:
        crop_h, crop_w = crop_shape[:2]
        scale = min(IMGSZ_HBB / max(crop_w, 1), IMGSZ_HBB / max(crop_h, 1))
        resized_w = max(1, int(round(crop_w * scale)))
        resized_h = max(1, int(round(crop_h * scale)))
        pad_x = (IMGSZ_HBB - resized_w) / 2.0
        pad_y = (IMGSZ_HBB - resized_h) / 2.0
        x1, y1, x2, y2 = [float(v) for v in box_xyxy]
        x1 = np.clip((x1 - pad_x) / scale, 0, crop_w - 1)
        x2 = np.clip((x2 - pad_x) / scale, 0, crop_w - 1)
        y1 = np.clip((y1 - pad_y) / scale, 0, crop_h - 1)
        y2 = np.clip((y2 - pad_y) / scale, 0, crop_h - 1)
        return [float(x1), float(y1), float(x2), float(y2)]

    @staticmethod
    def project_crop_box(box_xyxy: list[float], inverse_matrix) -> np.ndarray:
        x1, y1, x2, y2 = box_xyxy
        pts = np.array(
            [[[x1, y1]], [[x2, y1]], [[x2, y2]], [[x1, y2]]],
            dtype=np.float32,
        )
        return cv2.perspectiveTransform(pts, inverse_matrix).astype(np.int32).reshape(-1, 2)
