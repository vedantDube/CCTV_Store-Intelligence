# PROMPT: Generate pytest tests for the conversion funnel module (api/funnel.py).
# Cover the four-stage funnel: Entry → Zone Visit → Billing Queue → Purchase.
# Test drop-off percentage calculations between stages. Test that re-entry events
# with the same visitor_id do not double-count visitors. Test empty stores with zero
# visitors, stores with only billing visits (no zone visits), and the full happy path.
# CHANGES MADE: Added re-entry deduplication test verifying unique visitor_id counts.
# Fixed timestamp alignment between billing events and POS transactions.
# Moved shared DB setup to conftest.py.

import pytest
import uuid
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def make_event(store_id="ST_FUNNEL", event_type="ENTRY", zone_id=None,
               visitor_id=None, is_staff=False, timestamp=None):
    return {
        "event_id": str(uuid.uuid4()),
        "store_id": store_id,
        "camera_id": "CAM_TEST",
        "visitor_id": visitor_id or f"VIS_{uuid.uuid4().hex[:6]}",
        "event_type": event_type,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "zone_id": zone_id,
        "dwell_ms": 0,
        "is_staff": is_staff,
        "confidence": 0.92,
        "metadata": {"queue_depth": None, "sku_zone": None, "session_seq": 1}
    }


class TestFunnelBasic:
    def test_empty_store_funnel(self):
        resp = client.get("/stores/ST_EMPTY_FUN/funnel")
        assert resp.status_code == 200
        data = resp.json()
        for stage in data["stages"]:
            assert stage["count"] == 0

    def test_four_stages_returned(self):
        events = [make_event(visitor_id="VIS_1")]
        client.post("/events/ingest", json={"events": events})
        resp = client.get("/stores/ST_FUNNEL/funnel")
        assert len(resp.json()["stages"]) == 4

    def test_entry_only_visitor(self):
        events = [make_event(visitor_id="VIS_ENTRY", event_type="ENTRY", zone_id=None)]
        client.post("/events/ingest", json={"events": events})
        resp = client.get("/stores/ST_FUNNEL/funnel")
        stages = resp.json()["stages"]
        assert stages[0]["count"] == 1
        assert stages[1]["count"] == 0
        assert stages[2]["count"] == 0
        assert stages[3]["count"] == 0


class TestFunnelProgression:
    def test_visitor_reaches_zone(self):
        vid = "VIS_ZONE"
        events = [
            make_event(visitor_id=vid, event_type="ENTRY", zone_id=None),
            make_event(visitor_id=vid, event_type="ZONE_ENTER", zone_id="MAKEUP"),
        ]
        client.post("/events/ingest", json={"events": events})
        resp = client.get("/stores/ST_FUNNEL/funnel")
        stages = resp.json()["stages"]
        assert stages[0]["count"] == 1
        assert stages[1]["count"] == 1

    def test_visitor_reaches_billing(self):
        vid = "VIS_BILL"
        events = [
            make_event(visitor_id=vid, event_type="ENTRY", zone_id=None),
            make_event(visitor_id=vid, event_type="ZONE_ENTER", zone_id="SKINCARE"),
            make_event(visitor_id=vid, event_type="ZONE_ENTER", zone_id="BILLING"),
        ]
        client.post("/events/ingest", json={"events": events})
        resp = client.get("/stores/ST_FUNNEL/funnel")
        stages = resp.json()["stages"]
        assert stages[0]["count"] == 1
        assert stages[1]["count"] == 1
        assert stages[2]["count"] == 1
        assert stages[3]["count"] == 0


class TestFunnelDropoff:
    def test_dropoff_percentages(self):
        events = [
            make_event(visitor_id="VIS_A", event_type="ENTRY", zone_id=None),
            make_event(visitor_id="VIS_B", event_type="ENTRY", zone_id=None),
            make_event(visitor_id="VIS_C", event_type="ENTRY", zone_id=None),
            make_event(visitor_id="VIS_D", event_type="ENTRY", zone_id=None),
            make_event(visitor_id="VIS_A", event_type="ZONE_ENTER", zone_id="SKINCARE"),
            make_event(visitor_id="VIS_B", event_type="ZONE_ENTER", zone_id="MAKEUP"),
            make_event(visitor_id="VIS_C", event_type="ZONE_ENTER", zone_id="FOH"),
            make_event(visitor_id="VIS_A", event_type="ZONE_ENTER", zone_id="BILLING"),
            make_event(visitor_id="VIS_B", event_type="ZONE_ENTER", zone_id="BILLING"),
        ]
        client.post("/events/ingest", json={"events": events})
        resp = client.get("/stores/ST_FUNNEL/funnel")
        stages = resp.json()["stages"]
        assert stages[0]["count"] == 4
        assert stages[1]["count"] == 3
        assert stages[2]["count"] == 2
        assert stages[1]["drop_off_pct"] == 25.0


class TestFunnelReentry:
    def test_reentry_not_double_counted(self):
        vid = "VIS_REENTRY"
        events = [
            make_event(visitor_id=vid, event_type="ENTRY", zone_id=None),
            make_event(visitor_id=vid, event_type="ZONE_ENTER", zone_id="SKINCARE"),
            make_event(visitor_id=vid, event_type="EXIT", zone_id=None),
            make_event(visitor_id=vid, event_type="REENTRY", zone_id=None),
            make_event(visitor_id=vid, event_type="ZONE_ENTER", zone_id="BILLING"),
        ]
        client.post("/events/ingest", json={"events": events})
        resp = client.get("/stores/ST_FUNNEL/funnel")
        stages = resp.json()["stages"]
        assert stages[0]["count"] == 1


class TestFunnelStaffExclusion:
    def test_staff_excluded_from_funnel(self):
        events = [
            make_event(visitor_id="VIS_CUST", event_type="ENTRY", zone_id=None, is_staff=False),
            make_event(visitor_id="VIS_STAFF", event_type="ENTRY", zone_id=None, is_staff=True),
            make_event(visitor_id="VIS_STAFF", event_type="ZONE_ENTER", zone_id="SKINCARE", is_staff=True),
        ]
        client.post("/events/ingest", json={"events": events})
        resp = client.get("/stores/ST_FUNNEL/funnel")
        stages = resp.json()["stages"]
        assert stages[0]["count"] == 1
