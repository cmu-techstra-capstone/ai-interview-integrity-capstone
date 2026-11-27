# syntax=docker/dockerfile:1
# Backend/data/audio pipeline image. Contains code + Python deps + ffmpeg only.
# No datasets, media, models or caches are baked in: mount data at runtime (see compose.yaml).
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTEST_ADDOPTS="-p no:cacheprovider"

# ffmpeg/ffprobe: media decoding. curl: HTTP range requests to official dataset sources.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Optional extra CA certificates (*.crt), e.g. an intermediate a dataset server omits.
COPY docker/certs/ /usr/local/share/ca-certificates/extra/
RUN update-ca-certificates

WORKDIR /app

# 1) Dependencies only: this layer is cached until pyproject.toml changes.
#    EXTRAS=dev by default; STT candidates (heavy) only when explicitly requested.
ARG EXTRAS=dev
COPY pyproject.toml README.md ./
COPY docker/install_deps.py docker/install_deps.py
RUN python docker/install_deps.py "${EXTRAS}"

# 2) The package itself (fast layer, rebuilt on code changes).
COPY src ./src
RUN pip install --no-deps .

# 3) Small non-media files needed by tests/CLI.
COPY Dockerfile .dockerignore compose.yaml ./
COPY tests ./tests
COPY config ./config
COPY manifests ./manifests
COPY examples ./examples

RUN useradd --create-home --uid 10001 app && mkdir -p /app/data && chown -R app:app /app/data
USER app

CMD ["interview-integrity", "--help"]
