from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def run(args):
    print()
    print(">>>", " ".join(str(x) for x in args), flush=True)

    subprocess.run(
        [sys.executable, *map(str, args)],
        cwd=ROOT,
        check=True,
    )


def video_path(filename):
    path = ROOT / "video" / filename
    if not path.exists():
        raise FileNotFoundError(f"找不到影片：{path}")
    return path


def model_path(filename):
    path = ROOT / "model" / filename
    if not path.exists():
        raise FileNotFoundError(f"找不到模型：{path}")
    return path


multi_jobs = [
    ("公母蝦仰拍-3.mp4", 30),
    ("公母蝦仰拍-1.mp4", 10),
    ("公母蝦仰拍-2.mp4", 10),
    ("公母蝦仰拍-3.mp4", 10),
    ("公母蝦仰拍-1.mp4", 1),
    ("公母蝦仰拍-2.mp4", 1),
    ("公母蝦仰拍-3.mp4", 1),
]

for filename, step in multi_jobs:
    run([
        "-m",
        "multi_channel_track.run_multi_channel_track",
        "--video",
        video_path(filename),
        "--unknown-total",
        "--hbb-temporal-step-frames",
        step,
    ])


videos = [
    "公母蝦仰拍-1.mp4",
    "公母蝦仰拍-2.mp4",
    "公母蝦仰拍-3.mp4",
]

models = [
    "best-hbb-yolo11s.pt",
    "best-hbb-yolo11n.pt",
    "best-hbb-yolo11m.pt",
    "best-hbb-yolo11l.pt",
]

for model in models:
    for video in videos:
        run([
            "-m",
            "general_track.run_track",
            "--video",
            video_path(video),
            "--unknown-total",
            "--hbb-model",
            model_path(model),
        ])

print()
print("全部完成。")