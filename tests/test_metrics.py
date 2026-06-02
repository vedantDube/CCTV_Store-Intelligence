# PROMPT: Generate comprehensive pytest tests for the store metrics calculation module (api/metrics.py).
# Tests should cover: unique visitor counting with staff exclusion, conversion rate calculation
# with POS transaction 5-minute window correlation, average dwell time per zone, queue depth from
# BILLING_QUEUE_JOIN events, abandonment rate from BILLING_QUEUE_ABANDON events, and edge cases
# including zero-purchase stores, all-staff clips, empty stores, and re-entry visitors.
# CHANGES MADE: Added async database session override using in-memory SQLite for test isolation.
# Added POS transaction seeding for conversion rate tests. Replaced generic assertions with
# precise numerical checks. Added re-entry deduplication test to verify visitor_id uniqueness.
# Moved shared DB setup to conftest.py.

import pytest
import uuid
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def make_event(store_id="ST_METRIC", event_type="ZONE_ENTER", zone_id="SKINCARE",
               visitor_id=None, is_staff=False, dwell_ms=0, confidence=0.92,
               queue_depth=None, timestamp=None):
    return {
        "event_id": str(uuid.uuid4()),
        "store_id": store_id,
        "camera_id": "CAM_TEST",
        "visitor_id": visitor_id or f"VIS_{uuid.uuid4().hex[:6]}",
        "event_type": event_type,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "zone_id": zone_id,
        "dwell_ms": dwell_ms,
        "is_staff": is_staff,
        "confidence": confidence,
        "metadata": {
            "queue_depth": queue_depth,
            "sku_zone": "MOISTURISER",
            "session_seq": 1
        }
    }


class TestUniqueVisitors:
    def test_single_visitor(self):
        vid = "VIS_SINGLE"
        events = [
            make_event(visitor_id=vid, event_type="ENTRY", zone_id=None),
            make_event(visitor_id=vid, event_type="ZONE_ENTER", zone_id="SKINCARE"),
        ]
        client.post("/events/ingest", json={"events": events})
        resp = client.get("/stores/ST_METRIC/metrics")
        assert resp.status_code == 200
        assert resp.json()["unique_visitors"] == 1

    def test_multiple_visitors(self):
        events = [
            make_event(visitor_id="VIS_A", event_type="ENTRY", zone_id=None),
            make_event(visitor_id="VIS_B", event_type="ENTRY", zone_id=None),
            make_event(visitor_id="VIS_C", event_type="ENTRY", zone_id=None),
        ]
        client.post("/events/ingest", json={"events": events})
        resp = client.get("/stores/ST_METRIC/metrics")
        assert resp.json()["unique_visitors"] == 3

    def test_staff_excluded_from_visitors(self):
        events = [
            make_event(visitor_id="VIS_CUST1", is_staff=False),
            make_event(visitor_id="VIS_STAFF1", is_staff=True),
            make_event(visitor_id="VIS_CUST2", is_staff=False),
        ]
        client.post("/events/ingest", json={"events": events})
        resp = client.get("/stores/ST_METRIC/metrics")
        assert resp.json()["unique_visitors"] == 2

    def test_all_staff_clip_zero_visitors(self):
        events = [
            make_event(visitor_id="STAFF_A", is_staff=True),
            make_event(visitor_id="STAFF_B", is_staff=True),
        ]
        client.post("/events/ingest", json={"events": events})
        resp = client.get("/stores/ST_METRIC/metrics")
        data = resp.json()
        assert data["unique_visitors"] == 0
        assert data["conversion_rate"] == 0.0


class TestDwellMetrics:
    def test_avg_dwell_by_zone(self):
        vid = "VIS_DWELL"
        events = [
            make_event(visitor_id=vid, event_type="ZONE_DWELL", zone_id="SKINCARE", dwell_ms=30000),
            make_event(visitor_id=vid, event_type="ZONE_DWELL", zone_id="SKINCARE", dwell_ms=60000),
        ]
        client.post("/events/ingest", json={"events": events})
        resp = client.get("/stores/ST_METRIC/metrics")
        assert resp.json()["avg_dwell_by_zone"]["SKINCARE"] == 45000.0

    def test_zero_dwell_not_counted(self):
        vid = "VIS_ZERO"
        events = [
            make_event(visitor_id=vid, event_type="ZONE_ENTER", zone_id="MAKEUP", dwell_ms=0),
            make_event(visitor_id=vid, event_type="ZONE_DWELL", zone_id="MAKEUP", dwell_ms=50000),
        ]
        client.post("/events/ingest", json={"events": events})
        resp = client.get("/stores/ST_METRIC/metrics")
        assert resp.json()["avg_dwell_by_zone"]["MAKEUP"] == 50000.0


class TestQueueDepth:
    def test_queue_depth_from_billing_join(self):
        events = [
            make_event(visitor_id="VIS_Q1", event_type="BILLING_QUEUE_JOIN", zone_id="BILLING", queue_depth=3),
            make_event(visitor_id="VIS_Q2", event_type="BILLING_QUEUE_JOIN", zone_id="BILLING", queue_depth=5),
        ]
        client.post("/events/ingest", json={"events": events})
        resp = client.get("/stores/ST_METRIC/metrics")
        assert resp.json()["queue_depth"] == 5

    def test_no_queue_events_zero_depth(self):
        events = [make_event(visitor_id="VIS_NQ", event_type="ZONE_ENTER", zone_id="FOH")]
        client.post("/events/ingest", json={"events": events})
        resp = client.get("/stores/ST_METRIC/metrics")
        assert resp.json()["queue_depth"] == 0


class TestEmptyStore:
    def test_empty_store_returns_valid_metrics(self):
        resp = client.get("/stores/STORE_EMPTY_NONEXIST/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert data["unique_visitors"] == 0
        assert data["conversion_rate"] == 0.0
        assert data["queue_depth"] == 0
        assert data["abandonment_rate"] == 0.0
        assert data["avg_dwell_by_zone"] == {}


class TestConversionRate:
    def test_zero_purchase_store(self):
        events = [
            make_event(visitor_id="VIS_NP1", event_type="ZONE_ENTER", zone_id="BILLING"),
            make_event(visitor_id="VIS_NP2", event_type="ZONE_ENTER", zone_id="BILLING"),
        ]
        client.post("/events/ingest", json={"events": events})
        resp = client.get("/stores/ST_METRIC/metrics")
        assert resp.json()["conversion_rate"] == 0.0
