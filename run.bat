@echo off
echo ==================================================================
echo         STORE INTELLIGENCE PIPELINE INITIALIZER (WINDOWS)
echo ==================================================================
echo.

:: Check models
if not exist "models\yolov8m.pt" (
    echo [INFO] Downloading YOLOv8 & DeepSORT models...
    python download_models.py
)

:: Activate environment
if exist ".venv\Scripts\activate.bat" (
    echo [INFO] Activating virtual environment...
    call .venv\Scripts\activate.bat
) else (
    echo [WARNING] No virtual environment found. Running with global python.
)

:: Run API Server
echo [INFO] Starting FastAPI server on http://localhost:8000 ...
echo [INFO] Close this window to stop, or start other components:
echo [INFO] - Web UI: cd ui\web && npm run dev
echo [INFO] - Terminal UI: python ui\terminal\main.py
echo.
uvicorn api.main:app --host 0.0.0.0 --port 8000
