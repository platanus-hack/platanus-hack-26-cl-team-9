FROM node:22-alpine
# The app imports ../data/processed (see vite.config.ts fs.allow), so it lives in /app/web next to /app/data
WORKDIR /app/web
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
EXPOSE 5173
# Dev server; compose bind-mounts ./web and ./data for hot reload
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
