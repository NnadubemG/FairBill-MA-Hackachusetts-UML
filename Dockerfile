# FairBill MA container: one process serves the web app + JSON API.
# Works on any container host (Render, Fly.io, Railway, ECS, Cloud Run).
#
#   docker build -t fairbill-ma .
#   docker run -p 8000:8000 fairbill-ma
#   # live model mode: pass secrets at runtime, never bake them into the image
#   docker run -p 8000:8000 -e ANTHROPIC_API_KEY -e EXTRACT_MODEL_ID -e EXPLAIN_MODEL_ID -e LETTER_MODEL_ID fairbill-ma
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8000

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app_server ./app_server
COPY backend ./backend
COPY core ./core
COPY contracts ./contracts
COPY pipeline ./pipeline
COPY data/processed ./data/processed
COPY frontend ./frontend
COPY synthetic/samples ./synthetic/samples

RUN useradd --create-home --uid 10001 fairbill
USER fairbill

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/health',timeout=4)"
CMD ["python", "-m", "app_server.server"]
