# Build from the repo root: docker build -f infrastructure/docker/web.Dockerfile .
FROM node:22-alpine AS build
# The app imports ../data/processed (see web/vite.config.ts), so it lives in /app/web next to /app/data
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
COPY data/processed /app/data/processed
RUN npm run build

FROM nginx:stable-alpine
COPY infrastructure/docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/web/dist /usr/share/nginx/html
EXPOSE 80
