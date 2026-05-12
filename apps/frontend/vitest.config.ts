import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
    globals: true,
    exclude: ["node_modules/**", ".next/**", "e2e/**"]
  },
  resolve: {
    alias: {
      "@": new URL(".", import.meta.url).pathname,
      "@ag-ui/client": new URL("./tests/stubs/ag-ui-client.ts", import.meta.url).pathname,
      "@assistant-ui/react-ag-ui": new URL(
        "./tests/stubs/react-ag-ui.ts",
        import.meta.url
      ).pathname
    }
  }
});
