FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STOCKFISH_PATH=/usr/games/stockfish

# The OS installs the architecture-appropriate engine during image construction.
RUN apt-get update \
    && apt-get install -y --no-install-recommends stockfish \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir . \
    && useradd --create-home --uid 10001 analyzer
USER analyzer

# CLI/worker image, not a web server. Override CMD for a mounted PGN input.
ENTRYPOINT ["python", "-m", "chess_analyzer"]
CMD ["--check-engine"]