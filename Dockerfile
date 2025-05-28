FROM --platform=linux/amd64 ubuntu:24.04 AS build

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    POETRY_VERSION=1.7.1 \
    FLASK_APP=coughOverflow:create_app \
    FLASK_RUN_HOST=0.0.0.0 \
    FLASK_RUN_PORT=8080 \
    PATH="/venv/bin:$PATH"

# Install system dependencies and Python
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    build-essential \
    wget \
    libssl-dev \
    libffi-dev \
    zlib1g-dev \
    libpq-dev \
    libjpeg-dev \
    libfreetype6-dev \
    liblcms2-dev \
    libblas-dev \
    liblapack-dev \
    steghide \
    && rm -rf /var/lib/apt/lists/*

# Create and activate a Python virtual environment
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Poetry
RUN pip install --upgrade pip && pip install poetry

# Set working directory to /app
WORKDIR /app
COPY pyproject.toml poetry.lock ./

# Install dependencies using Poetry
RUN poetry install --no-root --no-interaction
COPY . /app
COPY start-flask.sh /app/start-flask.sh
COPY aws.env /app/aws.env
RUN chmod +x /app/start-flask.sh
# Select architecture and download the corresponding overflowengine binary
RUN ARCH=$(dpkg --print-architecture) && \
    if [ "$ARCH" = "amd64" ]; then \
        wget https://github.com/CSSE6400/CoughOverflow-Engine/releases/download/v1.0/overflowengine-amd64 -O overflowengine; \
    else \
        wget https://github.com/CSSE6400/CoughOverflow-Engine/releases/download/v1.0/overflowengine-arm64 -O overflowengine; \
    fi && chmod +x /app/overflowengine

# Copy the "todo" folder to the container


# Set Flask app environment variable
ENV FLASK_APP=todo

# Start Flask using Poetry to ensure it's in the correct virtual environment
ENTRYPOINT ["/bin/bash", "-c", "/app/start-flask.sh"]

