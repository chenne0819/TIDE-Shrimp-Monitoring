import argparse
import copy
import csv
import json
import random
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.optim import SGD
from torch.optim.lr_scheduler import StepLR
from torch.utils.data import DataLoader
from torchvision import datasets, models
from torchvision.transforms import v2
from torchvision.transforms.v2 import functional as transform_functional
from tqdm import tqdm

try:
    from training_result_plots import save_training_result_figures
except ImportError:
    from CNN.training_result_plots import save_training_result_figures


def parse_args():
    parser = argparse.ArgumentParser(description="Fine-tune torchvision ResNet18.")
    parser.add_argument("--data", default="CNN_dataset4")
    parser.add_argument("--output", default="runs/resnet18_5")
    parser.add_argument("--image-size", type=int, default=96)
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--momentum", type=float, default=0.9)
    parser.add_argument("--step-size", type=int, default=7)
    parser.add_argument("--gamma", type=float, default=0.1)
    parser.add_argument("--dropout", type=float, default=0.5)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--num-workers", type=int, default=0, help="Use 0 on Windows.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--no-pretrained", action="store_true")
    parser.add_argument("--no-augment", action="store_true")
    return parser.parse_args()


def resolve_path(value, base_dir):
    path = Path(value)
    return path if path.is_absolute() else (base_dir / path).resolve()


def set_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


class RandomLineOcclusion:
    def __init__(self, probability=0.35, max_lines=3, max_thickness=2):
        self.probability = probability
        self.max_lines = max_lines
        self.max_thickness = max_thickness

    def __call__(self, image):
        if random.random() >= self.probability:
            return image
        image = image.clone()
        _, height, width = transform_functional.get_dimensions(image)
        line_count = random.randint(1, self.max_lines)
        for _ in range(line_count):
            x1 = random.randrange(width)
            x2 = random.randrange(width)
            y1 = random.randrange(height)
            y2 = min(max(y1 + random.randint(-height // 4, height // 4), 0), height - 1)
            steps = max(abs(x2 - x1), abs(y2 - y1), 1) + 1
            xs = torch.linspace(x1, x2, steps, device=image.device).round().long().clamp(0, width - 1)
            ys = torch.linspace(y1, y2, steps, device=image.device).round().long().clamp(0, height - 1)
            color = torch.randint(70, 230, (1,), dtype=image.dtype, device=image.device).expand(image.shape[0], 1)
            thickness = random.randint(1, self.max_thickness)
            for offset in range(-thickness, thickness + 1):
                yy = (ys + offset).clamp(0, height - 1)
                image[:, yy, xs] = color
        return image


def build_transforms(image_size, augment):
    normalize = v2.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    eval_transform = v2.Compose(
        [
            v2.ToImage(),
            v2.Resize((image_size, image_size), antialias=True),
            v2.ToDtype(torch.float32, scale=True),
            normalize,
        ]
    )
    if not augment:
        return eval_transform, eval_transform
    train_transform = v2.Compose(
        [
            v2.ToImage(),
            v2.Resize((image_size, image_size), antialias=True),
            v2.RandomApply([v2.ColorJitter(brightness=0.30, contrast=0.30, saturation=0.20, hue=0.03)], p=0.80),
            v2.RandomAutocontrast(p=0.25),
            v2.RandomAdjustSharpness(sharpness_factor=1.8, p=0.25),
            v2.RandomGrayscale(p=0.20),
            v2.RandomAffine(degrees=7, translate=(0.05, 0.05), scale=(0.94, 1.06), shear=(-3, 3), fill=255),
            v2.RandomApply([v2.GaussianBlur(kernel_size=3, sigma=(0.1, 1.3))], p=0.25),
            RandomLineOcclusion(probability=0.35, max_lines=3, max_thickness=1),
            v2.ToDtype(torch.float32, scale=True),
            v2.RandomErasing(p=0.25, scale=(0.01, 0.05), ratio=(0.2, 3.0), value=1.0),
            normalize,
        ]
    )
    return train_transform, eval_transform


def build_loaders(data_dir, image_size, batch_size, num_workers, augment):
    train_transform, eval_transform = build_transforms(image_size, augment)
    split_transforms = {"train": train_transform, "val": eval_transform, "test": eval_transform}
    split_datasets = {
        split: datasets.ImageFolder(data_dir / split, transform=transform)
        for split, transform in split_transforms.items()
    }
    class_to_idx = split_datasets["train"].class_to_idx
    for split, dataset in split_datasets.items():
        if not dataset.samples:
            raise ValueError(f"No images found in: {data_dir / split}")
        if dataset.class_to_idx != class_to_idx:
            raise ValueError(f"Class folders in {split} differ from train.")
    loaders = {
        split: DataLoader(
            dataset,
            batch_size=batch_size,
            shuffle=split == "train",
            num_workers=num_workers,
            pin_memory=torch.cuda.is_available(),
        )
        for split, dataset in split_datasets.items()
    }
    return loaders, class_to_idx


def build_model(num_classes, pretrained, dropout):
    weights = models.ResNet18_Weights.DEFAULT if pretrained else None
    model = models.resnet18(weights=weights)
    model.fc = nn.Sequential(nn.Dropout(dropout), nn.Linear(model.fc.in_features, num_classes))
    return model


def run_phase(model, loader, criterion, optimizer, device, training):
    model.train(training)
    running_loss = 0.0
    running_correct = 0
    for inputs, labels in tqdm(loader, leave=False, desc="train" if training else "val"):
        inputs = inputs.to(device)
        labels = labels.to(device)
        optimizer.zero_grad(set_to_none=True)
        with torch.set_grad_enabled(training):
            outputs = model(inputs)
            loss = criterion(outputs, labels)
            predictions = outputs.argmax(dim=1)
            if training:
                loss.backward()
                optimizer.step()
        running_loss += loss.item() * inputs.size(0)
        running_correct += (predictions == labels).sum().item()
    dataset_size = len(loader.dataset)
    return running_loss / dataset_size, running_correct / dataset_size


@torch.no_grad()
def evaluate(model, loader, criterion, device, num_classes):
    model.eval()
    running_loss = 0.0
    running_correct = 0
    confusion = torch.zeros(num_classes, num_classes, dtype=torch.int64)
    for inputs, labels in tqdm(loader, leave=False, desc="test"):
        inputs = inputs.to(device)
        labels = labels.to(device)
        outputs = model(inputs)
        loss = criterion(outputs, labels)
        predictions = outputs.argmax(dim=1)
        running_loss += loss.item() * inputs.size(0)
        running_correct += (predictions == labels).sum().item()
        for true_label, predicted_label in zip(labels.cpu(), predictions.cpu()):
            confusion[true_label, predicted_label] += 1
    dataset_size = len(loader.dataset)
    return running_loss / dataset_size, running_correct / dataset_size, confusion


def save_results(history, confusion, class_to_idx, output_dir, metrics):
    with (output_dir / "history.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=history[0].keys())
        writer.writeheader()
        writer.writerows(history)
    labels = [name for name, _ in sorted(class_to_idx.items(), key=lambda item: item[1])]
    with (output_dir / "confusion_matrix.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["true\\pred", *labels])
        for label, row in zip(labels, confusion.tolist()):
            writer.writerow([label, *row])
    with (output_dir / "metrics.json").open("w", encoding="utf-8") as file:
        json.dump(metrics, file, indent=2, ensure_ascii=False)
    save_training_result_figures(history, confusion, class_to_idx, output_dir)


def main():
    args = parse_args()
    if min(args.epochs, args.batch_size, args.image_size, args.step_size) <= 0:
        raise ValueError("Epochs, batch size, image size, and step size must be positive.")
    if args.lr <= 0 or args.weight_decay < 0 or not 0 <= args.dropout < 1 or not 0 < args.gamma <= 1:
        raise ValueError("Invalid learning rate, dropout, weight decay, or gamma.")

    set_seed(args.seed)
    script_dir = Path(__file__).resolve().parent
    data_dir = resolve_path(args.data, script_dir)
    output_dir = resolve_path(args.output, script_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    loaders, class_to_idx = build_loaders(
        data_dir, args.image_size, args.batch_size, args.num_workers, not args.no_augment
    )
    model = build_model(len(class_to_idx), not args.no_pretrained, args.dropout).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = SGD(model.parameters(), lr=args.lr, momentum=args.momentum, weight_decay=args.weight_decay)
    scheduler = StepLR(optimizer, step_size=args.step_size, gamma=args.gamma)

    best_weights = copy.deepcopy(model.state_dict())
    best_val_loss = float("inf")
    best_val_acc = 0.0
    best_epoch = 0
    history = []
    checkpoint_path = output_dir / "best_resnet18.pt"

    print(f"Data: {data_dir}\nOutput: {output_dir}\nDevice: {device}\nClasses: {class_to_idx}")
    for epoch in range(1, args.epochs + 1):
        print(f"Epoch {epoch}/{args.epochs}")
        train_loss, train_acc = run_phase(model, loaders["train"], criterion, optimizer, device, True)
        val_loss, val_acc = run_phase(model, loaders["val"], criterion, optimizer, device, False)
        current_lr = optimizer.param_groups[0]["lr"]
        history.append(
            {"epoch": epoch, "train_loss": train_loss, "train_acc": train_acc,
             "val_loss": val_loss, "val_acc": val_acc, "lr": current_lr}
        )
        print(f"  train {train_loss:.4f}/{train_acc:.4f} | val {val_loss:.4f}/{val_acc:.4f}")
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_val_acc = val_acc
            best_epoch = epoch
            best_weights = copy.deepcopy(model.state_dict())
            torch.save(
                {"architecture": "resnet18", "model_state": best_weights, "class_to_idx": class_to_idx,
                 "image_size": args.image_size, "dropout": args.dropout,
                 "weight_decay": args.weight_decay, "best_epoch": best_epoch,
                 "best_val_loss": best_val_loss, "best_val_acc": best_val_acc},
                checkpoint_path,
            )
        scheduler.step()

    model.load_state_dict(best_weights)
    test_loss, test_acc, confusion = evaluate(model, loaders["test"], criterion, device, len(class_to_idx))
    metrics = {"architecture": "resnet18", "best_epoch": best_epoch, "best_val_loss": best_val_loss,
               "best_val_acc": best_val_acc,
               "test_loss": test_loss, "test_acc": test_acc, "class_to_idx": class_to_idx,
               "confusion_matrix": confusion.tolist(), "image_size": args.image_size,
               "dropout": args.dropout, "weight_decay": args.weight_decay}
    save_results(history, confusion, class_to_idx, output_dir, metrics)
    print(f"Best epoch: {best_epoch} | Test loss: {test_loss:.4f} | Test acc: {test_acc:.4f}")


if __name__ == "__main__":
    main()
