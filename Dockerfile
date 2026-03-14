FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY *.py ./
COPY templates/ templates/

# Telegram session persists in /app/sessions
ENV TELEGRAM_SESSION_DIR=sessions
VOLUME ["/app/sessions"]

# Health check via Flask endpoint (if running web_app)
HEALTHCHECK --interval=60s --timeout=5s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')" || exit 1

# Default: run CLI bot. Override with CMD ["python", "web_app.py"] for dashboard.
CMD ["python", "main.py"]
