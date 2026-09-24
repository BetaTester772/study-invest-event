FROM alpine:3.20
RUN apk add --no-cache pgbouncer \
    && (id pgbouncer >/dev/null 2>&1 || adduser -S -D -H pgbouncer)
COPY entrypoint.sh /usr/local/bin/pgbouncer-entrypoint
USER pgbouncer
EXPOSE 6432
HEALTHCHECK --interval=5s --timeout=3s --retries=10 CMD nc -z 127.0.0.1 6432 || exit 1
ENTRYPOINT ["/usr/local/bin/pgbouncer-entrypoint"]
