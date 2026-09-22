from project_paths import project_path

MODEL_HEAD_TAIL_OBB_PATH = project_path("model/yolo/best-obb-yolo11m-head_tail.pt")
MODEL_HBB_PATH = project_path("model/yolo/best-hbb-yolo11n.pt")
MODEL_YOLO_CLS_PATH = project_path("model/yolo/best-cls-yolo11m-run3.pt")
MODEL_CNN_PATH = project_path("model/cnn/best_resnet18-run3.pt")
# Use the classifier supplied with this local model bundle by default.
# MODEL_YOLO_CLS_PATH remains available as an optional --classifier-model choice.
MODEL_SEX_CLASSIFIER_PATH = MODEL_CNN_PATH

IMGSZ_OBB = 640
IMGSZ_HBB = 416
HBB_CONF = 0.5
MIN_OBSERVATIONS_PER_SHRIMP = 3
