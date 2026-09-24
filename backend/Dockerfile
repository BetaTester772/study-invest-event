# syntax=docker/dockerfile:1
FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
RUN pip install .

COPY alembic.ini ./
COPY migrations ./migrations
COPY docker-entrypoint.sh ./
RUN useradd --system --uid 1000 app && mkdir -p /data/uploads && chown -R app /data \
    && chmod +x docker-entrypoint.sh
USER app

ENV STUDY_INVEST_UPLOAD_DIR=/data/uploads
EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "--factory", "study_invest.api.app:create_app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
