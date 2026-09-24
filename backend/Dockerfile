# syntax=docker/dockerfile:1
# 의존성 버전은 uv.lock이 정한다. uv는 lock을 해시가 붙은 pip 설치 목록으로 옮기는 데만 쓰고
# 최종 이미지에는 넣지 않는다. lock이 pyproject.toml과 맞지 않으면(uv lock 누락) 빌드가 실패한다.
FROM python:3.11-slim AS requirements
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN pip install "uv>=0.8"
WORKDIR /src
COPY pyproject.toml uv.lock ./
RUN uv export --locked --no-emit-project --format requirements-txt -o requirements.txt

FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

# 의존성은 소스보다 먼저 설치해 소스만 바뀌면 이 층을 재사용한다.
COPY --from=requirements /src/requirements.txt /tmp/requirements.txt
RUN pip install --require-hashes --no-deps -r /tmp/requirements.txt && rm /tmp/requirements.txt

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-deps .

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
