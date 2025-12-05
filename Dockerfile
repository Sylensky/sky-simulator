# Night Sky Simulator - Docker Image
# Provides a containerized environment for running the sky simulator

FROM python:3.11-slim

# Set labels
LABEL maintainer="Sylensky"
LABEL description="Night Sky Simulator - A Python GUI for simulating the night sky"
LABEL version="1.0.0"

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies for tkinter, X11, and Wayland support
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-tk \
    tk \
    # X11 libraries
    libx11-6 \
    libxext6 \
    libxrender1 \
    libxft2 \
    libfontconfig1 \
    # Wayland support (for WSL2/WSLg)
    libwayland-client0 \
    libwayland-cursor0 \
    libwayland-egl1 \
    # XWayland compatibility
    libxkbcommon0 \
    libxkbcommon-x11-0 \
    # Image support (for Pillow)
    libjpeg62-turbo \
    libpng16-16 \
    libwebp7 \
    zlib1g \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create app directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application
COPY sky_simulator/ ./sky_simulator/
COPY data/ ./data/
COPY run_sky_simulator.py .

# Set the display for X11 forwarding
ENV DISPLAY=:0

# Create a non-root user for security
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

# Default command
CMD ["python", "run_sky_simulator.py"]
