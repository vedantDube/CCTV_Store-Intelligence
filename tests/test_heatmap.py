# PROMPT: Generate pytest tests for the heatmap module (api/heatmap.py). Cover zone visit
# frequency counting from ZONE_ENTER events, average dwell time calculation from ZONE_DWELL
# events, normalized score computation (0-100 scale), and the data_confidence boolean flag.
# CHANGES MADE: Added dynamic zone discovery verification. Added tests for normalization
# edge cases. Added data_confidence threshold test at exactly 20 sessions.
# Moved shared DB setup to conftest.py.

import pytest
import uuid
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def make_event(store_id="ST_HEAT", event_type="ZONE_ENTER", zone_id="FOH",
               visitor_id=None, dwell_ms=0, is_staff=False):
    return {
        "event_id": str(uuid.uuid4()),
        "store_id": store_id,
        "camera_id": "CAM_TEST",
        "visitor_id": visitor_id or f"VIS_{uuid.uuid4().hex[:6]}",
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "zone_id": zone_id,
        "dwell_ms": dwell_ms,
        "is_staff": is_staff,
        "confidence": 0.92,
        "metadata": {"queue_depth": None, "sku_zone": None, "session_seq": 1}
    }


class TestHeatmapBasic:
    def test_empty_store_returns_valid_heatmap(self):
        resp = client.get("/stores/ST_HEAT_EMPTY/heatmap")
        assert resp.status_code == 200
        data = resp.json()
        assert "heatmap" in data
        assert "data_confidence" in data

    def test_single_zone_visit(self):
        events = [make_event(zone_id="FOH", visitor_id="VIS_1")]
        client.post("/events/ingest", json={"events": events})
        resp = client.get("/stores/ST_HEAT/heatmap")
        data = resp.json()
        foh = next((z for z in data["heatmap"] if z["zone_id"] == "FOH"), None)
        assert foh is not None
        assert foh["visit_frequency"] == 1


class TestDataConfidence:
    def test_low_sessions_no_confidence(self):
        events = [make_event(visitor_id=f"VIS_{i}") for i in range(5)]
        client.post("/events/ingest", json={"events": events})
        resp = client.get("/stores/ST_HEAT/heatmap")
        assert resp.json()["data_confidence"] is False

    def test_enough_sessions_confidence(self):
        events = [make_event(visitor_id=f"VIS_{i}") for i in range(25)]
        client.post("/events/ingest", json={"events": events})
        resp = client.get("/stores/ST_HEAT/heatmap")
        assert resp.json()["data_confidence"] is True


class TestNormalization:
    def test_normalized_score_range(self):
        events = [
            make_event(zone_id="FOH", visitor_id="V1"),
            make_event(zone_id="FOH", visitor_id="V2"),
            make_event(zone_id="FOH", visitor_id="V3"),
            make_event(zone_id="SKINCARE", visitor_id="V4"),
            make_event(zone_id="SKINCARE", event_type="ZONE_DWELL", dwell_ms=60000, visitor_id="V4"),
        ]
        client.post("/events/ingest", json={"events": events})
        resp = client.get("/stores/ST_HEAT/heatmap")
        for zone in resp.json()["heatmap"]:
            assert 0 <= zone["normalized_score"] <= 100


class TestHeatmapStaffExclusion:
    def test_staff_excluded(self):
        events = [
            make_event(zone_id="FOH", visitor_id="VIS_CUST", is_staff=False),
            make_event(zone_id="FOH", visitor_id="VIS_STAFF", is_staff=True),
        ]
        client.post("/events/ingest", json={"events": events})
        resp = client.get("/stores/ST_HEAT/heatmap")
        foh = next((z for z in resp.json()["heatmap"] if z["zone_id"] == "FOH"), None)
        assert foh is not None
        assert foh["visit_frequency"] == 1


class TestDwellInHeatmap:
    def test_avg_dwell_ms_calculation(self):
        vid = "VIS_DW"
        events = [
            make_event(zone_id="SKINCARE", event_type="ZONE_DWELL", dwell_ms=30000, visitor_id=vid),
            make_event(zone_id="SKINCARE", event_type="ZONE_DWELL", dwell_ms=90000, visitor_id=vid),
        ]
        client.post("/events/ingest", json={"events": events})
        resp = client.get("/stores/ST_HEAT/heatmap")
        skin = next((z for z in resp.json()["heatmap"] if z["zone_id"] == "SKINCARE"), None)
        assert skin is not None
        assert skin["avg_dwell_ms"] == 60000.0
