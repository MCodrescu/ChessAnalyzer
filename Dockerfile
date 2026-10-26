FROM node:24-bookworm-slim AS frontend

WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY scripts/build-frontend.mjs ./scripts/build-frontend.mjs
COPY src/chess_analyzer/web/static/ ./src/chess_analyzer/web/static/
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STOCKFISH_PATH=/usr/games/stockfish \
    DJANGO_STATIC_ROOT=/app/staticfiles

# The OS installs the architecture-appropriate engine during image construction.
RUN apt-get update \
    && apt-get install -y --no-install-recommends stockfish \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md THIRD_PARTY_NOTICES.md manage.py gunicorn.conf.py ./
COPY src/ ./src/
COPY --from=frontend /build/src/chess_analyzer/web/static/review/vendor/ ./src/chess_analyzer/web/static/review/vendor/
RUN pip install --no-cache-dir '.[web]' \
    && DJANGO_DEBUG=1 python manage.py collectstatic --noinput \
    && useradd --create-home --uid 10001 analyzer
USER analyzer

FROM runtime AS cli
ENTRYPOINT ["python", "-m", "chess_analyzer"]
CMD ["--check-engine"]

FROM runtime AS web
ENV DJANGO_DEBUG=0
EXPOSE 8080
CMD ["gunicorn", "--config", "gunicorn.conf.py", "chess_analyzer.web.wsgi:application"]