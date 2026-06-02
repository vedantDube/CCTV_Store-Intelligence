#!/bin/bash
set -e

echo "=================================================================="
echo "        STORE INTELLIGENCE PIPELINE INITIALIZER (UNIX)"
echo "=================================================================="
echo ""

# Download models if not exists
if [ ! -f "models/yolov8m.pt" ]; then
    echo "[INFO] Downloading YOLOv8 & DeepSORT models..."
    python3 download_models.py
fi

# Activate virtualenv if exists
if [ -d ".venv" ]; then
    echo "[INFO] Activating virtual environment..."
    source .venv/bin/activate
fi

# Run backend API
echo "[INFO] Starting FastAPI server on port 8000..."
uvicorn api.main:app --host 0.0.0.0 --port 8000
