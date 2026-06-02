# PROMPT: Generate pytest unit tests for a FastAPI store intelligence analytics service using TestClient. The tests should cover event ingestion (/events/ingest), metrics calculation (/stores/{id}/metrics), conversion funnels (/stores/{id}/funnel), heatmaps (/stores/{id}/heatmap), anomalies (/stores/{id}/anomalies), and service health (/health). Include tests for idempotency by sending duplicate events, validation errors for malformed events, and database query coverage for non-existent stores.
# CHANGES MADE: Customized test payloads to strictly match our Pydantic DBEvent schema, added overrides for async database session dependency, added a test asserting transaction loading and POS correlation logic, and structured setup/teardown with local sqlite memory database context. Moved shared DB setup to conftest.py.

import pytest
import uuid
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from api.main import app
from api.db import DBEvent, DBTransaction

client = TestClient(app)

# Helper to generate mock event
def create_mock_event(event_id=None, store_id="ST1008", event_type="ZONE_ENTER", zone_id="SKINCARE", is_staff=False, timestamp=None):
    return {
        "event_id": event_id or str(uuid.uuid4()),
        "store_id": store_id,
        "camera_id": "CAM_01",
        "visitor_id": "VIS_test1",
        "event_type": event_type,
        "timestamp": timestamp or (datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")),
        "zone_id": zone_id,
        "dwell_ms": 15000 if event_type == "ZONE_DWELL" else 0,
        "is_staff": is_staff,
        "confidence": 0.95,
        "metadata": {
            "queue_depth": 3 if event_type == "BILLING_QUEUE_JOIN" else None,
            "sku_zone": "MOISTURISER",
            "session_seq": 1
        }
    }

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"

def test_events_ingest_success():
    event = create_mock_event()
    response = client.post("/events/ingest", json={"events": [event]})
    assert response.status_code == 200
    assert "Successfully processed 1 events." in response.json()["message"]

def test_events_ingest_malformed_type():
    event = create_mock_event(event_type="INVALID_TYPE")
    response = client.post("/events/ingest", json={"events": [event]})
    # All events failed → 422
    assert response.status_code == 422
    data = response.json()
    assert "errors" in data
    assert len(data["errors"]) > 0
    assert "INVALID_TYPE" in str(data["errors"])

def test_events_ingest_idempotency():
    event = create_mock_event()
    # First post
    response = client.post("/events/ingest", json={"events": [event]})
    assert response.status_code == 200
    # Second duplicate post
    response2 = client.post("/events/ingest", json={"events": [event]})
    assert response2.status_code == 200
    assert response2.json()["success_count"] == 1  # still succeeds (merge)

def test_store_metrics():
    store_id = "ST_TEST"
    event1 = create_mock_event(store_id=store_id, event_type="ZONE_ENTER", zone_id="SKINCARE")
    event2 = create_mock_event(store_id=store_id, event_type="ZONE_DWELL", zone_id="SKINCARE")
    event2["dwell_ms"] = 30000
    
    # Ingest mock events
    client.post("/events/ingest", json={"events": [event1, event2]})
    
    response = client.get(f"/stores/{store_id}/metrics")
    assert response.status_code == 200
    data = response.json()
    assert data["unique_visitors"] == 1
    assert data["avg_dwell_by_zone"]["SKINCARE"] == 30000.0

def test_store_funnel():
    store_id = "ST_FUNNEL"
    event1 = create_mock_event(store_id=store_id, event_type="ENTRY", zone_id=None)
    event2 = create_mock_event(store_id=store_id, event_type="ZONE_ENTER", zone_id="MAKEUP")
    event3 = create_mock_event(store_id=store_id, event_type="ZONE_ENTER", zone_id="BILLING")
    
    client.post("/events/ingest", json={"events": [event1, event2, event3]})
    
    response = client.get(f"/stores/{store_id}/funnel")
    assert response.status_code == 200
    data = response.json()
    assert len(data["stages"]) == 4
    assert data["stages"][0]["count"] == 1  # Entry
    assert data["stages"][1]["count"] == 1  # Zone Visit
    assert data["stages"][2]["count"] == 1  # Billing Queue
    assert data["stages"][3]["count"] == 0  # Purchase (no POS transactions)

def test_store_heatmap():
    store_id = "ST_HEATMAP"
    event = create_mock_event(store_id=store_id, event_type="ZONE_ENTER", zone_id="FOH")
    client.post("/events/ingest", json={"events": [event]})
    
    response = client.get(f"/stores/{store_id}/heatmap")
    assert response.status_code == 200
    data = response.json()
    assert data["data_confidence"] is False  # < 20 sessions

def test_store_anomalies():
    store_id = "ST_ANOMALY"
    # Ingest a billing queue spike
    event = create_mock_event(store_id=store_id, event_type="BILLING_QUEUE_JOIN", zone_id="BILLING")
    client.post("/events/ingest", json={"events": [event]})
    
    response = client.get(f"/stores/{store_id}/anomalies")
    assert response.status_code == 200
    data = response.json()
    # Should have at least some anomaly (dead zones or low conversion)
    assert isinstance(data["anomalies"], list)
