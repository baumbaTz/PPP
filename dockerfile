# Use a lightweight base image
FROM ubuntu:24.04

# Install essential packages and build tools
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    cmake \
    curl \
    libfftw3-dev \
    python3 \
    python3-pip \
    python3-venv

# Create a Python virtual environment
RUN python3 -m venv /opt/venv

# Activate the virtual environment and install dependencies
RUN /opt/venv/bin/pip install numpy requests

# Set the PATH to include the virtual environment
ENV PATH="/opt/venv/bin:$PATH"

# Clone and build whisper.cpp
RUN git clone https://github.com/ggerganov/whisper.cpp.git /whisper.cpp && \
    cd /whisper.cpp && \
    make

# Copy the Python script into the container
COPY transcribe-me.py /app/transcribe-me.py

# Set the working directory
WORKDIR /app

# Set the entrypoint
ENTRYPOINT ["python3", "transcribe-me.py"]
