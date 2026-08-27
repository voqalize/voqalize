# A minimal container for the inbound brain — deployable to Cloud Run, Fly, ECS,
# or any platform that gives you a public HTTPS/WSS URL.
#
# The image carries only the SDK + FastAPI + uvicorn (no pipecat, no audio libs):
# the voice runtime lives on the far side of the socket, so a brain image stays
# small. Cloud Run terminates TLS and upgrades WebSockets for you, so the app
# speaks plain HTTP/WS on $PORT and PyGato reaches it over wss://.
FROM python:3.12-slim

WORKDIR /app

# Install the published, pinned SDK and server dependencies first for layer
# caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

# Cloud Run injects $PORT (default 8080); bind to it and to 0.0.0.0.
ENV PORT=8080
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT}"]
