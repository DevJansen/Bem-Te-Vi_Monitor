import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      // Proxy da API local (Axios baseURL = "/api")
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        // Streams MJPEG (/api/video-feed) não devem expirar cedo
        timeout: 0,
      },
      // Mídia estática servida pelo FastAPI
      "/captures": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
