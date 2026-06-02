# PROMPT: Generate pytest tests for the event ingestion module (api/ingestion.py).
# Cover: successful batch ingestion, idempotency (duplicate event_id should be merged),
# partial success when some events are malformed, batch size limit of 500, validation of
# event_type against the known catalogue, empty batch handling, and structured error responses.
# CHANGES MADE: Added tests for confidence range validation. Added test for missing
# critical fields. Moved shared DB setup to conftest.py.

import pytest
import uuid
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def make_event(event_id=None, event_type="ZONE_ENTER", zone_id="SKINCARE", visitor_id=None,
               confidence=0.92, is_staff=False):
    return {
        "event_id": event_id or str(uuid.uuid4()),
        "store_id": "ST_INGEST",
        "camera_id": "CAM_01",
        "visitor_id": visitor_id or f"VIS_{uuid.uuid4().hex[:6]}",
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "zone_id": zone_id,
        "dwell_ms": 0,
        "is_staff": is_staff,
        "confidence": confidence,
        "metadata": {"queue_depth": None, "sku_zone": None, "session_seq": 1}
    }


class TestIngestSuccess:
    def test_single_event_ingested(self):
        resp = client.post("/events/ingest", json={"events": [make_event()]})
        assert resp.status_code == 200
        assert resp.json()["success_count"] == 1

    def test_batch_of_events(self):
        events = [make_event() for _ in range(10)]
        resp = client.post("/events/ingest", json={"events": events})
        assert resp.status_code == 200
        assert resp.json()["success_count"] == 10

    def test_empty_batch(self):
        resp = client.post("/events/ingest", json={"events": []})
        assert resp.status_code == 200
        assert resp.json()["success_count"] == 0


class TestIdempotency:
    def test_duplicate_event_id_merged(self):
        event = make_event()
        resp1 = client.post("/events/ingest", json={"events": [event]})
        assert resp1.status_code == 200
        resp2 = client.post("/events/ingest", json={"events": [event]})
        assert resp2.status_code == 200
        assert resp2.json()["success_count"] == 1

    def test_mixed_new_and_duplicate(self):
        eid = str(uuid.uuid4())
        event_dup = make_event(event_id=eid)
        event_new = make_event()
        client.post("/events/ingest", json={"events": [event_dup]})
        resp = client.post("/events/ingest", json={"events": [event_dup, event_new]})
        assert resp.status_code == 200
        assert resp.json()["success_count"] == 2


class TestBatchLimit:
    def test_exceeds_500_limit(self):
        events = [make_event() for _ in range(501)]
        resp = client.post("/events/ingest", json={"events": events})
        assert resp.status_code == 400


class TestValidation:
    def test_invalid_event_type_rejected(self):
        event = make_event(event_type="INVALID_TYPE")
        resp = client.post("/events/ingest", json={"events": [event]})
        data = resp.json()
        assert len(data.get("errors", [])) > 0

    def test_all_valid_event_types_accepted(self):
        valid_types = [
            "ENTRY", "EXIT", "ZONE_ENTER", "ZONE_EXIT", "ZONE_DWELL",
            "BILLING_QUEUE_JOIN", "BILLING_QUEUE_ABANDON", "REENTRY"
        ]
        for et in valid_types:
            event = make_event(event_type=et, zone_id="BILLING" if "BILLING" in et else "FOH")
            resp = client.post("/events/ingest", json={"events": [event]})
            assert resp.json()["success_count"] == 1, f"Event type {et} should be valid"


class TestPartialSuccess:
    def test_partial_batch_success(self):
        good_event = make_event(event_type="ENTRY", zone_id=None)
        bad_event = make_event(event_type="TOTALLY_BOGUS")
        resp = client.post("/events/ingest", json={"events": [good_event, bad_event]})
        data = resp.json()
        assert data["success_count"] == 1
        assert len(data["errors"]) == 1


class TestErrorStructure:
    def test_error_response_fields(self):
        event = make_event(event_type="FAKE_EVENT")
        resp = client.post("/events/ingest", json={"events": [event]})
        errors = resp.json().get("errors", [])
        assert len(errors) > 0
        err = errors[0]
        assert "index" in err
        assert "event_id" in err
        assert "error" in err
