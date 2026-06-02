# api/anomalies.py
from datetime import datetime, timedelta
from sqlmodel import select, func
from sqlmodel.ext.asyncio.session import AsyncSession
from api.db import DBEvent, DBTransaction
from api.metrics import compute_store_metrics
from typing import List, Dict, Any

async def detect_store_anomalies(session: AsyncSession, store_id: str) -> List[Dict[str, Any]]:
    # Get the latest event timestamp to use as relative "now" for historical dataset
    max_time_query = select(func.max(DBEvent.timestamp)).where(DBEvent.store_id == store_id)
    max_time_res = await session.execute(max_time_query)
    ref_now = max_time_res.scalar()
    
    if not ref_now:
        return []

    anomalies = []
    
    # 1. Dead Zone Check (no visits in last 30 minutes)
    #    Dynamically discover zones from events instead of hardcoding
    thirty_mins_ago = ref_now - timedelta(minutes=30)
    
    zone_query = select(DBEvent.zone_id).where(
        DBEvent.store_id == store_id,
        DBEvent.zone_id != None
    ).distinct()
    zone_res = await session.execute(zone_query)
    all_zones = [row[0] for row in zone_res.all() if row[0]]
    
    for zone in all_zones:
        visit_query = select(func.count()).where(
            DBEvent.store_id == store_id,
            DBEvent.zone_id == zone,
            DBEvent.timestamp >= thirty_mins_ago,
            DBEvent.timestamp <= ref_now,
            DBEvent.is_staff == False
        )
        visit_res = await session.execute(visit_query)
        visit_count = visit_res.scalar() or 0
        if visit_count == 0:
            anomalies.append({
                "type": "DEAD_ZONE",
                "severity": "WARN",
                "message": f"No visitor activity detected in zone '{zone}' for the last 30 minutes.",
                "suggested_action": f"Verify shelf layout or check if camera feed for zone '{zone}' is misaligned.",
                "timestamp": ref_now
            })

    # 2. Queue Spike Check (from BILLING_QUEUE_JOIN queue_depth)
    fifteen_mins_ago = ref_now - timedelta(minutes=15)
    queue_query = select(DBEvent).where(
        DBEvent.store_id == store_id,
        DBEvent.event_type == "BILLING_QUEUE_JOIN",
        DBEvent.timestamp >= fifteen_mins_ago,
        DBEvent.timestamp <= ref_now
    )
    queue_res = await session.execute(queue_query)
    queue_events = queue_res.scalars().all()
    max_depth = max([ev.queue_depth for ev in queue_events if ev.queue_depth is not None], default=0)
    
    if max_depth > 5:
        severity = "CRITICAL" if max_depth > 8 else "WARN"
        anomalies.append({
            "type": "QUEUE_SPIKE",
            "severity": severity,
            "message": f"Billing queue depth spiked to {max_depth} visitors.",
            "suggested_action": "Deploy additional cashiers to billing counter immediately.",
            "timestamp": ref_now
        })

    # 3. Conversion Drop Check — compare current conversion rate against expected baseline
    metrics = await compute_store_metrics(session, store_id)
    conv_rate = metrics["conversion_rate"]
    
    # Compute a simple trailing average from all available data as a baseline
    # If there's enough data, use a 7-day lookback vs current window
    seven_days_ago = ref_now - timedelta(days=7)
    
    # Count transactions in the last 7 days for a baseline
    tx_count_query = select(func.count()).select_from(DBTransaction).where(
        DBTransaction.store_id == store_id,
        DBTransaction.timestamp >= seven_days_ago
    )
    tx_res = await session.execute(tx_count_query)
    trailing_tx_count = tx_res.scalar() or 0
    
    # If store has visitors but low conversion relative to baseline
    if metrics["unique_visitors"] > 5 and conv_rate < 0.10:
        anomalies.append({
            "type": "CONVERSION_DROP",
            "severity": "WARN" if conv_rate >= 0.05 else "CRITICAL",
            "message": f"Conversion rate is low at {conv_rate * 100:.1f}% ({trailing_tx_count} transactions in trailing window).",
            "suggested_action": "Launch checkout promotion or inspect pricing/offers at checkout. Review if staff engagement is sufficient.",
            "timestamp": ref_now
        })
        
    return anomalies
