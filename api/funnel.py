# api/funnel.py
from datetime import datetime, timedelta
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from api.db import DBEvent, DBTransaction
from typing import List, Dict, Any

async def compute_store_funnel(session: AsyncSession, store_id: str) -> List[Dict[str, Any]]:
    # 1. Fetch all events for this store that are NOT staff
    event_query = select(DBEvent).where(DBEvent.store_id == store_id).where(DBEvent.is_staff == False)
    result = await session.execute(event_query)
    events = result.scalars().all()
    
    # 2. Fetch all transactions for this store
    tx_query = select(DBTransaction).where(DBTransaction.store_id == store_id)
    tx_result = await session.execute(tx_query)
    transactions = tx_result.scalars().all()

    # Identify all unique visitors
    unique_visitors = {ev.visitor_id for ev in events}
    
    # Track which stage each visitor reached
    visitor_stages = {vid: {"entry": True, "zone_visit": False, "billing": False, "purchase": False} for vid in unique_visitors}
    
    # Process events to check stages
    for ev in events:
        vid = ev.visitor_id
        # Stage 1: Zone Visit (any non-ENTRY/EXIT and non-BILLING zone)
        if ev.zone_id and ev.zone_id not in ("ENTRY", "EXIT", "BILLING"):
            visitor_stages[vid]["zone_visit"] = True
            
        # Stage 2: Billing Queue (any billing interaction)
        if ev.zone_id == "BILLING":
            visitor_stages[vid]["billing"] = True
            
            # Stage 3: Purchase (matched POS transaction)
            for tx in transactions:
                time_diff = tx.timestamp - ev.timestamp
                if timedelta(seconds=0) <= time_diff <= timedelta(minutes=5):
                    visitor_stages[vid]["purchase"] = True
                    break

    # Aggregate counts
    entry_count = len(unique_visitors)
    zone_visit_count = sum(1 for v in visitor_stages.values() if v["zone_visit"])
    billing_count = sum(1 for v in visitor_stages.values() if v["billing"])
    purchase_count = sum(1 for v in visitor_stages.values() if v["purchase"])
    
    # Funnel stages with drop-off percentages relative to the previous stage
    stages = [
        {
            "stage_name": "Entry",
            "count": entry_count,
            "drop_off_pct": 0.0
        },
        {
            "stage_name": "Zone Visit",
            "count": zone_visit_count,
            "drop_off_pct": round(((entry_count - zone_visit_count) / entry_count * 100.0), 2) if entry_count > 0 else 0.0
        },
        {
            "stage_name": "Billing Queue",
            "count": billing_count,
            "drop_off_pct": round(((zone_visit_count - billing_count) / zone_visit_count * 100.0), 2) if zone_visit_count > 0 else 0.0
        },
        {
            "stage_name": "Purchase",
            "count": purchase_count,
            "drop_off_pct": round(((billing_count - purchase_count) / billing_count * 100.0), 2) if billing_count > 0 else 0.0
        }
    ]
    
    return stages
