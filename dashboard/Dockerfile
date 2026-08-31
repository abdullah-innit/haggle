FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1

# Cloud Run Services (unlike Jobs) must listen on the $PORT env var it injects
CMD exec gunicorn --bind :$PORT --workers 1 --threads 4 --timeout 0 app:app
