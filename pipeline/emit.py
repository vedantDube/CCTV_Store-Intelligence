import json
import httpx
from datetime import datetime

def save_events_to_jsonl(events: list[dict], filepath: str = "events.jsonl"):
    """
    Saves a list of event dictionaries to a JSON Lines file.
    """
    with open(filepath, "w", encoding="utf-8") as f:
        for event in events:
            # Custom encoder for datetime objects if any
            f.write(json.dumps(event, default=str) + "\n")
    print(f"[EMIT] Successfully saved {len(events)} events to {filepath}")

def post_events_to_api(events: list[dict], api_url: str = "http://localhost:8000/events/ingest") -> bool:
    """
    Sends the list of events in batches of 500 to the FastAPI ingestion endpoint.
    """
    if not events:
        print("[EMIT] No events to send.")
        return True

    # Split into batches of 500
    batch_size = 500
    success = True
    
    # Simple datetime to string serializer
    def serialize_val(val):
        if isinstance(val, datetime):
            return val.isoformat() + "Z"
        return val

    serialized_events = []
    for ev in events:
        s_ev = {}
        for k, v in ev.items():
            if k == "metadata" and v is not None:
                s_ev[k] = {mk: serialize_val(mv) for mk, mv in v.items()}
            else:
                s_ev[k] = serialize_val(v)
        serialized_events.append(s_ev)

    for i in range(0, len(serialized_events), batch_size):
        batch = serialized_events[i:i + batch_size]
        print(f"[EMIT] Sending batch of {len(batch)} events to {api_url}...")
        try:
            response = httpx.post(api_url, json={"events": batch}, timeout=30.0)
            if response.status_code == 200:
                print(f"[EMIT] Batch sent successfully: {response.json().get('message')}")
            else:
                print(f"[EMIT] Error sending batch (status {response.status_code}): {response.text}")
                success = False
        except Exception as e:
            print(f"[EMIT] Exception while sending batch: {e}")
            success = False

    return success
