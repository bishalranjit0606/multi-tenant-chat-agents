import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

function apiProxy() {
  return {
    target: "http://127.0.0.1:8000",
    changeOrigin: true,
    configure(proxy) {
      // Keep SSE chunks flowing; default proxy buffering hides streaming.
      proxy.on("proxyRes", (proxyRes, _req, res) => {
        const type = String(proxyRes.headers["content-type"] || "");
        if (!type.includes("text/event-stream")) return;
        proxyRes.headers["cache-control"] = "no-cache, no-transform";
        proxyRes.headers["x-accel-buffering"] = "no";
        res.flushHeaders?.();
      });
    },
  };
}

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/shops": apiProxy(),
      "/login": "http://127.0.0.1:8000",
      "/logout": "http://127.0.0.1:8000",
      "/conversations": "http://127.0.0.1:8000",
      "/me": "http://127.0.0.1:8000",
      "/admin": "http://127.0.0.1:8000",
    },
  },
});
