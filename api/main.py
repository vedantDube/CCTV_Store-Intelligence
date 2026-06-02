# api/main.py
import uuid
import time
import json
import logging
from datetime import datetime, timezone
from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import select, func
from sqlmodel.ext.asyncio.session import AsyncSession

from api import db
from api.models import (
    IngestBatch, StoreMetricsResponse, FunnelResponse, 
    HeatmapResponse, AnomaliesResponse
)
from api.db import get_session, DBEvent
from api.ingestion import ingest_batch_events
from api.metrics import compute_store_metrics
from api.funnel import compute_store_funnel
from api.heatmap import compute_store_heatmap
from api.anomalies import detect_store_anomalies

# Setup logger
logger = logging.getLogger("store_intel")
logging.basicConfig(level=logging.INFO, format="%(message)s")

app = FastAPI(title="Store Intelligence API", version="0.1.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Structured Logging Middleware
@app.middleware("http")
async def structured_logging_middleware(request: Request, call_next):
    trace_id = str(uuid.uuid4())
    start_time = time.time()
    
    # Extract store_id from path if available
    store_id = None
    path_parts = request.url.path.strip("/").split("/")
    if "stores" in path_parts:
        try:
            idx = path_parts.index("stores")
            if idx + 1 < len(path_parts):
                store_id = path_parts[idx + 1]
        except ValueError:
            pass

    response = await call_next(request)
    
    latency = (time.time() - start_time) * 1000
    
    log_data = {
        "trace_id": trace_id,
        "store_id": store_id,
        "endpoint": request.url.path,
        "latency_ms": round(latency, 2),
        "status_code": response.status_code
    }
    
    # Read event count from request state if set during ingest
    event_count = getattr(request.state, "event_count", None)
    if event_count is not None:
        log_data["event_count"] = event_count
        
    logger.info(json.dumps(log_data))
    return response

# Startup database initialization
@app.on_event("startup")
async def on_startup():
    try:
        await db.init_db()
        logger.info("[STARTUP] Database and POS transactions initialized successfully.")
    except Exception as e:
        logger.error(f"[STARTUP] Error initializing database: {e}")

# --------------------
# API Endpoints
# --------------------

@app.post("/events/ingest", response_class=JSONResponse)
async def ingest_events(batch: IngestBatch, request: Request, session: AsyncSession = Depends(get_session)):
    # Record event count for structured logging
    request.state.event_count = len(batch.events)
    
    if len(batch.events) > 500:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Batch size exceeds maximum limit of 500 events."
        )
        
    success_count, errors = await ingest_batch_events(session, batch.events)
    
    # If all events failed
    if success_count == 0 and errors:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"message": "All events failed ingestion", "errors": errors}
        )
        
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "message": f"Successfully processed {success_count} events.",
            "success_count": success_count,
            "errors": errors
        }
    )

@app.get("/stores/{id}/metrics", response_model=StoreMetricsResponse)
async def get_store_metrics(id: str, session: AsyncSession = Depends(get_session)):
    try:
        metrics = await compute_store_metrics(session, id)
        return metrics
    except Exception as e:
        # Graceful degradation: DB unavailable -> HTTP 503
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database query error or connection unavailable: {str(e)}"
        )

@app.get("/stores/{id}/funnel", response_model=FunnelResponse)
async def get_store_funnel(id: str, session: AsyncSession = Depends(get_session)):
    try:
        stages = await compute_store_funnel(session, id)
        return {"store_id": id, "stages": stages}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database query error or connection unavailable: {str(e)}"
        )

@app.get("/stores/{id}/heatmap", response_model=HeatmapResponse)
async def get_store_heatmap(id: str, session: AsyncSession = Depends(get_session)):
    try:
        heatmap_data = await compute_store_heatmap(session, id)
        return heatmap_data
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database query error or connection unavailable: {str(e)}"
        )

@app.get("/stores/{id}/anomalies", response_model=AnomaliesResponse)
async def get_store_anomalies(id: str, session: AsyncSession = Depends(get_session)):
    try:
        anomalies = await detect_store_anomalies(session, id)
        return {"store_id": id, "anomalies": anomalies}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database query error or connection unavailable: {str(e)}"
        )

@app.get("/health", response_class=JSONResponse)
async def health_check(session: AsyncSession = Depends(get_session)):
    try:
        # Query last event timestamp per store
        stmt = select(DBEvent.store_id, func.max(DBEvent.timestamp)).group_by(DBEvent.store_id)
        res = await session.execute(stmt)
        store_lags = {}
        stale_feed_warning = False
        
        utcnow = datetime.now(timezone.utc).replace(tzinfo=None)
        
        for store_id, last_timestamp in res.all():
            if last_timestamp:
                lag = utcnow - last_timestamp
                store_lags[store_id] = last_timestamp.isoformat() + "Z"
                # If lag is more than 10 minutes
                if lag.total_seconds() > 600:
                    stale_feed_warning = True
                    
        content = {
            "status": "healthy",
            "last_event_timestamps": store_lags
        }
        if stale_feed_warning:
            content["warning"] = "STALE_FEED"
            
        return JSONResponse(status_code=status.HTTP_200_OK, content=content)
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unhealthy", "error": f"Database connection failed: {str(e)}"}
        )
