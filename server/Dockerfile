# syntax=docker/dockerfile:1
# Build from the repository root:
#   docker build -f server/Dockerfile -t medbill .

# Compile the React frontend inside Render's Linux build environment. Production
# builds use the real same-origin /api routes rather than fixtures.
FROM node:22-slim AS frontend-builder
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
COPY contracts/ /build/contracts/
ENV VITE_USE_FIXTURES=false
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app:/app/server \
    PORT=8000
WORKDIR /app

# Keep Python dependencies single-sourced in pyproject.toml without requiring a
# packaging backend for the server itself.
COPY server/pyproject.toml /app/server/pyproject.toml
RUN pip install --upgrade pip && python - <<'PY'
import pathlib, subprocess, sys, tomllib
config = tomllib.loads(pathlib.Path('/app/server/pyproject.toml').read_text())
subprocess.check_call([sys.executable, '-m', 'pip', 'install', *config['project']['dependencies']])
PY

COPY contracts/ /app/contracts/
COPY server/ /app/server/
COPY --from=frontend-builder /build/frontend/dist/ /app/frontend/dist/

WORKDIR /app/server
EXPOSE 8000
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
