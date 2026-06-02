# Store Intelligence Analytics System (Apex Retail Solution)

This repository implements a production-grade, containerized computer-vision and POS transaction correlation system for retail store intelligence.

Starting from raw CCTV video feeds, the system tracks visitors across cameras, screens out store staff based on uniform color check, maps shoppers to layout-defined brand coordinates, computes real-time business conversion metrics, and visualizes them on a glassmorphic dashboard.

---

## 1. Quick Start Setup (5 Commands)

To run the complete system locally, execute the following commands in order:

```bash
# 1. Install all dependencies and models
uv pip install -r requirements.txt

# 2. Start the FastAPI analytics API
.venv\Scripts\python.exe -m uvicorn api.main:app --host 0.0.0.0 --port 8000

# 3. Process the CCTV clips and ingest events
$env:PYTHONPATH="."; uv run python -m pipeline.run --step 30 --layout Revised

# 4. Launch the Web UI dashboard
cd ui/web && npm install && npm run dev

# 5. Run the automated test suite with coverage
uv run python -m pytest --cov=api --cov-report=term-missing -v
```

---

## 2. Docker Execution

To launch the complete API and database stack inside Docker containers:

```bash
docker compose up --build
```
Once healthy, POST your events batch to `http://localhost:8000/events/ingest` and open the dashboard at `http://localhost:5173`.

---

## 3. Repository Structure

```
/store-intelligence/
├── pipeline/
│   ├── detect.py          # YOLOv8 detection wrapper
│   ├── track.py           # DeepSORT tracker with Re-ID embedding
│   ├── emit.py            # Batch JSONL serialization and API client
│   ├── run.py             # Main video sync, staff check & brand mapping
│   ├── vlm_processor.py   # Optional VLM scene analyzer (LLaVA)
│   ├── zone_classifier.py # Polygon-based zone classification
│   ├── run.sh             # Unix command runner
│   └── run.bat            # Windows command runner
├── api/
│   ├── main.py            # FastAPI entry point & API endpoints
│   ├── db.py              # Async SQLModel ORM & POS transactions csv importer
│   ├── ingestion.py       # Event validation, dedup & idempotent upsert
│   ├── metrics.py         # 5m window POS correlation logic
│   ├── funnel.py          # Session sequence analytics
│   ├── heatmap.py         # Normalized traffic & dwell scoring
│   ├── anomalies.py       # Spike & dead zone detection
│   └── models.py          # Pydantic schema validation
├── ui/
│   ├── web/               # React + Vite Glassmorphic Dashboard
│   └── terminal/          # Rich CLI Console Dashboard
├── tests/
│   ├── test_api.py        # API integration tests
│   ├── test_metrics.py    # Metrics calculation tests
│   ├── test_funnel.py     # Funnel & session dedup tests
│   ├── test_heatmap.py    # Heatmap normalization tests
│   ├── test_anomalies.py  # Anomaly detection tests
│   ├── test_ingestion.py  # Ingestion & idempotency tests
│   └── test_tracking.py   # Detection & tracking tests
├── docs/
│   ├── DESIGN.md          # Architecture & AI engineering decisions
│   └── CHOICES.md         # Model, schema, and style justifications
├── requirements.txt       # Core dependencies
├── docker-compose.yml     # PostgreSQL & API container configuration
├── Dockerfile             # Lightweight Python API image
└── README.md
```

---

## 4. API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/events/ingest` | Accepts batches of up to 500 events. Idempotent by event_id. |
| GET | `/stores/{id}/metrics` | Unique visitors, conversion rate, avg dwell, queue depth, abandonment |
| GET | `/stores/{id}/funnel` | Entry → Zone Visit → Billing Queue → Purchase with drop-off % |
| GET | `/stores/{id}/heatmap` | Zone visit frequency + avg dwell, normalized 0–100 |
| GET | `/stores/{id}/anomalies` | Dead zones, queue spikes, conversion drops with severity |
| GET | `/health` | Service status, last event timestamps, STALE_FEED warning |

---

## 5. Live Dashboard (Part E)

The web dashboard at `http://localhost:5173` provides:
- **North Star Metric** — Real-time conversion rate hero display
- **Animated KPI Cards** — Unique visitors, queue depth, abandonment rate with smooth transitions
- **Conversion Funnel** — 4-stage visualization with drop-off percentages
- **Store Floor Heatmap** — Zone popularity with heat-intensity coloring
- **Operational Alerts** — Queue spikes, dead zones, conversion drops with severity badges
- **CCTV Feed Status** — Per-camera online/offline indicators with zone tags

Data updates every 3 seconds via API polling. Toggle "Simulate" mode for demo data when API is offline.

---

## 6. Documentation

* **Architecture and AI decisions**: Read [DESIGN.md](docs/DESIGN.md).
* **Model choice, schema choice, and styling choice**: Read [CHOICES.md](docs/CHOICES.md).
