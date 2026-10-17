import sys


def main() -> int:
    try:
        import torch
        import torchvision
        from torchvision.ops import nms

        print(f"PyTorch: {torch.__version__}")
        print(f"torchvision: {torchvision.__version__}")
        print(f"CUDA runtime: {torch.version.cuda}")
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable; install the CUDA requirements and check the NVIDIA driver.")
        device = torch.device("cuda:0")
        print(f"GPU: {torch.cuda.get_device_name(device)}")
        sample = torch.ones((32, 32), device=device)
        if (sample @ sample)[0, 0].item() != 32.0:
            raise RuntimeError("CUDA matrix calculation failed.")
        boxes = torch.tensor([[0., 0., 10., 10.], [1., 1., 9., 9.]], device=device)
        scores = torch.tensor([0.9, 0.8], device=device)
        if nms(boxes, scores, 0.5).tolist() != [0]:
            raise RuntimeError("torchvision CUDA NMS failed.")
        torch.cuda.synchronize(device)
        print("CUDA tensor and torchvision operator checks passed.")
        return 0
    except Exception as exc:
        print(f"GPU verification failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
