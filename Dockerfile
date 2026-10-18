# --- build the React dashboard
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- API + static dashboard in one process
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN useradd --create-home --uid 10001 anops
WORKDIR /app
COPY backend/requirements.txt backend/
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY --from=web /web/dist frontend/dist
RUN mkdir -p backup_storage secrets && chown -R anops:anops /app
USER anops
WORKDIR /app/backend
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/api/v1/health')"
# ONE worker on purpose: scheduler + per-device locks are in-process (see README "Scaling out")
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1"]
