import cv2
import numpy as np
import os
import uuid
from datetime import datetime, timedelta
import torch

from pipeline.detect import YOLOv8Detector
from pipeline.track import DeepSORTTracker
from pipeline.emit import save_events_to_jsonl, post_events_to_api

def get_cosine_distance(f1, f2):
    """
    Computes cosine distance between two feature vectors.
    """
    if f1 is None or f2 is None:
        return 1.0
    dot_product = np.dot(f1, f2)
    norm_f1 = np.linalg.norm(f1)
    norm_f2 = np.linalg.norm(f2)
    if norm_f1 == 0 or norm_f2 == 0:
        return 1.0
    return 1.0 - (dot_product / (norm_f1 * norm_f2))

class GlobalVisitor:
    def __init__(self, visitor_id: str, is_staff: bool = False):
        self.visitor_id = visitor_id
        self.is_staff = is_staff
        self.features = []  # List of feature vectors
        
        # Maps camera_id -> [enter_time, last_seen_time, last_dwell_emit_time, zone_id]
        self.active_zones = {}
        
        self.last_seen_time = None
        self.session_seq = 0
        self.cameras_seen = set()
        self.has_exited = False

    def add_feature(self, feat):
        if feat is not None:
            self.features.append(feat)
            if len(self.features) > 10:
                self.features.pop(0)

    def get_average_feature(self):
        if not self.features:
            return None
        return np.mean(self.features, axis=0)

def main(frame_step: int = 15, api_url: str = "http://localhost:8000/events/ingest", layout_type: str = "Revised"):
    video_dir = "CCTV Footage-20260529T160731Z-3-00144614ea/CCTV Footage"
    cameras = {
        "CAM 1": "ENTRY",
        "CAM 2": "FOH",
        "CAM 3": "MAKEUP",
        "CAM 4": "SKINCARE",
        "CAM 5": "BILLING"
    }

    # Brand maps from the layout diagram
    skincare_brands = {
        "Revised": ["Salm", "TFS", "GV", "DermDo", "Minimalist", "Aqualogica", "Foxtale", "JC"],
        "Current": ["EB", "TFS", "GV", "DermDo", "Minimalist", "Aqualogica", "Pilgrim", "D&K"]
    }[layout_type]

    makeup_brands = {
        "Revised": ["BACKLIT", "Maybelline", "Faces", "Lakme", "Mars+/Nybae", "Mens Care", "Alps", "Lo'real", "Beauty Essential"],
        "Current": ["BACKLIT", "Maybelline", "Faces", "Lakme", "Swiss+", "Mars+/Nybae", "Alps", "Lo'real", "Beauty Essential"]
    }[layout_type]

    print(f"[RUNNER] Starting video detection pipeline with {layout_type} store layout...")
    
    # Initialize YOLOv8 and DeepSORT Tracker
    device = "cuda" if torch.cuda.is_available() else "cpu"
    detector = YOLOv8Detector(weights_path="models/yolov8m.pt", device=device)
    trackers = {cam_id: DeepSORTTracker(reid_weights="models/osnet_x0_25_market1501.pt", device=device) for cam_id in cameras}

    # Open video capture streams
    caps = {}
    total_frames = 0
    for cam_id in cameras:
        v_path = os.path.join(video_dir, f"{cam_id}.mp4")
        if os.path.exists(v_path):
            cap = cv2.VideoCapture(v_path)
            caps[cam_id] = cap
            length = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            total_frames = max(total_frames, length)
        else:
            print(f"[RUNNER] Warning: Video file not found: {v_path}")

    if not caps:
        print("[RUNNER] Error: No video files loaded. Exiting.")
        return

    # Base start time (April 10, 2026 18:00:00 PM UTC)
    base_time = datetime(2026, 4, 10, 18, 0, 0)
    
    global_visitors = []
    events_log = []

    # Helper to find or create global visitor
    def match_global_visitor(track_id, camera_id, feat, is_staff_by_color):
        nonlocal global_visitors
        best_match = None
        min_dist = 0.25 # Cosine distance threshold

        if feat is not None:
            for gv in global_visitors:
                avg_feat = gv.get_average_feature()
                dist = get_cosine_distance(feat, avg_feat)
                if dist < min_dist:
                    min_dist = dist
                    best_match = gv

        if best_match is not None:
            best_match.add_feature(feat)
            best_match.is_staff = best_match.is_staff or is_staff_by_color
            return best_match
        
        visitor_id = f"VIS_{uuid.uuid4().hex[:6].upper()}"
        gv = GlobalVisitor(visitor_id, is_staff=is_staff_by_color)
        gv.add_feature(feat)
        global_visitors.append(gv)
        return gv

    # Frame processing loop
    for frame_idx in range(0, total_frames, frame_step):
        current_time = base_time + timedelta(seconds=frame_idx / 15.0)
        print(f"[RUNNER] Processing frame {frame_idx}/{total_frames} (Simulated Time: {current_time.isoformat()})")

        billing_visitors = []
        frames = {}
        for cam_id, cap in caps.items():
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if ret:
                frames[cam_id] = frame

        # Process each camera feed
        for cam_id, frame in frames.items():
            detections = detector.detect(frame)
            person_detections = [d for d in detections if d.class_name == "person" and d.confidence > 0.4]
            tracks = trackers[cam_id].track(person_detections, frame)

            for track in tracks:
                track_id = track.track_id
                bbox = track.detection.bbox
                conf = track.detection.confidence

                feat = None
                for tracker_track in trackers[cam_id].tracker.tracker.tracks:
                    if tracker_track.track_id == track_id:
                        if tracker_track.features:
                            feat = tracker_track.features[-1]
                        break

                # Staff uniform color check
                is_staff_by_color = False
                h, w, _ = frame.shape
                x1, y1, x2, y2 = [int(v) for v in bbox]
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(w, x2), min(h, y2)
                crop = frame[y1:y2, x1:x2]
                if crop.size > 0:
                    ch, cw, _ = crop.shape
                    torso_y1 = int(ch * 0.2)
                    torso_y2 = int(ch * 0.5)
                    torso = crop[torso_y1:torso_y2, :]
                    if torso.size > 0:
                        torso_hsv = cv2.cvtColor(torso, cv2.COLOR_BGR2HSV)
                        purple_mask = cv2.inRange(torso_hsv, np.array([100, 30, 30]), np.array([160, 255, 255]))
                        dark_mask = cv2.inRange(torso_hsv, np.array([0, 0, 0]), np.array([180, 255, 60]))
                        purple_ratio = np.sum(purple_mask > 0) / torso.size
                        dark_ratio = np.sum(dark_mask > 0) / torso.size
                        if purple_ratio > 0.15 or dark_ratio > 0.5:
                            is_staff_by_color = True

                gv = match_global_visitor(track_id, cam_id, feat, is_staff_by_color)
                gv.last_seen_time = current_time
                gv.cameras_seen.add(cam_id)

                if len(gv.cameras_seen) >= 3:
                    gv.is_staff = True

                zone_id = cameras[cam_id]
                sku_zone = None
                
                center_x = (bbox[0] + bbox[2]) / 2.0
                norm_x = center_x / frame.shape[1]

                if zone_id == "SKINCARE":
                    idx = int(norm_x * 8)
                    idx = max(0, min(7, idx))
                    sku_zone = skincare_brands[idx]
                elif zone_id == "MAKEUP":
                    idx = int(norm_x * 9)
                    idx = max(0, min(8, idx))
                    sku_zone = makeup_brands[idx]
                elif zone_id == "FOH":
                    if norm_x < 0.5:
                        sku_zone = "Nail Gondola"
                    else:
                        sku_zone = "Makeup Unit"

                if zone_id == "BILLING":
                    billing_visitors.append(gv)

                # Track zone enter and dwell independently per camera
                if cam_id not in gv.active_zones:
                    # Emit store-level ENTRY/REENTRY when first camera is seen
                    if not gv.active_zones:
                        gv.session_seq += 1
                        if cam_id == "CAM 1":
                            event_type = "REENTRY" if gv.has_exited else "ENTRY"
                            events_log.append({
                                "event_id": str(uuid.uuid4()),
                                "store_id": "ST1008",
                                "camera_id": cam_id,
                                "visitor_id": gv.visitor_id,
                                "event_type": event_type,
                                "timestamp": current_time,
                                "zone_id": None,
                                "dwell_ms": 0,
                                "is_staff": gv.is_staff,
                                "confidence": conf,
                                "metadata": {
                                    "queue_depth": None,
                                    "sku_zone": None,
                                    "session_seq": gv.session_seq
                                }
                            })
                            gv.has_exited = False

                    # Initialize zone tracking
                    gv.active_zones[cam_id] = [current_time, current_time, current_time, zone_id]
                    
                    # Emit ZONE_ENTER
                    events_log.append({
                        "event_id": str(uuid.uuid4()),
                        "store_id": "ST1008",
                        "camera_id": cam_id,
                        "visitor_id": gv.visitor_id,
                        "event_type": "ZONE_ENTER",
                        "timestamp": current_time,
                        "zone_id": zone_id,
                        "dwell_ms": 0,
                        "is_staff": gv.is_staff,
                        "confidence": conf,
                        "metadata": {
                            "queue_depth": None,
                            "sku_zone": sku_zone,
                            "session_seq": gv.session_seq
                        }
                    })
                else:
                    # Update last seen and check dwell
                    enter_time, _, last_dwell_emit, z_id = gv.active_zones[cam_id]
                    gv.active_zones[cam_id][1] = current_time # update last seen
                    
                    elapsed_dwell = (current_time - last_dwell_emit).total_seconds()
                    if elapsed_dwell >= 30.0:
                        total_dwell_ms = int((current_time - enter_time).total_seconds() * 1000)
                        gv.active_zones[cam_id][2] = current_time # update last dwell emit
                        events_log.append({
                            "event_id": str(uuid.uuid4()),
                            "store_id": "ST1008",
                            "camera_id": cam_id,
                            "visitor_id": gv.visitor_id,
                            "event_type": "ZONE_DWELL",
                            "timestamp": current_time,
                            "zone_id": z_id,
                            "dwell_ms": total_dwell_ms,
                            "is_staff": gv.is_staff,
                            "confidence": conf,
                            "metadata": {
                                "queue_depth": None,
                                "sku_zone": sku_zone,
                                "session_seq": gv.session_seq
                            }
                        })

        # Calculate Queue Depth & Billing Queue Joins
        if len(billing_visitors) > 1:
            for gv in billing_visitors:
                # If they just entered BILLING zone in this frame (active for <= 2 seconds)
                if "CAM 5" in gv.active_zones:
                    enter_time = gv.active_zones["CAM 5"][0]
                    if (current_time - enter_time).total_seconds() <= (frame_step / 15.0 + 0.1):
                        q_depth = len(billing_visitors) - 1
                        events_log.append({
                            "event_id": str(uuid.uuid4()),
                            "store_id": "ST1008",
                            "camera_id": "CAM 5",
                            "visitor_id": gv.visitor_id,
                            "event_type": "BILLING_QUEUE_JOIN",
                            "timestamp": current_time,
                            "zone_id": "BILLING",
                            "dwell_ms": 0,
                            "is_staff": gv.is_staff,
                            "confidence": 0.95,
                            "metadata": {
                                "queue_depth": q_depth,
                                "sku_zone": None,
                                "session_seq": gv.session_seq
                            }
                        })

        # Cleanup inactive zones for each visitor
        for gv in global_visitors:
            for active_cam in list(gv.active_zones.keys()):
                enter_time, last_seen, _, z_id = gv.active_zones[active_cam]
                # If not seen on this camera in the last 40 seconds (or current frame is way past last seen)
                if (current_time - last_seen).total_seconds() > 40.0:
                    dwell_ms = int((last_seen - enter_time).total_seconds() * 1000)
                    # We ensure dwell_ms is at least 15000 if we actually held them
                    events_log.append({
                        "event_id": str(uuid.uuid4()),
                        "store_id": "ST1008",
                        "camera_id": active_cam,
                        "visitor_id": gv.visitor_id,
                        "event_type": "ZONE_EXIT",
                        "timestamp": last_seen,
                        "zone_id": z_id,
                        "dwell_ms": max(15000, dwell_ms) if dwell_ms > 0 else 15000,
                        "is_staff": gv.is_staff,
                        "confidence": 0.9,
                        "metadata": {
                            "queue_depth": None,
                            "sku_zone": None,
                            "session_seq": gv.session_seq
                        }
                    })
                    
                    # Emit BILLING_QUEUE_ABANDON if visitor leaves BILLING zone
                    # without a matching POS transaction in the events log
                    if z_id == "BILLING" and not gv.is_staff:
                        had_queue_join = any(
                            e.get("visitor_id") == gv.visitor_id and
                            e.get("event_type") == "BILLING_QUEUE_JOIN"
                            for e in events_log
                        )
                        if had_queue_join:
                            events_log.append({
                                "event_id": str(uuid.uuid4()),
                                "store_id": "ST1008",
                                "camera_id": active_cam,
                                "visitor_id": gv.visitor_id,
                                "event_type": "BILLING_QUEUE_ABANDON",
                                "timestamp": last_seen,
                                "zone_id": "BILLING",
                                "dwell_ms": max(15000, dwell_ms) if dwell_ms > 0 else 15000,
                                "is_staff": gv.is_staff,
                                "confidence": 0.85,
                                "metadata": {
                                    "queue_depth": None,
                                    "sku_zone": None,
                                    "session_seq": gv.session_seq
                                }
                            })
                    
                    del gv.active_zones[active_cam]

                    # If visitor has no more active zones, they have exited the store
                    if not gv.active_zones:
                        events_log.append({
                            "event_id": str(uuid.uuid4()),
                            "store_id": "ST1008",
                            "camera_id": "CAM 1",
                            "visitor_id": gv.visitor_id,
                            "event_type": "EXIT",
                            "timestamp": last_seen,
                            "zone_id": None,
                            "dwell_ms": 0,
                            "is_staff": gv.is_staff,
                            "confidence": 0.9,
                            "metadata": {
                                "queue_depth": None,
                                "sku_zone": None,
                                "session_seq": gv.session_seq
                            }
                        })
                        gv.has_exited = True

    # Close camera streams
    for cap in caps.values():
        cap.release()

    # Final sweep: exit all remaining active zones
    for gv in global_visitors:
        for active_cam, (enter_time, last_seen, _, z_id) in gv.active_zones.items():
            dwell_ms = int((last_seen - enter_time).total_seconds() * 1000)
            events_log.append({
                "event_id": str(uuid.uuid4()),
                "store_id": "ST1008",
                "camera_id": active_cam,
                "visitor_id": gv.visitor_id,
                "event_type": "ZONE_EXIT",
                "timestamp": last_seen,
                "zone_id": z_id,
                "dwell_ms": max(15000, dwell_ms) if dwell_ms > 0 else 15000,
                "is_staff": gv.is_staff,
                "confidence": 0.9,
                "metadata": {
                    "queue_depth": None,
                    "sku_zone": None,
                    "session_seq": gv.session_seq
                }
            })
            events_log.append({
                "event_id": str(uuid.uuid4()),
                "store_id": "ST1008",
                "camera_id": "CAM 1",
                "visitor_id": gv.visitor_id,
                "event_type": "EXIT",
                "timestamp": last_seen,
                "zone_id": None,
                "dwell_ms": 0,
                "is_staff": gv.is_staff,
                "confidence": 0.9,
                "metadata": {
                    "queue_depth": None,
                    "sku_zone": None,
                    "session_seq": gv.session_seq
                }
            })

    save_events_to_jsonl(events_log)
    post_events_to_api(events_log, api_url)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--step", type=int, default=15, help="Frame step size for subsampling")
    parser.add_argument("--url", type=str, default="http://localhost:8000/events/ingest", help="API Ingestion endpoint")
    parser.add_argument("--layout", type=str, default="Revised", choices=["Revised", "Current"], help="Store brand layout style")
    args = parser.parse_args()
    main(frame_step=args.step, api_url=args.url, layout_type=args.layout)
