FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Force UTF-8 output — same class of bug that crashed counterparty_server.py
# on Windows earlier (emoji in a print statement + non-UTF-8 default encoding).
# Linux containers usually default to UTF-8 already, but this is cheap insurance.
ENV PYTHONIOENCODING=utf-8
# Make print() output show up in Cloud Run logs immediately instead of
# sitting in a buffer until the process exits.
ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py", "--batch", "services.json"]
