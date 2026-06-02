from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import JSONResponse
import cv2
import numpy as np
import json
from sqlmodel.ext.asyncio.session import AsyncSession

from pipeline.detect import YOLOv8Detector
from api.db import get_session, Detection

detector = YOLOv8Detector(weights_path="models/yolov8m.pt", device="cuda")

router = APIRouter(prefix="/detect")
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
async def detect_endpoint(file: UploadFile = File(...), session: AsyncSession = Depends(get_session)):
    img = _read_image(file)
    detections = detector.detect(img)
    db_detections = []
    resp = []
    for d in detections:
        db_det = Detection(
            class_id=d.class_id,
            class_name=d.class_name,
            confidence=round(d.confidence, 4),
            bbox=json.dumps(d.bbox)
        )
        db_detections.append(db_det)
        resp.append({
            "class_id": d.class_id,
            "class_name": d.class_name,
            "confidence": round(d.confidence, 4),
            "bbox": d.bbox,
        })
    
    try:
        session.add_all(db_detections)
        await session.commit()
    except Exception as e:
        print(f"Database write skipped or failed: {e}")
        
    return JSONResponse(content={"detections": resp})
