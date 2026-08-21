# Build from monorepo root (Render Root Directory = repo root)
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app

ENV HOST=0.0.0.0
ENV PORT=8000

EXPOSE 8000

CMD uvicorn app.main:app --host ${HOST} --port ${PORT}
