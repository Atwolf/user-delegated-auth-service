import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/agent": {
        target: process.env.VITE_AG_UI_GATEWAY_URL ?? "http://127.0.0.1:18088",
        changeOrigin: true,
      },
    },
  },
});
