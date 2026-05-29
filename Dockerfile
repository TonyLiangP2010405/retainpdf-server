FROM python:3.11-slim

WORKDIR /app

# Install system deps (git for cloning retain-pdf source)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       git curl build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install retain-pdf dependencies
RUN pip install --no-cache-dir Pillow==10.4.0 PyMuPDF==1.26.5 pikepdf==7.2.0 requests==2.32.5 urllib3==2.5.0

# Copy server code
COPY app ./app

# Create data dirs
RUN mkdir -p /data/uploads /data/outputs /data/temp /data/logs

# Clone retain-pdf source (or mount as volume in dev)
# You can override RETAIN_PDF_ROOT to point to an existing clone.
ARG RETAIN_PDF_BRANCH=main
RUN git clone --depth 1 https://github.com/wxyhgk/retain-pdf.git /app/retain-pdf || true

ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    SERVER_HOST=0.0.0.0 \
    SERVER_PORT=8000 \
    UPLOAD_DIR=/data/uploads \
    OUTPUT_DIR=/data/outputs \
    TEMP_DIR=/data/temp \
    JOB_DB=/data/jobs.db \
    RETAIN_PDF_ROOT=/app/retain-pdf \
    LOG_DIR=/data/logs

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
