# Marwa Chatbot — Docker Image
# Python 3.12 slim, multi-stage for minimal size.
#
# Build:
#   docker build -t marwa-chatbot .
#
# Run:
#   docker run -p 8000:8000 --env-file .env marwa-chatbot
#
# Or with explicit env vars:
#   docker run -p 8000:8000 \
#     -e SUPABASE_URL=... \
#     -e SUPABASE_SERVICE_ROLE_KEY=... \
#     -e SUPABASE_ANON_KEY=... \
#     -e SHOP_OWNER_ID=... \
#     -e TELEGRAM_BOT_TOKEN=... \
#     marwa-chatbot

FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ── Runtime stage ─────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY src/ ./src/
COPY telegram_bot.py .

# Create non-root user
RUN groupadd -r marwa && useradd -r -g marwa marwa && \
    chown -R marwa:marwa /app
USER marwa

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Start the FastAPI service
CMD ["python3", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
