# api/models.py
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

class EventMetadata(BaseModel):
    queue_depth: Optional[int] = None
    sku_zone: Optional[str] = None
    session_seq: Optional[int] = None

class EventModel(BaseModel):
    event_id: str = Field(..., description="UUID-v4 globally unique identifier")
    store_id: str = Field(..., description="Store identifier")
    camera_id: str = Field(..., description="Camera identifier")
    visitor_id: str = Field(..., description="Persistent Re-ID visitor token")
    event_type: str = Field(..., description="ENTRY, EXIT, ZONE_ENTER, ZONE_EXIT, ZONE_DWELL, BILLING_QUEUE_JOIN, BILLING_QUEUE_ABANDON, REENTRY")
    timestamp: datetime = Field(..., description="ISO-8601 UTC timestamp")
    zone_id: Optional[str] = Field(None, description="Retail zone identifier, null for ENTRY/EXIT")
    dwell_ms: int = Field(0, description="Dwell duration in milliseconds")
    is_staff: bool = Field(False, description="Whether the tracked person is staff")
    confidence: float = Field(..., description="Model detection confidence [0.0, 1.0]")
    metadata: Optional[EventMetadata] = None

class IngestBatch(BaseModel):
    events: List[EventModel]

class StoreMetricsResponse(BaseModel):
    store_id: str
    unique_visitors: int
    conversion_rate: float
    avg_dwell_by_zone: Dict[str, float]
    queue_depth: int
    abandonment_rate: float

class FunnelStage(BaseModel):
    stage_name: str
    count: int
    drop_off_pct: float

class FunnelResponse(BaseModel):
    store_id: str
    stages: List[FunnelStage]

class HeatmapItem(BaseModel):
    zone_id: str
    visit_frequency: int
    avg_dwell_ms: float
    normalized_score: float

class HeatmapResponse(BaseModel):
    store_id: str
    heatmap: List[HeatmapItem]
    data_confidence: bool

class AnomalyItem(BaseModel):
    type: str
    severity: str  # INFO / WARN / CRITICAL
    message: str
    suggested_action: str
    timestamp: datetime

class AnomaliesResponse(BaseModel):
    store_id: str
    anomalies: List[AnomalyItem]
