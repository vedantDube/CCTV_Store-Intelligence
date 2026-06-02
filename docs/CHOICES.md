# Architecture Decisions: Apex Retail Store Intelligence

This document outlines the rationale behind three key engineering decisions in the development of the Store Intelligence system. For each decision, we document the options considered, what AI tools suggested, and what was ultimately chosen — and why.

---

## 1. Detection Model Selection: YOLOv8m + DeepSORT OSNet

### Options Considered
1. **YOLOv8 Nano (YOLOv8n)**: Extremely fast (100+ FPS on CPU) but suffers from high localization errors and poor confidence in crowded retail checkouts, especially under partial occlusions. In testing on the provided footage, it frequently merged two adjacent people into a single bounding box, making group entry detection impossible.
2. **YOLOv8 Medium (YOLOv8m)**: Moderate size (25.9M parameters), excellent balance of detection accuracy (mAP 50.2 on COCO) and inference speed (15 FPS on standard CPU, 120 FPS on CUDA GPU). Resolves individual persons in groups reliably.
3. **YOLOv9 / RT-DETR**: More recent architectures with marginally better mAP, but significantly larger model sizes and less mature tooling. The Ultralytics ecosystem for YOLOv8 is production-proven with extensive documentation.
4. **LLaVA / Gemini VLMs**: State-of-the-art cognitive scene understanding, but too slow for real-time frame processing (average 2–5 seconds per frame for LLaVA, API latency for Gemini), making it highly impractical for continuous frame-by-frame customer tracking across 5 cameras.

### AI Suggestion & What I Changed
The AI assistant initially proposed using a visual language model (VLM) for direct zone and staff classification from frame crops. The specific suggestion was: *"Use GPT-4V or LLaVA to classify each detected person crop as customer/staff and identify their current zone."*

I tested this approach with LLaVA 1.5-7B locally on sample frames from the CCTV footage. Zone classification accuracy was ~65% — it often confused SKINCARE and MAKEUP zones since both contain similar product shelving. More critically, inference took 2-5 seconds per frame, which would require 10-25 seconds per frame across 5 cameras. This made it fundamentally incompatible with the real-time requirement.

Instead, the AI then suggested the YOLOv8m + DeepSORT combination with a specialized Re-ID model (`osnet_x0_25`), which I adopted. I chose the `_x0_25` variant (quarter-width) over the full `osnet_x1_0` because the smaller model still achieves 82.6% Rank-1 on Market-1501 while being 4x faster — important when processing 5 simultaneous camera feeds.

### Final Decision & Rationale
We selected **YOLOv8m + DeepSORT with OSNet Re-ID** running locally on CUDA.
* **Accuracy under Occlusion**: YOLOv8m provides the localization precision needed to segment individuals walking in groups or partially occluded by store displays. In the provided footage, it correctly separated 3-person groups that YOLOv8n merged into 1-2 detections.
* **Tracking Identity Stability**: OSNet extracts a 512-dimensional visual appearance embedding for each detected person. This allows DeepSORT to maintain visitor identity stable across camera angles, even when visitors go out of sight temporarily (cosine distance threshold: 0.25). This is critical for the re-entry detection requirement.
* **Staff Detection**: Rather than relying on VLM classification, I implemented a dual-heuristic approach: (1) HSV color analysis of the torso region to detect purple/dark uniforms, and (2) a "3-camera rule" — if a person is seen across 3+ different cameras, they are likely staff traversing the entire store rather than a customer browsing specific zones.

---

## 2. Event Schema Design Rationale

### Options Considered
1. **Fully Flat Relational Schema**: Individual columns for every field including all metadata — `queue_depth`, `sku_zone`, `session_seq` as top-level columns. Simplifies SQL queries but creates sparse columns (most events have `queue_depth = NULL`).
2. **Flexible Nested JSON Schema**: Primary event metadata as indexed columns with a flexible, nested `metadata` JSON field for context-specific parameters.
3. **Fully Normalized Schema**: Separate tables for events, zone visits, queue events, and sessions. Most correct from a relational design perspective but adds complex JOINs for every analytics query.

### AI Suggestion & What I Changed
The AI recommended Option 1 — keeping the database schema fully flat for SQL indexing: *"Store all fields as top-level columns for maximum query performance. Add indexes on store_id, visitor_id, event_type, and timestamp."*

I partially agreed but chose a **hybrid approach**. The Pydantic API schema uses nested `metadata` (Option 2) for extensibility and clean JSON representation, but the SQLModel database table flattens the metadata fields into top-level columns (similar to Option 1). This gives us:
- Clean nested JSON in the API contract (what external consumers see)
- Flat indexed columns in the database (what SQL queries use)
- The `ingestion.py` layer handles the mapping between the two

I rejected the fully normalized approach (Option 3) because the analytics queries need to aggregate across event types frequently. A funnel query that spans ENTRY → ZONE_ENTER → BILLING → POS would require 4+ JOINs with normalized tables, adding latency to what should be real-time endpoints.

### Final Decision & Rationale
We chose the **hybrid nested Pydantic / flat DB** structure:
* **UUID-v4 Event ID**: Guarantees global uniqueness across distributed pipeline instances. Allows the `/events/ingest` endpoint to perform idempotent upserts (`session.merge()`), protecting the database from duplicate transmissions in case of network retries. This was tested specifically with the idempotency test in `test_ingestion.py`.
* **State Sequencing**: Including a sequential `session_seq` counter tracks the customer journey in a clean chronological list (Entry → Zone Visit → Billing → Exit), making funnel analysis computationally lightweight — we simply check which stages each visitor_id reached.
* **Metadata Extensibility**: The nested metadata in the API schema allows future deployment-specific fields (e.g., `shelf_interaction_type`, `product_pickup_detected`) without requiring database migrations. The DB-side flat columns currently only contain the three required fields.

---

## 3. API Architecture: Async SQLModel with Graceful Degradation

### Options Considered
1. **Synchronous SQLAlchemy + SQLite**: Simplest implementation. No async complexity. But blocks the event loop during database queries, causing high latency under concurrent requests.
2. **Async SQLModel + PostgreSQL only**: Production-correct but fails to start without a running PostgreSQL instance. Breaks the "5-command setup" requirement.
3. **Async SQLModel with dynamic fallback**: Attempts PostgreSQL, degrades to async SQLite when unavailable. More complex but enables both Docker and local development.

### AI Suggestion & What I Changed
The AI initially suggested Option 2 with a strict PostgreSQL requirement. When I explained the Docker dependency concern, it proposed the dynamic fallback pattern: *"On startup, attempt a test query to PostgreSQL. If it fails, swap the engine to SQLite."*

I accepted the pattern but made two key modifications:
1. **Module-level engine variable**: The AI suggested using a dependency injection factory to select the engine per-request. I instead used a module-level `active_engine` variable set once at startup, because:
   - Engine creation is expensive (connection pool initialization)
   - Switching engines mid-request would cause transaction inconsistency
   - The startup check is deterministic — if Postgres is down at startup, it won't magically appear during a request

2. **Added `check_same_thread=False`** for SQLite connections. The AI's initial SQLite fallback code crashed with `ProgrammingError: SQLite objects created in a thread can only be used in that same thread` because async SQLite requires this flag. This was a debugging insight from my own testing, not from AI.

### Final Decision & Rationale
* **PostgreSQL for Docker**: `docker compose up` provisions a healthy Postgres container with proper health checks. The API waits for Postgres via `depends_on: condition: service_healthy`.
* **SQLite for local development**: Running `uvicorn api.main:app` without Docker transparently uses `store_intelligence.db`, enabling immediate local testing without any database setup.
* **Structured logging**: Every request logs `trace_id`, `store_id`, `endpoint`, `latency_ms`, and `event_count` as JSON. This was an explicit requirement and was implemented as FastAPI middleware rather than per-endpoint logging, ensuring 100% coverage without code duplication.
* **Graceful error handling**: All analytics endpoints wrap queries in try/except blocks, returning HTTP 503 with structured error messages when the database is unavailable — no raw stack traces leak to API consumers.
