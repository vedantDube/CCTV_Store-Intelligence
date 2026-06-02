import cv2
import numpy as np
from ultralytics import YOLO

class DetectionResult:
    def __init__(self, class_id: int, class_name: str, confidence: float, bbox: list[float]):
        self.class_id = class_id
        self.class_name = class_name
        self.confidence = confidence
        self.bbox = bbox  # [x1, y1, x2, y2]

class YOLOv8Detector:
    def __init__(self, weights_path: str = "models/yolov8m.pt", device: str = "cpu"):
        import torch
        if device == "cuda" and not torch.cuda.is_available():
            device = "cpu"
        self.model = YOLO(weights_path)
        self.device = device

    def detect(self, img: np.ndarray) -> list[DetectionResult]:
        # Ultralytics YOLOv8 expects RGB or BGR? By default it takes BGR numpy arrays.
        # Run inference
        results = self.model(img, device=self.device, verbose=False)
        detections = []
        if not results:
            return detections
        
        result = results[0]
        boxes = result.boxes
        if boxes is not None:
            for box in boxes:
                # Get coords
                xyxy = box.xyxy[0].cpu().numpy().tolist()  # [x1, y1, x2, y2]
                conf = float(box.conf[0].cpu().item())
                cls_id = int(box.cls[0].cpu().item())
                cls_name = self.model.names[cls_id]
                detections.append(DetectionResult(
                    class_id=cls_id,
                    class_name=cls_name,
                    confidence=conf,
                    bbox=xyxy
                ))
        return detections
