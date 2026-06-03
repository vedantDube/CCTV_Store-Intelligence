# Design Document: Apex Retail Store Intelligence API

This document details the system design, data flow, component boundaries, and key technical decisions made during the development of the **Apex Retail Store Intelligence** edge AI system.

## 1. System Architecture

The system is designed as an end-to-end event-driven video intelligence pipeline combined with a production-grade analytics REST API. The architecture separates compute-heavy CV processing (pipeline) from lightweight analytics serving (API), enabling independent scaling.

```
+---------------------------------------------------------------------------------------------------+
|                                      EDGE DETECTION PIPELINE                                      |
|                                                                                                   |
|  [CAM 1.mp4] ----> YOLOv8 Detector ---> DeepSORT Tracker ---> Multi-Camera                       |
|  [CAM 2.mp4] ----> (Person Class)        (torchreid Re-ID)      Sync Logic ---> Events Generator  |
|  [CAM 3.mp4]                                                                          |           |
|  [CAM 4.mp4]                              Staff Color Filter ----+                     |           |
|  [CAM 5.mp4]                              (HSV Torso Analysis)   |                     v           |
+------------------------------------------------|----------------|--------------------- | ----------+
                                                 |                |                      | (JSON Batch)
                                                 v                v                      v
                                          [is_staff flag]  [3-Camera Rule]   [events.jsonl + POST]
                                                                                         |
+---------------------------------------------------------------------------------------------------+
|                                       ANALYTICS CLOUD API                                         |
|                                                                                                   |
|                      +------------------ [POST /events/ingest] -------------------+               |
|                      |                                                            |               |
|                      v                                                            v               |
|               Idempotency Check                                           Async DB Session        |
|               (Upsert Event ID)                                           (PostgreSQL/SQLite)     |
|                      |                                                            |               |
|                      +--------------------------> DB <----------------------------+               |
|                                                   ^                                               |
|                                                   | (POS CSV Import on Startup)                   |
|                                                   |                                               |
|        [GET /metrics] ------> Correlates billing zone dwells with POS (5m window)                 |
|        [GET /funnel] -------> Aggregates Session sequences (Entry -> Zone -> Bill -> Pay)         |
|        [GET /heatmap] ------> Normalized Visit count and Dwell Times (0-100 scores)               |
|        [GET /anomalies] ----> Detects dead zones, conversion drops, queue spikes                  |
|        [GET /health] -------> Per-store last event timestamp + STALE_FEED detection               |
+---------------------------------------------------------------------------------------------------+
```

---

## 2. Key Components

### 2.1 Video Ingestion & Tracking Pipeline (`pipeline/`)
* **`pipeline/detect.py`**: Integrates the Ultralytics YOLOv8m object detection model, extracting bounding boxes with class confidence filters for the `person` class. Uses GPU (CUDA) when available, with automatic CPU fallback.
* **`pipeline/track.py`**: Implements DeepSORT tracking using a PyTorch OSNet Re-ID feature extractor (`osnet_x0_25`) to identify and track visitors frame-by-frame. Includes IoU-based fallback matching when Re-ID embeddings are unavailable.
* **`pipeline/run.py`**: The core execution runner. It processes the 5 retail camera angles in a time-synchronized frame loop, extracts tracking features, implements cross-camera Re-ID matching via cosine distance (threshold: 0.25), excludes store staff using rule-based uniform color matching (HSV torso analysis for purple/dark clothing), segments shelves into layout-based brand coordinates, and translates raw coordinates into business events.
* **`pipeline/emit.py`**: Standardizes, batches (up to 500), and posts events to the REST ingestion API. Handles datetime serialization and network error recovery.
* **`pipeline/vlm_processor.py`**: Optional Visual Language Model (LLaVA 1.5-7B) processor for scene understanding. Supports both real inference and high-fidelity mock responses for development. Evaluated during development for zone classification (see AI-Assisted Decisions below).
* **`pipeline/zone_classifier.py`**: OpenCV polygon-based zone classifier using foot-point projection for persons and centroid for objects.

### 2.2 Store Analytics API (`api/`)
* **`api/main.py`**: Exposes FastAPI REST endpoints (`POST /events/ingest`, `/metrics`, `/funnel`, `/heatmap`, `/anomalies`, `/health`) with structured JSON logging middleware (trace_id, latency_ms, event_count).
* **`api/db.py`**: Sets up async SQLModel database schemas (`DBEvent` and `DBTransaction`) with a dynamic database fallback system — attempts PostgreSQL, gracefully degrades to SQLite. Automatically imports POS transaction records on app startup.
* **`api/ingestion.py`**: Handles event validation against the event type catalogue, idempotent upserts via `session.merge()`, partial success with structured error reporting.
* **`api/metrics.py`**: Computes unique visitors (staff-excluded), conversion rate via 5-minute POS window correlation, average dwell time per zone, queue depth, and abandonment rate.
* **`api/funnel.py`**: Session-based conversion funnel (Entry → Zone Visit → Billing Queue → Purchase) with drop-off percentage calculations. Deduplicates re-entry visitors by keying on visitor_id.
* **`api/heatmap.py`**: Zone visit frequency and average dwell, normalized to 0–100 scores, with a `data_confidence` flag when fewer than 20 unique sessions exist.
* **`api/anomalies.py`**: Detects dead zones (no visits in 30 min), queue spikes (>5 depth), and conversion drops. Uses dynamic zone discovery from actual events rather than hardcoded zone lists.

---

## 3. AI-Assisted Decisions

During implementation, several design challenges arose where AI-assisted reasoning helped shape the code structure. Below are three specific instances where LLM tools directly influenced architectural decisions.

### 3.1 Resolving Broken torchreid PyPI Dependencies
* **Challenge**: The PyPI package `torchreid` was broken due to compatibility mismatches with newer torch distributions. Running `pip install torchreid` failed with compilation errors on both Linux and Windows.
* **AI Prompt Used**: *"I need to install torchreid for DeepSORT Re-ID in a Python 3.11 environment with torch 2.2.0. The PyPI package fails to compile. What are alternative installation methods?"*
* **LLM Suggestion**: The AI suggested using the official developer source repository `git+https://github.com/KaiyangZhou/deep-person-reid.git` installed with `--no-build-isolation` after pre-building `Cython` and `wheel` inside requirements.txt.
* **What I Changed**: Accepted the suggestion but also added `setuptools==69.5.1` pinning after encountering a secondary build failure without it. The final requirements.txt reflects both the AI suggestion and my iterative debugging.
* **Outcome**: This successfully bypassed the dependency compiling errors and enabled the DeepSORT tracking module to load the OSNet model parameters seamlessly.

### 3.2 Dynamic Database Fallback System
* **Challenge**: During local execution, Docker is frequently offline. Connecting directly to a remote Postgres database throws immediate connection exceptions, failing health checks and crashing the development environment. But we needed PostgreSQL support for the Docker deployment.
* **AI Prompt Used**: *"My FastAPI app connects to PostgreSQL via DATABASE_URL but I want it to gracefully fall back to SQLite when Postgres is unavailable. How should I implement this with SQLAlchemy async engines?"*
* **LLM Suggestion**: The AI proposed implementing a self-healing check-connectivity block inside `api/db.py`. On startup, the API attempts a test query against Postgres; if it fails due to network or `getaddrinfo` exceptions, it automatically swaps the active SQLAlchemy engine to a local SQLite instance (`sqlite+aiosqlite:///store_intelligence.db`).
* **What I Changed**: I agreed with the approach but restructured the code to use a module-level `active_engine` variable rather than the AI's original suggestion of a context manager, since the engine needs to persist across requests. I also added the `check_same_thread=False` parameter for SQLite which the AI initially missed.
* **Outcome**: This ensures the application degrades gracefully and functions out-of-the-box on clean environments, regardless of Docker container statuses. The `/health` endpoint accurately reflects which database is active.

### 3.3 Multi-Camera Independent Tracking State
* **Challenge**: The initial single active camera visitor model caused state-flapping. Because camera fields of view overlap, a person detected on CAM 1 (Entry) and CAM 2 (FOH) at the same frame index flapped back and forth, resetting their zone entry time and reducing all dwell metrics to zero. This was the hardest bug to diagnose.
* **AI Prompt Used**: *"My multi-camera person tracker has state flapping — a visitor alternates between CAM 1 and CAM 2 zones every frame because they appear in both camera feeds simultaneously. How should I model zone state per visitor?"*
* **LLM Suggestion**: The AI suggested tracking active zones independently as a dictionary mapping (`camera_id -> [enter_time, last_seen_time, last_dwell_emit, zone_id]`). Zone transitions are handled asynchronously when a person goes unseen on a camera for more than 40 seconds, rather than immediately on zone change.
* **What I Changed**: I accepted the dictionary approach but overrode the AI's suggested timeout of 30 seconds, increasing it to 40 seconds based on empirical testing — at 30s, fast-walking customers triggered false zone exits between the FOH and SKINCARE cameras. I also added the "3-camera rule" for staff detection (if a person appears on 3+ cameras, they are likely staff moving through the entire store, not a customer browsing).
* **Outcome**: This successfully eliminated state flapping, yielding precise, non-zero customer dwell times and accurate conversion metrics. The 40-second timeout was validated against the 20-minute clips where typical zone visit durations ranged from 45 seconds to 5 minutes.

### 3.4 VLM Evaluation for Zone Classification (Overridden)
* **Evaluation Prompt**: *"Can you classify which retail zone this person is in based on this frame crop? The zones are: ENTRY, FOH, MAKEUP, SKINCARE, BILLING."*
* **Models Tested**: LLaVA 1.5-7B (local), GPT-4V (API)
* **Results**: LLaVA achieved ~65% zone classification accuracy on sample frames but required 2-5 seconds per frame, making it impractical for the 15fps pipeline. GPT-4V was more accurate (~80%) but too expensive for continuous frame processing.
* **Decision**: Overrode the VLM approach in favor of deterministic camera-to-zone mapping from `store_layout.json`. Each camera has a fixed zone assignment, and sub-zone brand mapping uses normalized x-coordinates from the bounding box centroid. This is 100% accurate for zone assignment (since each camera covers exactly one zone) and has zero latency overhead.
* **The VLM processor remains in `pipeline/vlm_processor.py`** as an optional module that could be activated for stores where cameras cover multiple zones, but is not used in the current single-zone-per-camera deployment.

---

## 4. Edge Case Handling Strategy

| Edge Case | Detection Approach | Confidence Impact |
|-----------|-------------------|-------------------|
| Group entry (2-4 people) | YOLOv8m resolves individual bounding boxes; DeepSORT assigns separate track IDs | Confidence may drop to 0.5-0.7 for overlapping persons |
| Staff movement | HSV torso analysis (purple/dark uniform) + 3-camera rule | Staff flag retroactively applied to all events for that visitor |
| Re-entry | Cosine distance matching (threshold 0.25) against feature gallery | REENTRY event emitted instead of new ENTRY |
| Partial occlusion | Low-confidence detections retained (not suppressed) with `confidence` field | Consumers can filter by confidence threshold |
| Empty periods | Pipeline correctly emits no events; API returns zero metrics without errors | data_confidence flag warns about sparse data |
| Billing queue abandonment | BILLING_QUEUE_ABANDON emitted when visitor exits billing zone without POS match | Cross-references event log for prior BILLING_QUEUE_JOIN |
