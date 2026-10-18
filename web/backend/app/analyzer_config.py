"""Create an isolated TOML configuration for each background analysis job."""
import json
from pathlib import Path
import tomllib


def _toml_value(value):
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if type(value) not in (str, bool, int, float):
        raise ValueError(f"Unsupported analyzer setting type: {type(value).__name__}")
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def write_job_config(analyzer_root: Path, source: Path, output: Path, destination: Path,
                     *, water_policy: str, max_frames: int | None):
    template = analyzer_root / "general_track/config.toml"
    with template.open("rb") as file:
        settings = tomllib.load(file)
    # Relative assets belong to the template, not the per-job output directory.
    for name in ("obb_model", "classifier_model", "water_model", "biometrics_model_dir", "tracker"):
        value = settings.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Analyzer config requires {name}")
        if name == "tracker" and value in ("bytetrack.yaml", "botsort.yaml"):
            continue
        path = Path(value).expanduser()
        settings[name] = str((path if path.is_absolute() else template.parent / path).resolve())
    settings.update(video=str(source.resolve()), output_root=str(output.resolve()),
                    water_quality=True, biometrics=True, water_policy=water_policy,
                    preview=False, preview_only=False, debug=False, save_crops=False)
    settings.pop("max_frames", None)
    if max_frames is not None:
        settings["max_frames"] = max_frames
    destination.write_text("\n".join(f"{json.dumps(key)} = {_toml_value(value)}"
                                      for key, value in settings.items()) + "\n", encoding="utf-8")
    return destination
