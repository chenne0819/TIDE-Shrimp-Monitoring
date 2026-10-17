import csv
from datetime import datetime
from pathlib import Path

import cv2


def write_csv(path, rows):
    fieldnames = list(rows[0]) if rows else []
    with Path(path).open("w", newline="", encoding="utf-8-sig") as file:
        if fieldnames:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)


class RunOutput:
    def __init__(self, output_root, source_name, fps, save_crops=False):
        parent = Path(output_root) / source_name
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = 0
        while True:
            self.run_dir = parent / (stamp if suffix == 0 else f"{stamp}_{suffix:02d}")
            try:
                self.run_dir.mkdir(parents=True, exist_ok=False)
                break
            except FileExistsError:
                suffix += 1
        self.video_path = self.run_dir / "result.mp4"
        self.crop_dir = self.run_dir / "classifier_crops"
        self.fps = fps
        self.save_crops = save_crops
        self.writer = None
        if save_crops:
            self.crop_dir.mkdir()

    def write(self, frame, items, frame_index):
        if self.save_crops:
            for index, item in enumerate(items):
                path = self.crop_dir / f"frame_{frame_index:06d}_{index:02d}_{item['label']}.jpg"
                if not cv2.imwrite(str(path), item["classifier_crop"]):
                    raise RuntimeError(f"Unable to save classifier crop: {path}")
        if self.writer is None:
            height, width = frame.shape[:2]
            self.writer = cv2.VideoWriter(str(self.video_path), cv2.VideoWriter_fourcc(*"mp4v"),
                                          self.fps, (width, height))
            if not self.writer.isOpened():
                raise RuntimeError(f"Unable to create result video: {self.video_path}")
        self.writer.write(frame)

    def finish(self, records, summaries, monitoring):
        csv_path = self.run_dir / "detections.csv"
        summary_path = self.run_dir / "per_shrimp.csv"
        write_csv(csv_path, records)
        write_csv(summary_path, summaries)
        return {
            "output_dir": str(self.run_dir),
            "video": str(self.video_path) if self.writer is not None else "",
            "detections": str(csv_path),
            "per_shrimp": str(summary_path),
            **monitoring.export(self.run_dir),
        }

    def close(self):
        if self.writer is not None:
            self.writer.release()
