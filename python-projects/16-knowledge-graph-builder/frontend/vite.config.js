import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The FastAPI server serves frontend/dist at "/" and the API under /api (same origin, so the sign-in cookie just works).
// `npm run dev` serves the source with hot reload on :5173 and forwards /api to the server on :8016.
export default defineConfig({
  plugins: [react()],
  build: { outDir: "dist", emptyOutDir: true, sourcemap: false },
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8016" } },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.js"],
    css: false,
    restoreMocks: true,
  },
});
