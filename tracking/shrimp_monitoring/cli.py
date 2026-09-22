"""Common, opt-in monitoring options for all inference commands."""

from project_paths import project_path

from .runtime import MonitoringSession

def add_monitoring_arguments(parser) -> None:
    group = parser.add_argument_group("water quality and size/weight estimation")
    group.add_argument("--monitoring", action="store_true", help="Enable both original water classifier and size/weight regression.")
    group.add_argument("--water-quality", action="store_true", help="Enable the first-frame water check only.")
    group.add_argument("--biometrics", action="store_true", help="Enable length, OBB-width proxy and weight estimates only.")
    group.add_argument("--water-model", default=project_path("model/water/logistic_regression_model.pth"), help="Original water state_dict checkpoint.")
    group.add_argument("--biometrics-model-dir", default=project_path("model/biometrics"), help="Directory containing the four original regression .pkl files.")
    group.add_argument("--water-policy", choices=("stop", "report"), default="stop", help="Stop a turbid source before detection (default), or only report its water status.")
    group.add_argument("--pixels-per-mm", type=float, default=2.5, help="Pixels per mm in the calibration reference frame; original value is 2.5.")
    group.add_argument("--measurement-reference-size", type=int, nargs=2, metavar=("WIDTH", "HEIGHT"), default=(800, 450), help="Calibration frame resolution; polygons are mapped here without changing detector input.")
    group.add_argument("--weight-mode", choices=("length", "length-width"), default="length", help="Original length-only fallback (default), or length + OBB width proxy (requires validation).")


def monitoring_from_args(args) -> MonitoringSession:
    water, estimator = None, None
    if args.monitoring or args.biometrics:
        from .biometrics import BiometricsEstimator
        estimator = BiometricsEstimator(
            args.biometrics_model_dir,
            pixels_per_mm=args.pixels_per_mm,
            reference_size=tuple(args.measurement_reference_size),
            weight_mode=args.weight_mode,
        )
    if args.monitoring or args.water_quality:
        from .water import WaterClassifier
        water = WaterClassifier(args.water_model)
    return MonitoringSession(water_classifier=water, estimator=estimator, water_policy=args.water_policy)
