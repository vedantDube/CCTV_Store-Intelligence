import sys
import os
import json
import httpx
import uuid
import argparse
from datetime import datetime

def normalize_event(raw_event: dict) -> dict:
    """
    Normalizes different variations of the event schemas into the required EventModel API schema.
    """
    # 1. If it already has visitor_id and event_id in the correct format, return as is
    if "visitor_id" in raw_event and "event_id" in raw_event:
        return raw_event

    # 2. Otherwise map raw detection fields to the API schema
    event_id = raw_event.get("event_id") or str(uuid.uuid4())
    store_id = raw_event.get("store_id") or raw_event.get("store_code") or "ST1008"
    camera_id = raw_event.get("camera_id") or "CAM 1"

    visitor_id = raw_event.get("visitor_id") or raw_event.get("id_token")
    if visitor_id is None:
        track_id = raw_event.get("track_id")
        if track_id is not None:
            visitor_id = f"VIS_{track_id}"
        else:
            visitor_id = "VIS_UNKNOWN"

    raw_type = raw_event.get("event_type", "").lower()
    event_type = "ZONE_DWELL"
    zone_id = raw_event.get("zone_id")

    if raw_type == "entry":
        event_type = "ENTRY"
        zone_id = None
    elif raw_type == "exit":
        event_type = "EXIT"
        zone_id = None
    elif raw_type == "zone_entered":
        event_type = "ZONE_ENTER"
    elif raw_type == "zone_exited":
        event_type = "ZONE_EXIT"
    elif raw_type in ("queue_completed", "queue_abandoned"):
        if raw_event.get("abandoned") or raw_type == "queue_abandoned":
            event_type = "BILLING_QUEUE_ABANDON"
        else:
            event_type = "BILLING_QUEUE_JOIN"
        zone_id = "BILLING"
    elif raw_type.upper() in ["ENTRY", "EXIT", "ZONE_ENTER", "ZONE_EXIT", "ZONE_DWELL", "BILLING_QUEUE_JOIN", "BILLING_QUEUE_ABANDON", "REENTRY"]:
        event_type = raw_type.upper()

    ts_str = raw_event.get("event_timestamp") or raw_event.get("event_time") or raw_event.get("timestamp") or raw_event.get("queue_join_ts") or raw_event.get("queue_exit_ts")
    if not ts_str:
        ts_str = datetime.utcnow().isoformat() + "Z"
    else:
        # Standardize ISO timestamp suffix
        if isinstance(ts_str, str) and not ts_str.endswith("Z") and "+" not in ts_str:
            ts_str = ts_str + "Z"

    dwell_ms = raw_event.get("dwell_ms") or 0
    if "wait_seconds" in raw_event:
        dwell_ms = int(raw_event["wait_seconds"]) * 1000

    metadata = raw_event.get("metadata") or {}
    queue_depth = metadata.get("queue_depth") or raw_event.get("queue_position_at_join")
    sku_zone = metadata.get("sku_zone") or raw_event.get("zone_name")
    session_seq = metadata.get("session_seq") or 1

    return {
        "event_id": event_id,
        "store_id": store_id,
        "camera_id": camera_id,
        "visitor_id": visitor_id,
        "event_type": event_type,
        "timestamp": ts_str,
        "zone_id": zone_id,
        "dwell_ms": dwell_ms,
        "is_staff": bool(raw_event.get("is_staff", False)),
        "confidence": float(raw_event.get("confidence") or raw_event.get("conf") or 1.0),
        "metadata": {
            "queue_depth": queue_depth,
            "sku_zone": sku_zone,
            "session_seq": session_seq
        }
    }

def replay_jsonl(filepath: str, api_url: str):
    if not os.path.exists(filepath):
        print(f"[REPLAY] Error: File {filepath} not found.")
        sys.exit(1)

    events = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(normalize_event(json.loads(line)))
            except Exception as e:
                print(f"[REPLAY] Skipping invalid JSON line: {e}")

    print(f"[REPLAY] Loaded and normalized {len(events)} events from {filepath}")
    if not events:
        return True

    batch_size = 500
    success = True

    for i in range(0, len(events), batch_size):
        batch = events[i:i + batch_size]
        print(f"[REPLAY] Sending batch of {len(batch)} events to {api_url}...")
        try:
            response = httpx.post(api_url, json={"events": batch}, timeout=30.0)
            if response.status_code == 200:
                print(f"[REPLAY] Batch sent successfully: {response.json().get('message')}")
            else:
                print(f"[REPLAY] Error sending batch (status {response.status_code}): {response.text}")
                success = False
        except Exception as e:
            print(f"[REPLAY] Exception while sending batch: {e}")
            success = False

    return success

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Replay and normalize events from a JSONL file to the Ingestion API")
    parser.add_argument("filepath", type=str, help="Path to the events JSONL file")
    parser.add_argument("--url", type=str, default="http://localhost:8000/events/ingest", help="API Ingestion endpoint")
    args = parser.parse_args()
    replay_jsonl(args.filepath, args.url)
