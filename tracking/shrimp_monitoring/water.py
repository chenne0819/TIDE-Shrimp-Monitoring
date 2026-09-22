"""ShrimpVisionRT's 28x28 logistic water classifier, loaded once per session.

Source: ShrimpVisionRT/shrimp_OBB/logistic_water.py (dd87698).
Its ndarray path interprets OpenCV BGR bytes as RGB before grayscale conversion.
That behavior is deliberately retained for compatibility with the supplied model.
"""

from pathlib import Path

import numpy as np
from PIL import Image


def preprocess_water(image) -> np.ndarray:
    if isinstance(image, (str, Path)):
        with Image.open(image) as source:
            gray = source.convert("L")
    elif isinstance(image, np.ndarray):
        if image.size == 0 or image.dtype != np.uint8 or image.ndim not in (2, 3):
            raise ValueError("Water classifier expects a non-empty uint8 image.")
        gray = Image.fromarray(image).convert("L")
    else:
        raise ValueError("Water classifier expects an image path or an OpenCV frame.")
    gray = gray.resize((28, 28), resample=Image.Resampling.BILINEAR)
    pixels = np.asarray(gray, dtype=np.float32) / 255.0
    return ((pixels - 0.5) / 0.5).reshape(1, 784)


class WaterClassifier:
    class_names = ("turbid", "clear")

    def __init__(self, model_path: str | Path) -> None:
        import torch

        self.model_path = Path(model_path).resolve()
        if not self.model_path.is_file():
            raise FileNotFoundError(f"Water checkpoint not found: {self.model_path}; use --water-model.")
        try:
            state = torch.load(self.model_path, map_location="cpu", weights_only=True)
            self.model = torch.nn.Linear(784, 2)
            self.model.load_state_dict({"weight": state["linear.weight"], "bias": state["linear.bias"]})
            self.model.eval()
        except (KeyError, TypeError, RuntimeError) as error:
            raise ValueError(f"Invalid water checkpoint {self.model_path}: expected Linear(784, 2) state_dict.") from error
        if not all(torch.isfinite(value).all() for value in self.model.parameters()):
            raise ValueError(f"Non-finite parameters in water checkpoint: {self.model_path}")

    def predict(self, image) -> dict:
        import torch

        tensor = torch.from_numpy(preprocess_water(image))
        with torch.inference_mode():
            logits = self.model(tensor)
            index = int(torch.argmax(logits, dim=1).item())
            confidence = float(torch.softmax(logits, dim=1)[0, index].item())
        return {"water_label": self.class_names[index], "water_confidence": confidence}
