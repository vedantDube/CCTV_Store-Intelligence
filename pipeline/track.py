import numpy as np
from deep_sort_realtime.deepsort_tracker import DeepSort
from pipeline.detect import DetectionResult

class TrackResult:
    def __init__(self, track_id: int, detection: DetectionResult):
        self.track_id = track_id
        self.detection = detection

class DeepSORTTracker:
    def __init__(self, reid_weights: str = "models/osnet_x0_25_market1501.pt", device: str = "cpu"):
        import torch
        if device == "cuda" and not torch.cuda.is_available():
            device = "cpu"
        self.tracker = DeepSort(
            max_age=30,
            n_init=3,
            nms_max_overlap=1.0,
            max_cosine_distance=0.2,
            nn_budget=None,
            embedder="torchreid",
            embedder_model_name="osnet_x0_25",
            bgr=True,
            embedder_gpu=(device == "cuda"),
            embedder_wts=reid_weights
        )

    def track(self, detections: list[DetectionResult], frame: np.ndarray) -> list[TrackResult]:
        # Formulate detections for deep-sort-realtime: List of ([left, top, w, h], confidence, detection_obj)
        raw_detections = []
        for det in detections:
            x1, y1, x2, y2 = det.bbox
            w = max(0.0, x2 - x1)
            h = max(0.0, y2 - y1)
            # Pass the det object itself as the third element
            raw_detections.append(([x1, y1, w, h], det.confidence, det))

        # Update tracker
        tracks = self.tracker.update_tracks(raw_detections, frame=frame)

        results = []
        for track in tracks:
            if not track.is_confirmed():
                continue
            
            track_id = int(track.track_id) if (isinstance(track.track_id, str) and track.track_id.isdigit()) else track.track_id
            
            # Retrieve the associated detection object
            det_obj = track.get_det_class()
            if isinstance(det_obj, DetectionResult):
                # Update its bounding box to the tracked bounding box
                tlbr = track.to_tlbr()
                det_obj.bbox = [float(tlbr[0]), float(tlbr[1]), float(tlbr[2]), float(tlbr[3])]
                results.append(TrackResult(track_id=track_id, detection=det_obj))
            else:
                # Fallback IoU matching in case get_det_class() is not our object
                tlbr = track.to_tlbr()
                best_det = None
                best_iou = 0.0
                track_bbox = [float(tlbr[0]), float(tlbr[1]), float(tlbr[2]), float(tlbr[3])]
                
                for det in detections:
                    # Calculate IoU
                    x1 = max(track_bbox[0], det.bbox[0])
                    y1 = max(track_bbox[1], det.bbox[1])
                    x2 = min(track_bbox[2], det.bbox[2])
                    y2 = min(track_bbox[3], det.bbox[3])
                    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
                    area1 = (track_bbox[2] - track_bbox[0]) * (track_bbox[3] - track_bbox[1])
                    area2 = (det.bbox[2] - det.bbox[0]) * (det.bbox[3] - det.bbox[1])
                    union = area1 + area2 - intersection
                    iou_val = intersection / union if union > 0 else 0.0
                    if iou_val > best_iou:
                        best_iou = iou_val
                        best_det = det
                
                if best_det is not None and best_iou > 0.3:
                    best_det.bbox = track_bbox
                    results.append(TrackResult(track_id=track_id, detection=best_det))
                else:
                    # Fallback to creating a new one if no match
                    conf = track.get_det_conf() if track.get_det_conf() is not None else 1.0
                    cls_name = track.get_det_class() if isinstance(track.get_det_class(), str) else "unknown"
                    fallback_det = DetectionResult(
                        class_id=-1,
                        class_name=cls_name,
                        confidence=conf,
                        bbox=track_bbox
                    )
                    results.append(TrackResult(track_id=track_id, detection=fallback_det))
                    
        return results
