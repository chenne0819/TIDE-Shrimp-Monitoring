from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn
from torchvision import models


class TinyCNN(nn.Module):
    def __init__(self, num_classes=2, dropout=0.35):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(3, 32, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(32),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
            nn.Conv2d(32, 64, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
            nn.Conv2d(64, 128, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(128),
            nn.ReLU(inplace=True),
            nn.AdaptiveAvgPool2d(1),
        )
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Dropout(dropout),
            nn.Linear(128, num_classes),
        )

    def forward(self, x):
        return self.classifier(self.features(x))


def build_resnet18(num_classes: int, dropout: float = 0.30):
    model = models.resnet18(weights=None)
    in_features = model.fc.in_features
    model.fc = nn.Sequential(
        nn.Dropout(p=dropout),
        nn.Linear(in_features, num_classes),
    )
    return model


def build_classifier_model(model_name: str, num_classes: int):
    model_name = (model_name or "tiny_cnn").lower()
    if model_name == "resnet18":
        return build_resnet18(num_classes)
    if model_name in {"tinycnn", "tiny_cnn"}:
        return TinyCNN(num_classes=num_classes)
    raise ValueError(f"Unsupported CNN checkpoint model type: {model_name}")


class MaleLineCNNClassifier:
    def __init__(self, model_path: str, threshold: float | None = None, device: str | None = None) -> None:
        self.model_path = Path(model_path)
        if not self.model_path.exists():
            raise FileNotFoundError(f"CNN model not found: {self.model_path}")

        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        checkpoint = torch.load(self.model_path, map_location=self.device)
        checkpoint_threshold = (
            checkpoint.get("threshold")
            or checkpoint.get("confidence_threshold")
            or checkpoint.get("male_line_threshold")
            or checkpoint.get("best_threshold")
            or 0.5
        )
        self.threshold = float(checkpoint_threshold if threshold is None else threshold)
        self.model_name = checkpoint.get("model", "tiny_cnn")
        self.class_to_idx = checkpoint.get("class_to_idx", {"male_line": 0, "no_male_line": 1})
        self.image_size = int(checkpoint.get("image_size", 32))
        self.grayscale = bool(checkpoint.get("grayscale", False))
        self.male_index = int(self.class_to_idx.get("male_line", 0))

        self.model = build_classifier_model(self.model_name, num_classes=len(self.class_to_idx)).to(self.device)
        self.model.load_state_dict(checkpoint["model_state"])
        self.model.eval()

        self.mean = torch.tensor([0.485, 0.456, 0.406], dtype=torch.float32, device=self.device).view(1, 3, 1, 1)
        self.std = torch.tensor([0.229, 0.224, 0.225], dtype=torch.float32, device=self.device).view(1, 3, 1, 1)

    @staticmethod
    def crop_hbb_box(image: np.ndarray, box_xyxy: list[float] | tuple[float, float, float, float] | None):
        if box_xyxy is None or image is None or image.size == 0:
            return None
        height, width = image.shape[:2]
        x1, y1, x2, y2 = [int(round(float(v))) for v in box_xyxy]
        x1 = max(0, min(x1, width - 1))
        y1 = max(0, min(y1, height - 1))
        x2 = max(x1 + 1, min(x2, width))
        y2 = max(y1 + 1, min(y2, height))
        crop = image[y1:y2, x1:x2]
        return crop if crop.size else None

    def predict_crop(self, crop_bgr: np.ndarray) -> tuple[bool, float]:
        if crop_bgr is None or crop_bgr.size == 0:
            return False, 0.0

        resized = cv2.resize(crop_bgr, (self.image_size, self.image_size), interpolation=cv2.INTER_AREA)
        if self.grayscale:
            resized = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
            resized = cv2.cvtColor(resized, cv2.COLOR_GRAY2BGR)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        tensor = torch.from_numpy(rgb).permute(2, 0, 1).unsqueeze(0).to(self.device)
        tensor = (tensor - self.mean) / self.std

        with torch.no_grad():
            logits = self.model(tensor)
            probs = torch.softmax(logits, dim=1)[0]
            male_prob = float(probs[self.male_index].item())
        return male_prob >= self.threshold, male_prob
