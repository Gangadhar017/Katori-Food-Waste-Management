import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Relative asset paths plus hash routing let the same build run at a domain root
// (served by the API) and under a sub-path (GitHub Pages).
export default defineConfig({
  plugins: [react()],
  base: "./",
  server: {
    port: Number(process.env.PORT) || 5173,
    proxy: { "/api": { target: process.env.KATORI_API || "http://127.0.0.1:8000" } },
  },
  build: { target: "es2022", sourcemap: false },
});
