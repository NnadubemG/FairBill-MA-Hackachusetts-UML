FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app_server ./app_server
COPY backend ./backend
COPY contracts ./contracts
COPY core ./core
COPY pipeline ./pipeline
COPY data/processed ./data/processed
COPY frontend ./frontend

EXPOSE 8000
CMD ["sh", "-c", "python -m app_server.server --port ${PORT} --data data/processed"]
