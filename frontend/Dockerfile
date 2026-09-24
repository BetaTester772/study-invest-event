# syntax=docker/dockerfile:1
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM caddy:2.11-alpine
COPY Caddyfile /etc/caddy/Caddyfile
# 설정 오류는 컨테이너가 뜬 뒤가 아니라 빌드 때 드러나게 한다.
RUN caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
COPY --from=build /app/dist /srv
EXPOSE 80
