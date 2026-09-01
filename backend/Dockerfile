FROM python:3.11-slim

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY config.yaml .

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s CMD python -c "import os,urllib.request;urllib.request.urlopen(f\"http://localhost:{os.environ.get('PORT','8000')}/health\")"
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
