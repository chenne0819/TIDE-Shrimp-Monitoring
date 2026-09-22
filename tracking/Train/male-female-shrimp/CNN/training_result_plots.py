from pathlib import Path

import numpy as np


def _ordered_labels(class_to_idx):
    return [name for name, _ in sorted(class_to_idx.items(), key=lambda item: item[1])]


def _save_line_plot(plt, epochs, series, title, ylabel, path, ylim=None):
    figure, axis = plt.subplots(figsize=(7, 5))
    for label, values in series.items():
        axis.plot(epochs, values, label=label)
    axis.set(title=title, xlabel="epoch", ylabel=ylabel)
    if ylim is not None:
        axis.set_ylim(*ylim)
    axis.grid(alpha=0.25)
    axis.legend()
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def _save_confusion_plot(plt, matrix, labels, title, path, value_format):
    figure, axis = plt.subplots(figsize=(6, 5))
    image = axis.imshow(matrix, cmap="Blues", vmin=0)
    axis.set(
        title=title,
        xlabel="predicted class",
        ylabel="true class",
        xticks=np.arange(len(labels)),
        yticks=np.arange(len(labels)),
        xticklabels=labels,
        yticklabels=labels,
    )
    threshold = float(matrix.max()) / 2 if matrix.size else 0
    for row in range(len(labels)):
        for column in range(len(labels)):
            value = matrix[row, column]
            axis.text(
                column,
                row,
                value_format.format(value),
                ha="center",
                va="center",
                color="white" if value > threshold else "black",
            )
    figure.colorbar(image, ax=axis, fraction=0.046, pad=0.04)
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def save_training_result_figures(history, confusion, class_to_idx, output_dir):
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib is unavailable; skipping result figures.")
        return

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    labels = _ordered_labels(class_to_idx)
    epochs = [int(row["epoch"]) for row in history]
    train_loss = [float(row["train_loss"]) for row in history]
    val_loss = [float(row["val_loss"]) for row in history]
    train_acc = [float(row["train_acc"]) for row in history]
    val_acc = [float(row["val_acc"]) for row in history]

    _save_line_plot(
        plt,
        epochs,
        {"train": train_loss, "val": val_loss},
        "Training and validation loss",
        "loss",
        output_dir / "training_loss.png",
    )
    _save_line_plot(
        plt,
        epochs,
        {"train": train_acc, "val": val_acc},
        "Training and validation accuracy",
        "accuracy",
        output_dir / "training_accuracy.png",
        ylim=(0, 1),
    )

    figure, axes = plt.subplots(1, 2, figsize=(10, 4))
    axes[0].plot(epochs, train_loss, label="train")
    axes[0].plot(epochs, val_loss, label="val")
    axes[0].set(xlabel="epoch", ylabel="loss")
    axes[0].legend()
    axes[1].plot(epochs, train_acc, label="train")
    axes[1].plot(epochs, val_acc, label="val")
    axes[1].set(xlabel="epoch", ylabel="accuracy", ylim=(0, 1))
    axes[1].legend()
    figure.tight_layout()
    figure.savefig(output_dir / "training_curves.png", dpi=160)
    plt.close(figure)

    confusion_array = np.asarray(
        confusion.cpu().numpy() if hasattr(confusion, "cpu") else confusion,
        dtype=np.float64,
    )
    _save_confusion_plot(
        plt,
        confusion_array,
        labels,
        "Test confusion matrix",
        output_dir / "confusion_matrix.png",
        "{:.0f}",
    )
    row_totals = confusion_array.sum(axis=1, keepdims=True)
    normalized = np.divide(
        confusion_array,
        row_totals,
        out=np.zeros_like(confusion_array),
        where=row_totals > 0,
    )
    _save_confusion_plot(
        plt,
        normalized,
        labels,
        "Normalized test confusion matrix",
        output_dir / "confusion_matrix_normalized.png",
        "{:.3f}",
    )

    true_totals = confusion_array.sum(axis=1)
    predicted_totals = confusion_array.sum(axis=0)
    diagonal = np.diag(confusion_array)
    precision = np.divide(diagonal, predicted_totals, out=np.zeros_like(diagonal), where=predicted_totals > 0)
    recall = np.divide(diagonal, true_totals, out=np.zeros_like(diagonal), where=true_totals > 0)
    f1 = np.divide(2 * precision * recall, precision + recall, out=np.zeros_like(diagonal), where=(precision + recall) > 0)

    x_positions = np.arange(len(labels))
    bar_width = 0.25
    figure, axis = plt.subplots(figsize=(8, 5))
    axis.bar(x_positions - bar_width, precision, bar_width, label="precision")
    axis.bar(x_positions, recall, bar_width, label="recall")
    axis.bar(x_positions + bar_width, f1, bar_width, label="F1")
    axis.set(
        title="Per-class test metrics",
        xlabel="class",
        ylabel="score",
        xticks=x_positions,
        xticklabels=labels,
        ylim=(0, 1),
    )
    axis.grid(axis="y", alpha=0.25)
    axis.legend()
    figure.tight_layout()
    figure.savefig(output_dir / "per_class_metrics.png", dpi=160)
    plt.close(figure)

    if history and "lr" in history[0]:
        lr_series = {"learning rate": [float(row["lr"]) for row in history]}
    elif history and "backbone_lr" in history[0] and "classifier_lr" in history[0]:
        lr_series = {
            "backbone": [float(row["backbone_lr"]) for row in history],
            "classifier": [float(row["classifier_lr"]) for row in history],
        }
    else:
        lr_series = None
    if lr_series:
        _save_line_plot(
            plt,
            epochs,
            lr_series,
            "Learning rate schedule",
            "learning rate",
            output_dir / "learning_rate.png",
        )
