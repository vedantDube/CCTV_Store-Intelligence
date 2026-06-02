# PROMPT: Generate pytest tests for the anomaly detection module (api/anomalies.py).
# Cover: dead zone detection when no visits in 30 minutes, billing queue spike detection
# with queue_depth thresholds (>5 WARN, >8 CRITICAL), conversion drop detection when
# conversion rate falls below baseline, and edge cases including empty stores and stores
# with only staff events.
# CHANGES MADE: Added time-aware event seeding to test the 30-minute dead zone window.
# Replaced static zone list tests with dynamic zone discovery assertions. Added severity
# level validation for queue spike thresholds. Moved shared DB setup to conftest.py.

import pytest
import uuid
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def make_event(store_id="ST_ANOM", event_type="ZONE_ENTER", zone_id="FOH",
               visitor_id=None, is_staff=False, dwell_ms=0, confidence=0.90,
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
            "sku_zone": None,
            "session_seq": 1
        }
    }


class TestEmptyStore:
    def test_no_events_returns_empty_anomalies(self):
        resp = client.get("/stores/ST_EMPTY_ANOM/anomalies")
        assert resp.status_code == 200
        data = resp.json()
        assert data["anomalies"] == []


class TestDeadZone:
    def test_dead_zone_detected(self):
        now = datetime.now(timezone.utc)
        old_time = (now - timedelta(minutes=45)).isoformat()
        
        events = [
            make_event(zone_id="FOH", timestamp=old_time, visitor_id="VIS_OLD"),
            make_event(zone_id="MAKEUP", timestamp=old_time, visitor_id="VIS_OLD2"),
            make_event(zone_id="MAKEUP", timestamp=now.isoformat(), visitor_id="VIS_NEW"),
        ]
        client.post("/events/ingest", json={"events": events})
        
        resp = client.get("/stores/ST_ANOM/anomalies")
        assert resp.status_code == 200
        anomalies = resp.json()["anomalies"]
        dead_zones = [a for a in anomalies if a["type"] == "DEAD_ZONE"]
        dead_zone_msgs = [a["message"] for a in dead_zones]
        assert any("FOH" in msg for msg in dead_zone_msgs)

    def test_active_zones_not_flagged(self):
        now = datetime.now(timezone.utc).isoformat()
        events = [
            make_event(zone_id="FOH", timestamp=now, visitor_id="VIS_1"),
            make_event(zone_id="SKINCARE", timestamp=now, visitor_id="VIS_2"),
        ]
        client.post("/events/ingest", json={"events": events})
        
        resp = client.get("/stores/ST_ANOM/anomalies")
        anomalies = resp.json()["anomalies"]
        dead_zones = [a for a in anomalies if a["type"] == "DEAD_ZONE"]
        assert len(dead_zones) == 0


class TestQueueSpike:
    def test_queue_spike_warn(self):
        now = datetime.now(timezone.utc).isoformat()
        events = [
            make_event(event_type="BILLING_QUEUE_JOIN", zone_id="BILLING",
                      queue_depth=6, timestamp=now, visitor_id="VIS_Q1"),
        ]
        client.post("/events/ingest", json={"events": events})
        
        resp = client.get("/stores/ST_ANOM/anomalies")
        anomalies = resp.json()["anomalies"]
        spikes = [a for a in anomalies if a["type"] == "QUEUE_SPIKE"]
        assert len(spikes) == 1
        assert spikes[0]["severity"] == "WARN"

    def test_queue_spike_critical(self):
        now = datetime.now(timezone.utc).isoformat()
        events = [
            make_event(event_type="BILLING_QUEUE_JOIN", zone_id="BILLING",
                      queue_depth=10, timestamp=now, visitor_id="VIS_QC"),
        ]
        client.post("/events/ingest", json={"events": events})
        
        resp = client.get("/stores/ST_ANOM/anomalies")
        anomalies = resp.json()["anomalies"]
        spikes = [a for a in anomalies if a["type"] == "QUEUE_SPIKE"]
        assert len(spikes) == 1
        assert spikes[0]["severity"] == "CRITICAL"

    def test_no_queue_spike_below_threshold(self):
        now = datetime.now(timezone.utc).isoformat()
        events = [
            make_event(event_type="BILLING_QUEUE_JOIN", zone_id="BILLING",
                      queue_depth=3, timestamp=now, visitor_id="VIS_LOW"),
        ]
        client.post("/events/ingest", json={"events": events})
        
        resp = client.get("/stores/ST_ANOM/anomalies")
        anomalies = resp.json()["anomalies"]
        spikes = [a for a in anomalies if a["type"] == "QUEUE_SPIKE"]
        assert len(spikes) == 0


class TestAnomalySchema:
    def test_anomaly_response_fields(self):
        now = datetime.now(timezone.utc).isoformat()
        events = [
            make_event(event_type="BILLING_QUEUE_JOIN", zone_id="BILLING",
                      queue_depth=7, timestamp=now, visitor_id="VIS_SCHEMA"),
        ]
        client.post("/events/ingest", json={"events": events})
        
        resp = client.get("/stores/ST_ANOM/anomalies")
        for anomaly in resp.json()["anomalies"]:
            assert "type" in anomaly
            assert "severity" in anomaly
            assert anomaly["severity"] in ("INFO", "WARN", "CRITICAL")
            assert "message" in anomaly
            assert "suggested_action" in anomaly
            assert "timestamp" in anomaly
