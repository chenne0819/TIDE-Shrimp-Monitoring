"""Read the existing analyzer's exported per-individual summaries, never sum frames."""
import csv
import json
import math
from pathlib import Path
from statistics import mean


def rows(path: Path | None):
    if path is None or not path.is_file() or not path.stat().st_size:
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) and result >= 0 else None
    except (ValueError, TypeError):
        return None


def find_one(root: Path, names: tuple[str, ...]):
    for name in names:
        matches = list(root.rglob(name))
        if len(matches) > 1:
            raise RuntimeError(f"Unexpected duplicate analyzer export: {name}")
        if matches:
            return matches[0]
    return None


def read_results(root: Path):
    monitoring_path = find_one(root, ("monitoring.json",))
    if monitoring_path is None:
        raise RuntimeError("Analyzer did not export monitoring.json; check that monitoring integration is installed.")
    metadata = json.loads(monitoring_path.read_text(encoding="utf-8-sig"))
    # The public metadata describes methods without exposing machine-specific model paths.
    metadata = {key: value for key, value in metadata.items() if key not in {"water_model", "biometrics_model_dir"}}
    metadata["count_note"] = "同一影片內的個體 ID 數，不代表跨影片去重後的池內族群數。"
    metadata["measurement_note"] = "沿用原攝影校正；長度、重量為估計值，寬度為 OBB 代理值，需驗證新攝影條件。"
    tracks_path = find_one(root, ("per_shrimp.csv", "per_shrimp_summary.csv"))
    water_path = find_one(root, ("water_quality.csv",))
    summary_path = find_one(root, ("bucket_summary.csv",))
    detections_path = find_one(root, ("detections.csv",))
    stopped = metadata.get("status") == "skipped_turbid"
    if tracks_path is None and not stopped:
        raise RuntimeError("Analyzer did not export a per-individual summary.")
    tracks = []
    seen = set()
    for row in rows(tracks_path):
        track_id = str(row.get("track_id", row.get("Shrimp_ID", ""))).strip()
        observations = int(number(row.get("observations", row.get("Total_Seen"))) or 0)
        if not track_id or observations == 0:
            continue
        if track_id in seen:
            raise RuntimeError(f"Duplicate track in analyzer summary: {track_id}")
        seen.add(track_id)
        label = row.get("final_label", row.get("Final_Label", "Unknown")).strip().lower()
        label = {"m": "Male", "male": "Male", "f": "Female", "female": "Female"}.get(label, "Unknown")
        tracks.append({"track_id": track_id, "label": label,
                       "observations": observations,
                       "length_mm": number(row.get("mean_length_mm")),
                       "width_mm": number(row.get("mean_width_mm")),
                       "weight_g": number(row.get("mean_weight_g"))})
    water = next(iter(rows(water_path)), {})
    label = water.get("water_label")
    summary = next(iter(rows(summary_path)), {})
    artifacts = {key: value for key, value in {"tracks": tracks_path, "water": water_path,
                 "summary": summary_path, "detections": detections_path}.items() if value is not None}
    return {
        "status": "stopped" if stopped else "completed", "tracks": tracks, "metadata": metadata,
        "water_label": label if label in {"clear", "turbid"} else None,
        "water_confidence": number(water.get("water_confidence")), "artifacts": artifacts,
        "processed_frames": int(number(summary.get("Processed_Source_Frames")) or 0),
        "video": find_one(root, ("result.mp4", "result_video.mp4")),
        **{f"avg_{field}": round(mean(values), 3) if values else None
           for field in ("length_mm", "width_mm", "weight_g")
           for values in [[track[field] for track in tracks if track[field] is not None]]},
    }
