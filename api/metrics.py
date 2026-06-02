# api/metrics.py
from datetime import datetime, timedelta
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from api.db import DBEvent, DBTransaction
from typing import Dict, Any

async def compute_store_metrics(session: AsyncSession, store_id: str) -> Dict[str, Any]:
    # 1. Fetch all events for this store that are NOT staff
    event_query = select(DBEvent).where(DBEvent.store_id == store_id).where(DBEvent.is_staff == False)
    result = await session.execute(event_query)
    events = result.scalars().all()
    
    # 2. Fetch all transactions for this store
    tx_query = select(DBTransaction).where(DBTransaction.store_id == store_id)
    tx_result = await session.execute(tx_query)
    transactions = tx_result.scalars().all()
    
    # Unique visitors (by visitor_id)
    visitor_ids = {ev.visitor_id for ev in events}
    unique_visitors = len(visitor_ids)
    
    # Average dwell time per zone
    zone_dwells = {}  # zone_id -> list of dwells
    for ev in events:
        if ev.zone_id and ev.dwell_ms > 0:
            if ev.zone_id not in zone_dwells:
                zone_dwells[ev.zone_id] = []
            zone_dwells[ev.zone_id].append(ev.dwell_ms)
            
    avg_dwell_by_zone = {}
    for zone, dwells in zone_dwells.items():
        avg_dwell_by_zone[zone] = round(sum(dwells) / len(dwells), 2) if dwells else 0.0
        
    # Queue depth (from metadata of BILLING_QUEUE_JOIN)
    queue_depths = [ev.queue_depth for ev in events if ev.event_type == "BILLING_QUEUE_JOIN" and ev.queue_depth is not None]
    queue_depth = max(queue_depths) if queue_depths else 0
    
    # Abandonment Rate
    # Abandonment Rate = number of unique visitors with BILLING_QUEUE_ABANDON / unique visitors who entered billing area
    billing_enters = [ev for ev in events if ev.zone_id == "BILLING" and ev.event_type in ("ZONE_ENTER", "BILLING_QUEUE_JOIN")]
    billing_abandons = [ev for ev in events if ev.event_type == "BILLING_QUEUE_ABANDON"]
    
    billing_visitors = {ev.visitor_id for ev in billing_enters}
    abandon_visitors = {ev.visitor_id for ev in billing_abandons}
    total_billing_visits = len(billing_visitors)
    
    abandonment_rate = (len(abandon_visitors) / total_billing_visits) if total_billing_visits > 0 else 0.0
    
    # Conversion Rate calculation
    # "A visitor who was in the billing zone in the 5-minute window before a transaction timestamp
    #  counts as a converted visitor for that session."
    # Optimised: sort transactions by time, then for each billing event check via sorted lookup
    converted_visitors = set()
    billing_events = [ev for ev in events if ev.zone_id == "BILLING"]
    
    # Sort transactions for efficient matching
    sorted_transactions = sorted(transactions, key=lambda tx: tx.timestamp)
    
    for ev in billing_events:
        ev_time = ev.timestamp
        for tx in sorted_transactions:
            time_diff = tx.timestamp - ev_time
            total_seconds = time_diff.total_seconds()
            # Transaction must be within [0, 300] seconds after the billing event
            if total_seconds < 0:
                continue
            if total_seconds > 300:
                break  # sorted, so all further transactions are also too far
            converted_visitors.add(ev.visitor_id)
            break
                
    conversion_rate = (len(converted_visitors) / unique_visitors) if unique_visitors > 0 else 0.0
    
    return {
        "store_id": store_id,
        "unique_visitors": unique_visitors,
        "conversion_rate": round(conversion_rate, 4),
        "avg_dwell_by_zone": avg_dwell_by_zone,
        "queue_depth": queue_depth,
        "abandonment_rate": round(abandonment_rate, 4)
    }
