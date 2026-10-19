import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development the interface runs on :5173 and forwards /api to the Python server on :8000.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: false } } },
  test: { environment: "node" },
});
