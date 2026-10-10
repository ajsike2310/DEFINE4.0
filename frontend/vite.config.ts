/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Built app is served by the dashboard server at /app/ (python -m scripts.run_dashboard). `npm run dev` proxies /api to it.
export default defineConfig({
  base: process.env.VITE_BASE ?? "/app/",
  plugins: [react(), tailwindcss()],
  server: { port: 5173, proxy: { "/api": process.env.VITE_API_TARGET ?? "http://127.0.0.1:8002" } },
  // The recorded fixtures and mocks are keyed on /api/..., so tests pin the API base to it.
  test: { environment: "jsdom", include: ["tests/**/*.test.{ts,tsx}"], env: { VITE_API_BASE: "/api" } },
});
