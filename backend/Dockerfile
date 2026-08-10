# Backend image for the AI Executive Assistant (private/local mode ready).
FROM python:3.11-slim

WORKDIR /app

# ffmpeg: robust audio decoding for local Whisper.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-local.txt requirements.txt ./
RUN pip install --no-cache-dir -r requirements-local.txt

COPY app ./app
COPY templates ./templates
COPY static ./static

ENV DATA_DIR=/app/data \
    PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
