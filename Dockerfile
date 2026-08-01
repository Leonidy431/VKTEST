# Multi-stage build for ROV agent Docker image
# Target: Raspberry Pi 3 (arm32v7)

FROM arm32v7/python:3.11-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libssl-dev \
    libffi-dev \
    python3-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt /tmp/requirements.txt

# Build Python wheels
RUN pip install --no-cache-dir --user --wheel \
    --wheel-dir /tmp/wheels \
    -r /tmp/requirements.txt

# ============ Runtime stage ============

FROM arm32v7/python:3.11-slim

LABEL maintainer="ROV Autonomous System"
LABEL description="Autonomous Underwater Vehicle (AUV) Control Agent"

# Install runtime dependencies only
RUN apt-get update && apt-get install -y \
    # GPIO/I2C/SPI drivers
    python3-smbus \
    python3-gpiozero \
    python3-rpi.gpio \
    \
    # Serial communication
    python3-serial \
    \
    # System utilities
    curl \
    sqlite3 \
    \
    # Audio/media (for sonar processing)
    libavformat58 \
    libavcodec58 \
    libswresample3 \
    libopus0 \
    libvpx6 \
    \
    # WebRTC dependencies
    libopus-dev \
    libvpx-dev \
    libsrtp2-dev \
    pkg-config \
    \
    # Performance monitoring
    htop \
    sysstat \
    \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy Python wheels from builder
COPY --from=builder /tmp/wheels /tmp/wheels

# Install wheels
RUN pip install --no-cache-dir --no-index \
    --find-links /tmp/wheels \
    $(pip install --dry-run --no-index --find-links /tmp/wheels \
      -r /tmp/wheels/requirements.txt 2>/dev/null | awk '{print $3}') \
    && rm -rf /tmp/wheels

# Copy application code
COPY robotics/ /app/robotics/
COPY docs/ /app/docs/

# Create non-root user for security
RUN useradd -m -u 1000 rover && \
    chown -R rover:rover /app

USER rover

# Expose WebRTC and monitoring ports
EXPOSE 9000/udp   # WebRTC P2P data
EXPOSE 8080/tcp   # REST monitoring API
EXPOSE 5000/tcp   # Dashboard

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV ROBOT_ID=rov-001
ENV LOG_LEVEL=DEBUG

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import os; print('OK') if os.path.exists('/tmp/rov_health') else exit(1)"

# Entrypoint
ENTRYPOINT ["python3", "-u", "robotics/autonomous_agent_main.py"]
