FROM ubuntu:24.04

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# Install system dependencies
# Ubuntu 24.04 includes FFmpeg 6.1/7.0 headers natively, which PyAV 14.x strictly requires to compile!
RUN apt-get update && apt-get install -y --no-install-recommends software-properties-common && \
    add-apt-repository ppa:deadsnakes/ppa -y && \
    apt-get update

# - build-essential, pkg-config, and libav*-dev are required to build wheels for packages like 'av'
# - libreoffice and poppler-utils are required for PPTX and PDF processing used in app.py
# - wget and xz-utils are needed to fetch FFmpeg 7
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    pkg-config \
    libreoffice \
    poppler-utils \
    wget \
    xz-utils \
    ca-certificates \
    libgl1 \
    libglib2.0-0 \
    python3.11 \
    python3.11-dev \
    python3.11-venv \
    python3-pip \
    # Core FFmpeg development headers (from Debian Bookworm, likely 5.x/6.x)
    libavcodec-dev \
    libavformat-dev \
    libswscale-dev \
    libavdevice-dev \
    libavfilter-dev \
    libavutil-dev \
    # Additional build dependencies for FFmpeg-related libraries like 'av'
    yasm \
    nasm \
    zlib1g-dev \
    libx264-dev \
    libx265-dev \
    libvpx-dev \
    libopus-dev \
    libmp3lame-dev \
    libfdk-aac-dev \
    && rm -rf /var/lib/apt/lists/*

# Install FFmpeg 7 (Static build for application runtime)
# This ensures we use exactly version 7 as required.
RUN wget https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz \
    && tar xvf ffmpeg-release-amd64-static.tar.xz \
    && mv ffmpeg-*-amd64-static/ffmpeg /usr/local/bin/ \
    && mv ffmpeg-*-amd64-static/ffprobe /usr/local/bin/ \
    && rm -rf ffmpeg-release-amd64-static.tar.xz ffmpeg-*-amd64-static

# Verify FFmpeg version
RUN ffmpeg -version

# Create a virtual environment to avoid Debian's system pip conflicts
RUN python3.11 -m venv /opt/venv
# Make sure we use the virtualenv Python and pip
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt && \
    sed -i 's/# import av/import av/g' /opt/venv/lib/python3.11/site-packages/lipsync/helpers.py

COPY . .

EXPOSE 5000

CMD ["gunicorn", "--conf", "gunicorn.conf.py", "app:app"]