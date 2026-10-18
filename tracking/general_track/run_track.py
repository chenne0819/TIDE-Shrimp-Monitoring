import argparse
import math
from pathlib import Path
import sys
import tomllib


DEFAULT_CONFIG = Path(__file__).with_name("config.toml")


def load_settings(config_path=DEFAULT_CONFIG):
    path = Path(config_path).expanduser().resolve()
    with path.open("rb") as file:
        settings = tomllib.load(file)
    # Existing standalone configurations retain their raw-video behavior.
    settings.setdefault("smooth_video", False)
    booleans = {"water_quality", "biometrics", "preview", "preview_only", "debug", "save_crops", "smooth_video"}
    required = booleans | {"video", "obb_model", "classifier_model", "tracker", "imgsz", "conf", "iou",
                           "water_policy", "pixels_per_mm", "measurement_reference_size", "weight_mode", "output_root"}
    allowed = required | {"cnn_threshold", "max_frames", "water_model", "biometrics_model_dir"}
    if unknown := settings.keys() - allowed:
        raise ValueError(f"Unknown settings: {', '.join(sorted(unknown))}")
    if missing := required - settings.keys():
        raise ValueError(f"Missing settings: {', '.join(sorted(missing))}")
    for name in booleans:
        if type(settings[name]) is not bool:
            raise ValueError(f"{name} must be true or false")
    for name in ("conf", "iou", "cnn_threshold", "pixels_per_mm"):
        if name not in settings:
            continue
        value = settings[name]
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError(f"{name} must be a finite number")
        if (value <= 0 if name == "pixels_per_mm" else not 0 <= value <= 1):
            raise ValueError(f"{name} must be positive" if name == "pixels_per_mm" else f"{name} must be between 0 and 1")
    for name in ("imgsz", "max_frames"):
        if name in settings and (type(settings[name]) is not int or settings[name] < 1):
            raise ValueError(f"{name} must be a positive integer")
    reference = settings["measurement_reference_size"]
    if not isinstance(reference, list) or len(reference) != 2 or any(type(v) is not int or v < 1 for v in reference):
        raise ValueError("measurement_reference_size must contain two positive integers: [width, height]")
    if settings["water_policy"] not in ("stop", "report"):
        raise ValueError("water_policy must be stop or report")
    if settings["weight_mode"] not in ("length", "length-width"):
        raise ValueError("weight_mode must be length or length-width")

    def resolve(name):
        value = settings.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a nonempty path")
        value = Path(value).expanduser()
        return str((value if value.is_absolute() else path.parent / value).resolve())

    video = settings["video"]
    if type(video) is int:
        if video < 0:
            raise ValueError("video camera index must not be negative")
    else:
        settings["video"] = resolve("video")
        if not Path(settings["video"]).is_file():
            raise FileNotFoundError(f"Video not found: {settings['video']}")
    for name in ("obb_model", "classifier_model"):
        settings[name] = resolve(name)
        if not Path(settings[name]).is_file():
            raise FileNotFoundError(f"Model not found ({name}): {settings[name]}")
    tracker = settings["tracker"]
    if not isinstance(tracker, str) or not tracker.strip():
        raise ValueError("tracker must be an internal tracker name or a YAML path")
    if tracker not in ("bytetrack.yaml", "botsort.yaml"):
        settings["tracker"] = resolve("tracker")
        if not Path(settings["tracker"]).is_file():
            raise FileNotFoundError(f"Tracker not found: {settings['tracker']}")
    settings["output_root"] = resolve("output_root")
    if Path(settings["output_root"]).is_file():
        raise ValueError("output_root must be a directory")
    if settings["water_quality"]:
        settings["water_model"] = resolve("water_model")
        if not Path(settings["water_model"]).is_file():
            raise FileNotFoundError(f"Water model not found: {settings['water_model']}")
    if settings["biometrics"]:
        settings["biometrics_model_dir"] = resolve("biometrics_model_dir")
        from shrimp_monitoring.biometrics import MODEL_FILES
        for filename, _ in MODEL_FILES.values():
            if not (Path(settings["biometrics_model_dir"]) / filename).is_file():
                raise FileNotFoundError(f"Biometrics model not found: {filename}")
    return settings


def create_analyzer(settings):
    from shrimp_monitoring import MonitoringSession
    from .modules.head_tail_pipeline import HeadTailShrimpAnalyzer
    from .modules.obb_track import load_obb_model
    from .modules.sex_classifier import load_sex_classifier
    water, estimator = None, None
    if settings["water_quality"]:
        from shrimp_monitoring.water import WaterClassifier
        water = WaterClassifier(settings["water_model"])
    if settings["biometrics"]:
        from shrimp_monitoring.biometrics import BiometricsEstimator
        estimator = BiometricsEstimator(settings["biometrics_model_dir"], pixels_per_mm=settings["pixels_per_mm"],
                                        reference_size=settings["measurement_reference_size"], weight_mode=settings["weight_mode"])
    monitoring = MonitoringSession(water_classifier=water, estimator=estimator, water_policy=settings["water_policy"])
    return HeadTailShrimpAnalyzer(load_obb_model(settings["obb_model"]), load_sex_classifier(settings["classifier_model"]),
                                  monitoring=monitoring, cnn_threshold=settings.get("cnn_threshold"), imgsz=settings["imgsz"])


def build_parser():
    parser = argparse.ArgumentParser(description="Track OBB shrimp and classify female/male using a TOML configuration.",
                                     allow_abbrev=False)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="TOML configuration path; default: %(default)s")
    return parser


def main():
    args = build_parser().parse_args()
    try:
        settings = load_settings(args.config)
        analyzer = create_analyzer(settings)
        keys = ("video", "output_root", "tracker", "conf", "iou", "preview", "preview_only", "debug", "save_crops", "smooth_video")
        paths = analyzer.run(**{key: settings[key] for key in keys}, max_frames=settings.get("max_frames"))
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1) from None
    if paths.get("skipped"):
        print("Skipped: the first frame was classified as turbid water.")
    if paths["output_dir"]:
        print(f"Output: {paths['output_dir']}")
    elif not paths.get("skipped"):
        print("Preview complete. No outputs were saved.")


if __name__ == "__main__":
    main()
