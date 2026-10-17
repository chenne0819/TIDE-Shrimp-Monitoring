"""Collect six labeled videos once, then replay preview thresholds without inference.

Run from tracking/: ../.venv/Scripts/python.exe -B evaluate_ema.py --output-root PATH
Existing completed traces are reused. --replay-only never loads neural models.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import sys
import time

from general_track.modules.preview_smoothing import PreviewSmoothing


ROOT = Path(__file__).resolve().parent
VIDEOS = [(f"{prefix}仰拍-{index}.mp4", label)
          for prefix, label in (("公蝦", "male"), ("母蝦", "female"))
          for index in range(1, 4)]


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_video(analyzer, settings, source, label, directory):
    import cv2
    from general_track.modules import visualization
    from general_track.modules.obb_track import reset_obb_tracking

    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        capture.release()
        raise RuntimeError(f"Cannot open {source.name}")
    partial = directory / "trace.partial.jsonl"
    analyzer.monitoring.reset()
    reset_obb_tracking(analyzer.obb_model)
    analyzer._shrimp_display_ids = {}
    analyzer._next_display_id = 1
    preview = PreviewSmoothing(settings.get("cnn_threshold"))
    start = time.monotonic()
    index = 0
    try:
        fps = capture.get(cv2.CAP_PROP_FPS)
        if not math.isfinite(fps) or fps <= 0:
            raise ValueError("Video has no valid FPS; evaluation requires source timestamps")
        total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        width, height = int(capture.get(3)), int(capture.get(4))
        with partial.open("w", encoding="utf-8", newline="\n") as file:
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                if index == 0 and not analyzer.monitoring.check_frame(frame, index, fps):
                    raise RuntimeError("Water policy stopped the video; no complete evaluation")
                rows = analyzer._detect(frame, settings["tracker"], settings["conf"], settings["iou"])
                records, items = analyzer._process_frame(frame, rows, index, fps)
                # Match preview work, including its raw render and optional debug panel,
                # but never create a GUI window or encode a result video.
                visualization.render_frame(frame, records, items, analyzer.monitoring)
                now = time.monotonic()
                preview_items = preview.update(items, now)
                rendered = visualization.render_frame(frame, records, preview_items, analyzer.monitoring)
                row = {"frame": index, "source_seconds": index / fps, "wall_seconds": now - start,
                       "items": [{key: item[key] for key in
                                  ("track_id", "label", "confidence", "male_probability")}
                                 for item in items]}
                # Rendering uses the real preview branch but only the raw observations
                # above are replayed, so no threshold result contaminates the cache.
                if settings["debug"]:
                    rendered = visualization.combine_preview(rendered, visualization.make_debug_view(preview_items, index))
                visualization.fit_preview_to_screen(rendered)
                file.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
                index += 1
                if index % 100 == 0:
                    elapsed = time.monotonic() - start
                    status = {"video": source.name, "frames": index, "total_frames": total,
                              "elapsed_seconds": round(elapsed, 2), "processing_fps": round(index / elapsed, 2)}
                    write_json(directory.parent / "progress.json", status)
                    print(json.dumps(status, ensure_ascii=False), flush=True)
            file.flush()
        if index != total or index == 0:
            raise RuntimeError(f"Incomplete decode: {index}/{total} frames; trace kept as partial")
        metadata = {"video": source.name, "truth": label, "expected_shrimp": 5, "fps": fps,
                    "frames": index, "duration_seconds": index / fps, "width": width, "height": height,
                    "elapsed_seconds": time.monotonic() - start, "source_sha256": sha256(source),
                    "timing": "recorded monotonic processing time; offscreen preview, no GUI waitKey",
                    "created_at": datetime.now(timezone.utc).isoformat()}
        partial.replace(directory / "trace.jsonl")
        write_json(directory / "metadata.json", metadata)
        print(f"Completed {source.name}: {index} frames", flush=True)
    finally:
        capture.release()


def evaluate_trace(frames, metadata, threshold):
    smoothing = PreviewSmoothing(threshold)
    truth = metadata["truth"]
    previous = {}
    track_correct = Counter()
    track_total = Counter()
    segments = []
    switches = correct = observations = untracked = empty = 0
    error_seconds = observed_seconds = 0.0
    for frame in frames:
        now, source_time = frame["wall_seconds"], frame["source_seconds"]
        if not frame["items"]:
            empty += 1
        output = smoothing.update(frame["items"], now)
        for item in output:
            track_id = item["track_id"]
            if track_id is None:
                untracked += 1
                continue
            label = item["label"]
            right = label == truth
            observations += 1
            correct += right
            track_correct[track_id] += right
            track_total[track_id] += 1
            # Each valid tracked classification represents one source-frame interval.
            # Missing IDs/crops are excluded and reported, never assumed correct.
            observed_seconds += 1 / metadata["fps"]
            error_seconds += (not right) / metadata["fps"]
            old = previous.get(track_id)
            if old is None or now - old["wall"] > smoothing.RETENTION_SECONDS:
                segment = {"start": source_time, "first_correct_seconds": 0.0 if right else None}
                segments.append(segment)
            else:
                segment = old["segment"]
                switches += label != old["label"]
                if right and segment["first_correct_seconds"] is None:
                    segment["first_correct_seconds"] = source_time - segment["start"]
            previous[track_id] = {"wall": now, "label": label, "segment": segment}
    delays = [value["first_correct_seconds"] for value in segments if value["first_correct_seconds"] is not None]
    track_accuracies = [track_correct[key] / count for key, count in track_total.items()]
    return {"video": metadata["video"], "truth": truth, "threshold": threshold,
            "observations": observations, "correct_observations": correct,
            "accuracy": correct / observations if observations else None,
            "error_observation_seconds": error_seconds, "tracked_observation_seconds": observed_seconds,
            "switches": switches,
            "switches_per_visible_track_minute": switches * 60 / observed_seconds if observed_seconds else None,
            "unique_track_ids": len(track_total), "expected_shrimp": metadata["expected_shrimp"],
            "track_segments": len(segments), "segments_never_correct": sum(
                value["first_correct_seconds"] is None for value in segments),
            "mean_first_correct_source_seconds": sum(delays) / len(delays) if delays else None,
            "mean_track_accuracy": sum(track_accuracies) / len(track_accuracies) if track_accuracies else None,
            "untracked_classifications": untracked, "empty_frames": empty,
            "valid_observations_per_expected_shrimp_frame": observations / (
                metadata["expected_shrimp"] * len(frames)) if frames else 0}


def aggregate(results):
    if any(row["accuracy"] is None for row in results):
        raise ValueError("At least one video has no tracked classifications; cannot rank thresholds")
    recalls = {label: sum(row["accuracy"] for row in results if row["truth"] == label) /
               sum(row["truth"] == label for row in results) for label in ("male", "female")}
    # Video-balanced rates avoid letting long clips or fragmented tracks dominate.
    tp = recalls["male"]
    tn = recalls["female"]
    male_f1 = 2 * tp / (2 * tp + (1 - tn) + (1 - tp))
    female_f1 = 2 * tn / (2 * tn + (1 - tp) + (1 - tn))
    return {"threshold": results[0]["threshold"], "balanced_accuracy": (tp + tn) / 2,
            "macro_f1_video_balanced": (male_f1 + female_f1) / 2,
            "male_recall": tp, "female_recall": tn,
            "switches": sum(row["switches"] for row in results),
            "mean_switches_per_visible_track_minute": sum(
                row["switches_per_visible_track_minute"] for row in results) / len(results),
            "segments_never_correct": sum(row["segments_never_correct"] for row in results)}


def load_traces(output):
    traces = []
    for filename, truth in VIDEOS:
        directory = output / Path(filename).stem
        metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
        if metadata["truth"] != truth:
            raise ValueError("Cached truth does not match the declared video labels")
        with (directory / "trace.jsonl").open(encoding="utf-8") as file:
            frames = [json.loads(line) for line in file]
        if len(frames) != metadata["frames"]:
            raise ValueError("Trace frame count does not match metadata")
        traces.append((frames, metadata))
    return traces


def write_csv(path, rows):
    import csv
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def replay(output):
    traces = load_traces(output)
    metrics = {}
    details = {}

    def run(threshold):
        results = [evaluate_trace(frames, metadata, threshold) for frames, metadata in traces]
        details[threshold] = results
        metrics[threshold] = aggregate(results)

    for threshold in [value / 100 for value in range(101)]:
        run(threshold)
    coarse = sorted(metrics, key=lambda key: (-metrics[key]["macro_f1_video_balanced"], metrics[key]["switches"]))[:3]
    for center in coarse:
        for integer in range(max(0, round(center * 1000) - 10), min(1000, round(center * 1000) + 10) + 1):
            threshold = integer / 1000
            if threshold not in metrics:
                run(threshold)
    ranked = sorted(metrics.values(), key=lambda row: (-row["macro_f1_video_balanced"], row["switches"], row["threshold"]))
    best = ranked[0]
    baseline = metrics[0.03]
    write_csv(output / "threshold_metrics.csv", sorted(metrics.values(), key=lambda row: row["threshold"]))
    write_csv(output / "video_metrics.csv", [row for key in sorted(details) for row in details[key]])
    summary = {"best": best, "baseline": baseline, "thresholds_tested": len(metrics),
               "ranking": "video-balanced macro-F1 descending, then switches ascending; descriptive tuning only",
               "best_per_video": details[best["threshold"]], "baseline_per_video": details[0.03]}
    write_json(output / "summary.json", summary)
    lines = ["# EMA 門檻離線評估報告", "", "此結果為六支指定影片的調參分析，不是獨立測試準確率。",
             "真實標籤依使用者提供：每支 5 隻，公蝦影片全為公、母蝦影片全為母；不同影片不假設為不同個體。",
             "", "## 方法", "", "- 六支影片逐幀執行原有 OBB、追蹤、方向校正及 CNN；無抽幀。",
             "- 固定 EMA 時間常數與確認時間各 1 秒；只搜尋獨立重播門檻，不修改單幀 0.03 或預覽設定。",
             "- EMA 重播使用首次離屏推論記錄的 monotonic 時間；各門檻共用同一份觀測與時間。",
             "- 無 GUI waitKey；日後電腦速度或顯示負載改變，實際時間平滑結果可能不同。",
             "- 每支影片等權重；macro-F1 由公／母影片平均正確率形成的平衡混淆率計算。",
             "- 只對有 ID 且成功分類的觀測評分；未偵測、無裁切、無 ID 不視為正確。",
             "- 每筆有效觀測以 1/FPS 計算來源影片的個體觀測時間；不代表獨立蝦隻數或 ID 指標準確率。",
             "", "## 結果", "", f"搜尋 {len(metrics)} 個門檻，先 0–1 每 0.01 粗搜，再於前三名附近每 0.001 細搜。",
             "", "| 項目 | 原門檻 0.03 | 候選門檻 |", "|---|---:|---:|",
             f"| 門檻 | 0.030 | {best['threshold']:.3f} |",
             f"| 影片平衡 macro-F1 | {baseline['macro_f1_video_balanced']:.4f} | {best['macro_f1_video_balanced']:.4f} |",
             f"| 公蝦平均 recall | {baseline['male_recall']:.2%} | {best['male_recall']:.2%} |",
             f"| 母蝦平均 recall | {baseline['female_recall']:.2%} | {best['female_recall']:.2%} |",
             f"| 標籤切換總次數 | {baseline['switches']} | {best['switches']} |", "",
             "## 候選門檻逐影片結果", "", "| 影片 | 正確率 | 切換 | ID 數 | 從未正確的追蹤片段 |",
             "|---|---:|---:|---:|---:|"]
    for row in summary["best_per_video"]:
        lines.append(f"| {row['video']} | {row['accuracy']:.2%} | {row['switches']} | {row['unique_track_ids']} | {row['segments_never_correct']} |")
    lines += ["", "## 限制與下一步", "", "- 單色別影片提供弱標籤；非蝦誤偵測若進入分類也會被計分，未逐框人工驗證。",
              "- ID 數量不應直接等於生物個體數；高於 5 可能是 ID 分裂或誤偵測，不強制選取五個 ID。",
              "- 模型訓練資料是否與本批影片重疊、影片間是否為相同個體，尚未確認。",
              "- 候選門檻尚未套用；先在未參與調參的影片確認分類與視覺穩定性。",
              "- 機率/時間原始紀錄、模型雜湊與環境資訊保存在本報告同目錄。"]
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "general_track/config.toml")
    parser.add_argument("--replay-only", action="store_true")
    args = parser.parse_args()
    output = args.output_root.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if not args.replay_only:
        from general_track.run_track import create_analyzer, load_settings
        import torch
        settings = load_settings(args.config)
        environment = {"python": sys.version, "executable": sys.executable,
                       "packages": {name: importlib.metadata.version(name) for name in
                                    ("torch", "torchvision", "ultralytics", "opencv-python", "numpy", "scikit-learn")},
                       "settings": settings, "config_sha256": sha256(args.config),
                       "model_sha256": {name: sha256(settings[name]) for name in ("obb_model", "classifier_model")},
                       "cuda_available": torch.cuda.is_available(),
                       "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
                       "smoothing": {"time_constant": 1.0, "confirmation_seconds": 1.0, "retention_seconds": 3.0},
                       "source_code_sha256": {name: sha256(ROOT / name) for name in
                                              ("evaluate_ema.py", "general_track/modules/preview_smoothing.py",
                                               "general_track/modules/head_tail_pipeline.py")}}
        previous = output / "environment.json"
        if previous.is_file() and json.loads(previous.read_text(encoding="utf-8")) != environment:
            raise ValueError("Environment/config changed; choose a new output directory to avoid mixing runs")
        write_json(previous, environment)
        analyzer = create_analyzer(settings)
        for filename, label in VIDEOS:
            directory = output / Path(filename).stem
            directory.mkdir(exist_ok=True)
            if (directory / "metadata.json").is_file() and (directory / "trace.jsonl").is_file():
                metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
                if metadata["source_sha256"] != sha256(ROOT / "video" / filename):
                    raise ValueError(f"Source changed for cached trace: {filename}")
                print(f"Reuse completed trace: {filename}", flush=True)
                continue
            collect_video(analyzer, settings, ROOT / "video" / filename, label, directory)
    replay(output)


if __name__ == "__main__":
    main()
