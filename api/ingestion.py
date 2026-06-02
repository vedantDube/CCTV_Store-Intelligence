# api/ingestion.py
from sqlmodel.ext.asyncio.session import AsyncSession
from api.db import DBEvent
from api.models import EventModel
from typing import List, Tuple

# Valid event types as defined in the problem statement
VALID_EVENT_TYPES = {
    "ENTRY", "EXIT", "ZONE_ENTER", "ZONE_EXIT", "ZONE_DWELL",
    "BILLING_QUEUE_JOIN", "BILLING_QUEUE_ABANDON", "REENTRY"
}

async def ingest_batch_events(session: AsyncSession, events: List[EventModel]) -> Tuple[int, List[dict]]:
    """
    Ingests a batch of events. Deduplicates by event_id, validates, and stores.
    Returns: (successful_count, list_of_errors)
    
    Idempotent by design: if an event_id already exists, it is merged (upserted)
    rather than rejected, preventing duplicate errors on retries.
    """
    if not events:
        return 0, []
    
    success_count = 0
    errors = []
    
    for idx, ev in enumerate(events):
        try:
            # Validate critical required fields
            if not ev.event_id or not ev.store_id or not ev.visitor_id:
                raise ValueError("Missing critical fields: event_id, store_id, visitor_id")
            
            # Validate event_type against the known catalogue
            if ev.event_type not in VALID_EVENT_TYPES:
                raise ValueError(
                    f"Invalid event_type: '{ev.event_type}'. "
                    f"Must be one of: {', '.join(sorted(VALID_EVENT_TYPES))}"
                )
            
            # Validate confidence range
            if not (0.0 <= ev.confidence <= 1.0):
                raise ValueError(f"Confidence must be between 0.0 and 1.0, got {ev.confidence}")

            db_event = DBEvent(
                event_id=ev.event_id,
                store_id=ev.store_id,
                camera_id=ev.camera_id,
                visitor_id=ev.visitor_id,
                event_type=ev.event_type,
                timestamp=ev.timestamp,
                zone_id=ev.zone_id,
                dwell_ms=ev.dwell_ms,
                is_staff=ev.is_staff,
                confidence=ev.confidence,
                queue_depth=ev.metadata.queue_depth if ev.metadata else None,
                sku_zone=ev.metadata.sku_zone if ev.metadata else None,
                session_seq=ev.metadata.session_seq if ev.metadata else None
            )
            
            # Merge ensures idempotency: if event_id already exists, it is updated (or merged)
            await session.merge(db_event)
            success_count += 1
        except Exception as e:
            errors.append({
                "index": idx,
                "event_id": getattr(ev, 'event_id', 'unknown'),
                "error": str(e)
            })
            
    if success_count > 0:
        await session.commit()
        
    return success_count, errors
