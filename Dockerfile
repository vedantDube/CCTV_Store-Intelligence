# Dockerfile
# Lightweight Python image for the API server.
# GPU-accelerated pipeline should run on the host or a separate GPU container.
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (opencv, git for deep-person-reid)
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    ffmpeg \
    libsm6 \
    libxext6 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirement file and install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Expose FastAPI port
EXPOSE 8000

# Start the FastAPI server
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
