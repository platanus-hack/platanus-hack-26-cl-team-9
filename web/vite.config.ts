import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// fs.allow: the Chile outline lives in ../data/processed (see docs/stack.md section 3).
// proxy: the operation mode of mapa 3 calls the backend at /api (docs/mapa3.md section 10). Docker sets
// VITE_API_TARGET=http://backend:8000; locally it defaults to the API started with `uv run cascadasen-api`.
export default defineConfig({
  plugins: [react()],
  server: {
    fs: { allow: [".."] },
    proxy: { "/api": { target: process.env.VITE_API_TARGET ?? "http://localhost:8000", changeOrigin: true } },
  },
});
