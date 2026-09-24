FROM alpine:3.24
# 헬스체크가 쓰는 nc(busybox 애플릿)가 이미지에 실제로 있는지 빌드 때 확인한다.
# 베이스 이미지가 바뀌어 없어지면 런타임에 영구 unhealthy가 되는 대신 빌드가 실패한다.
RUN apk add --no-cache pgbouncer \
    && (id pgbouncer >/dev/null 2>&1 || adduser -S -D -H pgbouncer) \
    && command -v nc >/dev/null
COPY entrypoint.sh /usr/local/bin/pgbouncer-entrypoint
USER pgbouncer
EXPOSE 6432
HEALTHCHECK --interval=5s --timeout=3s --retries=10 CMD nc -z 127.0.0.1 6432 || exit 1
ENTRYPOINT ["/usr/local/bin/pgbouncer-entrypoint"]
