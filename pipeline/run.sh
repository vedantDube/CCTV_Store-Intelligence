#!/bin/bash
set -e

# Run pipeline script with default frame step 15 (1fps)
echo "[RUNNER] Launching video intelligence pipeline..."
python -m pipeline.run --step 15 --url http://localhost:8000/events/ingest --layout Revised
