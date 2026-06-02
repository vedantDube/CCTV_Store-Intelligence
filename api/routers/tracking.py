from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import JSONResponse
import cv2
import numpy as np
import json
from sqlmodel.ext.asyncio.session import AsyncSession

from pipeline.detect import YOLOv8Detector
from pipeline.track import DeepSORTTracker
from pipeline.zone_classifier import ZoneClassifier
from api.db import get_session, Detection, Track

detector = YOLOv8Detector(weights_path="models/yolov8m.pt", device="cuda")
tracker = DeepSORTTracker(reid_weights="models/osnet_x0_25_market1501.pt", device="cuda")
zone_classifier = ZoneClassifier()

router = APIRouter(prefix="/track")

def _read_image(upload: UploadFile) -> np.ndarray:
    try:
        contents = upload.file.read()
        np_arr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Unable to decode image")
        return img
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/", response_class=JSONResponse)
async def track_endpoint(file: UploadFile = File(...), session: AsyncSession = Depends(get_session)):
    img = _read_image(file)
    detections = detector.detect(img)
    tracks = tracker.track(detections, img)
    
    resp = []
    try:
        for t in tracks:
            zone_name = zone_classifier.classify(t.detection.bbox, t.detection.class_name)
            
            db_det = Detection(
                class_id=t.detection.class_id,
                class_name=t.detection.class_name,
                confidence=round(t.detection.confidence, 4),
                bbox=json.dumps(t.detection.bbox)
            )
            session.add(db_det)
            await session.flush()
            
            db_track = Track(
                track_id=t.track_id,
                detection_id=db_det.id,
                class_id=t.detection.class_id,
                class_name=t.detection.class_name,
                confidence=round(t.detection.confidence, 4),
                bbox=json.dumps(t.detection.bbox),
                zone=zone_name
            )
            session.add(db_track)
            
            resp.append({
                "track_id": t.track_id,
                "class_id": t.detection.class_id,
                "class_name": t.detection.class_name,
                "confidence": round(t.detection.confidence, 4),
                "bbox": t.detection.bbox,
                "zone": zone_name
            })
        await session.commit()
    except Exception as e:
        print(f"Database write skipped or failed: {e}")
        resp = []
        for t in tracks:
            zone_name = zone_classifier.classify(t.detection.bbox, t.detection.class_name)
            resp.append({
                "track_id": t.track_id,
                "class_id": t.detection.class_id,
                "class_name": t.detection.class_name,
                "confidence": round(t.detection.confidence, 4),
                "bbox": t.detection.bbox,
                "zone": zone_name
            })
            
    return JSONResponse(content={"tracks": resp})
