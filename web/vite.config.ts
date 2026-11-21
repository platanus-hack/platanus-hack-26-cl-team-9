import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// fs.allow: the Chile outline lives in ../data/processed (see docs/stack.md section 3).
export default defineConfig({
  plugins: [react()],
  server: { fs: { allow: [".."] } },
});
