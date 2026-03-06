# syntax=docker/dockerfile:1.7
# ── Stage 1: Python dependencies ──────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# System deps for OCR packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc g++ libffi-dev libssl-dev \
        # opencv headless runtime deps
        libglib2.0-0 libgl1 libsm6 libxext6 libxrender1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt          ./requirements_ocr.txt
COPY backend/requirements.txt  ./requirements_api.txt
RUN pip install --no-cache-dir -r requirements_ocr.txt -r requirements_api.txt

# ── Stage 2: Runtime image ────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Tesseract + Poppler (needed at runtime for transcript_to_csv.py / phase 2 OCR)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        tesseract-ocr poppler-utils \
        libglib2.0-0 libgl1 libsm6 libxext6 libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages \
     /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

WORKDIR /app

# Copy the application code
COPY audit_l1.py audit_l2.py audit_l3.py run_pipeline.py \
     transcript_to_csv.py program.md nsu_catalog.json ./
COPY backend/ ./backend/
COPY alembic/  ./alembic/
COPY alembic.ini ./

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
