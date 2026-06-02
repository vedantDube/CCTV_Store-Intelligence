# api/heatmap.py
from sqlmodel import select, func
from sqlmodel.ext.asyncio.session import AsyncSession
from api.db import DBEvent
from typing import List, Dict, Any

async def compute_store_heatmap(session: AsyncSession, store_id: str) -> Dict[str, Any]:
    # 1. Fetch all events for this store that are NOT staff
    event_query = select(DBEvent).where(DBEvent.store_id == store_id).where(DBEvent.is_staff == False)
    result = await session.execute(event_query)
    events = result.scalars().all()

    unique_sessions = len({ev.visitor_id for ev in events})
    data_confidence = unique_sessions >= 20

    # Dynamically discover zones from events instead of hardcoding
    zone_query = select(DBEvent.zone_id).where(
        DBEvent.store_id == store_id,
        DBEvent.zone_id != None
    ).distinct()
    zone_res = await session.execute(zone_query)
    discovered_zones = [row[0] for row in zone_res.all() if row[0]]
    
    # Fall back to defined zones if no events exist
    defined_zones = discovered_zones if discovered_zones else ["FOH", "MAKEUP", "SKINCARE", "BILLING"]
    
    zone_stats = {z: {"freq": 0, "dwells": []} for z in defined_zones}

    for ev in events:
        if ev.zone_id in zone_stats:
            if ev.event_type == "ZONE_ENTER":
                zone_stats[ev.zone_id]["freq"] += 1
            if ev.event_type == "ZONE_DWELL" and ev.dwell_ms > 0:
                zone_stats[ev.zone_id]["dwells"].append(ev.dwell_ms)

    heatmap_items = []
    
    # Extract frequencies and average dwells
    freqs = []
    avg_dwells = []
    
    for zone in defined_zones:
        freq = zone_stats[zone]["freq"]
        dwells = zone_stats[zone]["dwells"]
        avg_dwell = sum(dwells) / len(dwells) if dwells else 0.0
        
        freqs.append(freq)
        avg_dwells.append(avg_dwell)
        
    min_freq = min(freqs) if freqs else 0
    max_freq = max(freqs) if freqs else 0
    min_dwell = min(avg_dwells) if avg_dwells else 0.0
    max_dwell = max(avg_dwells) if avg_dwells else 0.0

    for i, zone in enumerate(defined_zones):
        freq = freqs[i]
        avg_dwell = avg_dwells[i]
        
        # Normalize freq (0 - 100)
        freq_norm = ((freq - min_freq) / (max_freq - min_freq) * 100.0) if max_freq > min_freq else (100.0 if freq > 0 else 0.0)
        # Normalize dwell (0 - 100)
        dwell_norm = ((avg_dwell - min_dwell) / (max_dwell - min_dwell) * 100.0) if max_dwell > min_dwell else (100.0 if avg_dwell > 0 else 0.0)
        
        normalized_score = round((freq_norm + dwell_norm) / 2.0, 2)
        
        heatmap_items.append({
            "zone_id": zone,
            "visit_frequency": freq,
            "avg_dwell_ms": round(avg_dwell, 2),
            "normalized_score": normalized_score
        })

    return {
        "store_id": store_id,
        "heatmap": heatmap_items,
        "data_confidence": data_confidence
    }
