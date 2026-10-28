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

FROM debian:bookworm-slim AS rating-assets
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git g++ make curl \
    && rm -rf /var/lib/apt/lists/*
RUN git init /model \
    && git -C /model remote add origin https://github.com/MCodrescu/ELO-Estimator.git \
    && git -C /model fetch --depth 1 origin e9867d40a996dee6a98ddbaf2a52bce0c2ab2078 \
    && git -C /model checkout --detach FETCH_HEAD
RUN git init /stockfish \
    && git -C /stockfish remote add origin https://github.com/official-stockfish/Stockfish.git \
    && git -C /stockfish fetch --depth 1 origin edb0d9db6731067ec50ce619ff372b463bc4dd5d \
    && git -C /stockfish checkout --detach FETCH_HEAD \
    && make -C /stockfish/src -j2 build ARCH=general-64 \
    && strip /stockfish/src/stockfish

FROM runtime AS rating-runtime
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends git libgomp1 \
    && pip install --no-cache-dir '.[rating]' \
    && rm -rf /var/lib/apt/lists/*
COPY --from=rating-assets /model/artifacts/rating_model/ /opt/rating-model/
COPY --from=rating-assets /stockfish/src/stockfish /opt/stockfish/stockfish
COPY --from=rating-assets /stockfish/Copying.txt /opt/stockfish/Copying.txt
ENV RATING_MODEL_DIRECTORY=/opt/rating-model \
    RATING_STOCKFISH_EXECUTABLE=/opt/stockfish/stockfish \
    RATING_ENGINE_COMPATIBILITY=same-release \
    RATING_ANALYSIS_CACHE=/app/data/rating-cache \
    RATING_JOB_DATABASE=/app/data/rating-jobs.sqlite3
RUN mkdir -p /app/data && chown analyzer:analyzer /app/data
USER analyzer

FROM rating-runtime AS rating-worker
CMD ["python", "manage.py", "rating_worker"]

FROM rating-runtime AS rating-web
ENV DJANGO_DEBUG=0
EXPOSE 8080
CMD ["gunicorn", "--config", "gunicorn.conf.py", "chess_analyzer.web.wsgi:application"]

FROM runtime AS web
ENV DJANGO_DEBUG=0
EXPOSE 8080
CMD ["gunicorn", "--config", "gunicorn.conf.py", "chess_analyzer.web.wsgi:application"]