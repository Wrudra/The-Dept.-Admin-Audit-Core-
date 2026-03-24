import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": "/src" },
  },
  server: {
    port: 5173,
    allowedHosts: ["mara-xyloid-dortha.ngrok-free.dev"],
    proxy: {
      // Proxy /api/* to the FastAPI dev server so cookies work on the same origin
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      // Proxy hosted MCP endpoint through the same ngrok/frontend origin
      "/mcp": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
  },
});
