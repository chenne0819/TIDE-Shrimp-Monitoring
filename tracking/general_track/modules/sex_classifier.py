from __future__ import annotations

import pickle
from collections import OrderedDict
from pathlib import Path

import cv2
import numpy as np
import torch
from torch import nn
from torchvision import models
from torchvision.ops import FeaturePyramidNetwork
from ultralytics import YOLO


REQUIRED_SEX_CLASSES = {"female", "male"}


class ResNet50FPNClassifier(nn.Module):
    def __init__(self, num_classes: int, dropout: float = 0.5, fpn_channels: int = 256) -> None:
        super().__init__()
        resnet = models.resnet50(weights=None)
        self.stem = nn.Sequential(resnet.conv1, resnet.bn1, resnet.relu, resnet.maxpool)
        self.layer1 = resnet.layer1
        self.layer2 = resnet.layer2
        self.layer3 = resnet.layer3
        self.layer4 = resnet.layer4
        self.fpn = FeaturePyramidNetwork(
            in_channels_list=[256, 512, 1024, 2048],
            out_channels=fpn_channels,
        )
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.classifier = nn.Sequential(
            nn.Dropout(dropout),
            nn.Linear(fpn_channels * 4, num_classes),
        )

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        x = self.stem(inputs)
        c2 = self.layer1(x)
        c3 = self.layer2(c2)
        c4 = self.layer3(c3)
        c5 = self.layer4(c4)
        features = self.fpn(OrderedDict([("c2", c2), ("c3", c3), ("c4", c4), ("c5", c5)]))
        pooled = [self.pool(features[name]).flatten(1) for name in ("c2", "c3", "c4", "c5")]
        return self.classifier(torch.cat(pooled, dim=1))


class ShrimpSexClassifier:
    """Load the female/male ResNet18 checkpoint used by the training pipeline."""

    def __init__(self, model_path: str, device: str | None = None) -> None:
        self.path = Path(model_path)
        if not self.path.exists():
            raise FileNotFoundError(f"Sex classifier not found: {self.path}")
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        checkpoint = torch.load(self.path, map_location=self.device)
        self.class_to_idx = checkpoint["class_to_idx"]
        if set(self.class_to_idx) != REQUIRED_SEX_CLASSES:
            raise ValueError(f"Expected CNN classes {sorted(REQUIRED_SEX_CLASSES)}, got {self.class_to_idx}")
        self.architecture = str(checkpoint.get("architecture", checkpoint.get("model", "resnet18"))).lower()

        self.image_size = int(checkpoint.get("image_size", 128))
        self.grayscale = bool(checkpoint.get("grayscale", False))
        if self.architecture == "resnet18":
            model = models.resnet18(weights=None)
        elif self.architecture == "resnet34":
            model = models.resnet34(weights=None)
        elif self.architecture == "resnet50":
            model = models.resnet50(weights=None)
        elif self.architecture == "resnet50_fpn":
            model = ResNet50FPNClassifier(
                num_classes=len(self.class_to_idx),
                dropout=float(checkpoint.get("dropout", 0.5)),
                fpn_channels=int(checkpoint.get("fpn_channels", 256)),
            )
        else:
            raise ValueError(f"Unsupported classifier architecture: {self.architecture}")
        state_dict = checkpoint["model_state"]
        if self.architecture == "resnet50_fpn":
            pass
        elif "fc.1.weight" in state_dict:
            model.fc = torch.nn.Sequential(
                torch.nn.Dropout(float(checkpoint.get("dropout", 0.5))),
                torch.nn.Linear(model.fc.in_features, len(self.class_to_idx)),
            )
        elif "fc.weight" in state_dict:
            model.fc = torch.nn.Linear(model.fc.in_features, len(self.class_to_idx))
        else:
            raise ValueError("Unsupported classifier head format: expected fc.weight or fc.1.weight")
        model.load_state_dict(state_dict)
        self.model = model.to(self.device).eval()
        self.labels = {index: name for name, index in self.class_to_idx.items()}
        self.mean = torch.tensor([0.485, 0.456, 0.406], device=self.device).view(1, 3, 1, 1)
        self.std = torch.tensor([0.229, 0.224, 0.225], device=self.device).view(1, 3, 1, 1)

    def predict(self, crop_bgr: np.ndarray) -> tuple[str, float, float]:
        if crop_bgr is None or crop_bgr.size == 0:
            raise ValueError("Cannot classify an empty crop")
        image = cv2.resize(crop_bgr, (self.image_size, self.image_size), interpolation=cv2.INTER_AREA)
        if self.grayscale:
            image = cv2.cvtColor(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        tensor = torch.from_numpy(rgb).permute(2, 0, 1).unsqueeze(0).to(self.device)
        tensor = (tensor - self.mean) / self.std
        with torch.no_grad():
            probabilities = torch.softmax(self.model(tensor), dim=1)[0]
        index = int(torch.argmax(probabilities).item())
        return self.labels[index], float(probabilities[index]), float(probabilities[self.class_to_idx["male"]])


class YoloShrimpSexClassifier:
    """Female/male classifier backed by an Ultralytics YOLO classification model."""

    def __init__(self, model_path: str) -> None:
        self.path = Path(model_path)
        if not self.path.exists():
            raise FileNotFoundError(f"YOLO sex classifier not found: {self.path}")
        self.model = YOLO(str(self.path))
        if self.model.task != "classify":
            raise ValueError(f"Expected a YOLO classification model, got task: {self.model.task}")
        self.class_to_idx = {name: int(index) for index, name in self.model.names.items()}
        if set(self.class_to_idx) != REQUIRED_SEX_CLASSES:
            raise ValueError(f"Expected YOLO classes {sorted(REQUIRED_SEX_CLASSES)}, got {self.class_to_idx}")
        self.architecture = "yolo-classify"
        model_args = getattr(self.model.model, "args", {}) or {}
        self.image_size = int(model_args.get("imgsz", 224))

    def predict(self, crop_bgr: np.ndarray) -> tuple[str, float, float]:
        if crop_bgr is None or crop_bgr.size == 0:
            raise ValueError("Cannot classify an empty crop")
        result = self.model.predict(crop_bgr, imgsz=self.image_size, verbose=False)[0]
        if result.probs is None:
            raise ValueError("YOLO classification model returned no probabilities")
        probabilities = result.probs.data.detach().cpu().numpy()
        index = int(np.argmax(probabilities))
        label = self.model.names[index]
        return label, float(probabilities[index]), float(probabilities[self.class_to_idx["male"]])


def load_sex_classifier(model_path: str):
    """Load a custom ResNet checkpoint or fall back to Ultralytics classification."""
    try:
        return ShrimpSexClassifier(model_path)
    except (KeyError, TypeError, RuntimeError, ValueError, pickle.UnpicklingError) as resnet_error:
        try:
            return YoloShrimpSexClassifier(model_path)
        except Exception:
            raise resnet_error
